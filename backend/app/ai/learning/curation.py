"""
Learning candidate generation, PII cleaning, and knowledge/training curation.
"""

from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.memory.extraction import redact_sensitive_pii
from app.ai.rag.ingestion import KnowledgeIngestionService
from app.models.ai import KnowledgeSource, LearningCandidate, TrainingExample

logger = logging.getLogger("ai.learning.curation")


class LearningCandidateService:
    """Manages distillation of high-quality human answers into knowledge and training candidates."""

    async def create_candidate(
        self,
        session: AsyncSession,
        conversation_id: int,
        customer_question: str,
        human_answer: str,
        inbound_message_id: int | None = None,
        outbound_message_id: int | None = None,
        category: str = "general",
        language: str = "en",
        source_quality: str = "high",
    ) -> LearningCandidate | None:
        """Sanitize and create a pending learning candidate."""
        clean_q, q_sens = redact_sensitive_pii(customer_question)
        clean_a, a_sens = redact_sensitive_pii(human_answer)

        # Safety policy: If text contains raw credentials or cards, reject candidate
        if q_sens or a_sens:
            logger.warning(
                f"Rejected learning candidate for conv #{conversation_id} due to sensitive PII/secrets."
            )
            return None

        cand = LearningCandidate(
            conversation_id=conversation_id,
            inbound_message_id=inbound_message_id,
            outbound_message_id=outbound_message_id,
            customer_question=clean_q.strip(),
            human_answer=clean_a.strip(),
            suggested_faq_q=clean_q.strip(),
            suggested_faq_a=clean_a.strip(),
            category=category,
            language=language,
            source_quality=source_quality,
            status="pending",
        )
        session.add(cand)
        await session.commit()
        await session.refresh(cand)
        logger.info(
            f"Created LearningCandidate #{cand.id} from human reply in conv #{conversation_id}"
        )
        return cand

    async def list_candidates(
        self,
        session: AsyncSession,
        status: str = "pending",
        limit: int = 50,
    ) -> list[LearningCandidate]:
        stmt = (
            select(LearningCandidate)
            .where(LearningCandidate.status == status)
            .order_by(desc(LearningCandidate.created_at))
            .limit(limit)
        )
        res = await session.execute(stmt)
        return list(res.scalars().all())

    async def promote_to_knowledge(
        self,
        session: AsyncSession,
        candidate_id: int,
        ingestion_service: KnowledgeIngestionService,
        reviewer_name: str = "admin",
        faq_question: str | None = None,
        faq_answer: str | None = None,
    ) -> bool:
        """Promote an approved candidate into the active RAG Knowledge Base."""
        cand = await session.get(LearningCandidate, candidate_id)
        if not cand:
            return False

        q = (faq_question or cand.suggested_faq_q or cand.customer_question).strip()
        a = (faq_answer or cand.suggested_faq_a or cand.human_answer).strip()

        # 1. Create KnowledgeSource
        source = KnowledgeSource(
            title=f"FAQ: {q[:60]}",
            source_type="faq",
            language=cand.language,
            status="active",
            trust_level="verified",
            created_by=reviewer_name,
            approved_by=reviewer_name,
        )
        session.add(source)
        await session.flush()
        await session.refresh(source)

        # 2. Ingest as FAQ Document and generate vector chunks
        await ingestion_service.ingest_document(
            session=session,
            source_id=source.id,
            title=f"FAQ: {q}",
            content=a,
            scope_type="global",
            is_faq=True,
            faq_question=q,
            metadata={"candidate_id": cand.id, "conversation_id": cand.conversation_id},
        )

        # 3. Update candidate status
        cand.status = "promoted"
        cand.reviewed_by = reviewer_name
        cand.reviewed_at = datetime.utcnow()
        await session.commit()
        logger.info(f"Promoted candidate #{cand.id} into Knowledge Base source #{source.id}")
        return True

    async def add_to_training(
        self,
        session: AsyncSession,
        candidate_id: int,
        system_instruction: str | None = None,
    ) -> TrainingExample | None:
        """Add candidate to offline fine-tuning dataset."""
        cand = await session.get(LearningCandidate, candidate_id)
        if not cand:
            return None

        example = TrainingExample(
            source_candidate_id=cand.id,
            system_instruction=system_instruction
            or "You are a helpful customer service assistant.",
            input_context=cand.customer_question,
            target_response=cand.human_answer,
            is_approved=True,
        )
        session.add(example)
        cand.status = "approved"
        cand.reviewed_at = datetime.utcnow()
        await session.commit()
        await session.refresh(example)
        return example

    async def reject_candidate(
        self,
        session: AsyncSession,
        candidate_id: int,
        reviewer_name: str = "admin",
    ) -> bool:
        cand = await session.get(LearningCandidate, candidate_id)
        if not cand:
            return False
        cand.status = "rejected"
        cand.reviewed_by = reviewer_name
        cand.reviewed_at = datetime.utcnow()
        await session.commit()
        return True


learning_service = LearningCandidateService()
