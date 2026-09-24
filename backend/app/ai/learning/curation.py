"""
Learning candidate generation, PII cleaning, and knowledge/training curation.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import desc, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.memory.extraction import redact_sensitive_pii
from app.ai.rag.ingestion import KnowledgeIngestionService
from app.models.ai import KnowledgeSource, LearningCandidate, TrainingExample

logger = logging.getLogger("ai.learning.curation")


class CandidateConflictError(ValueError):
    """Raised when an operation on a LearningCandidate conflicts due to concurrent claim/transition."""


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
        conversation_id: int | None = None,
    ) -> list[LearningCandidate]:
        stmt = select(LearningCandidate).where(LearningCandidate.status == status)
        if conversation_id is not None:
            stmt = stmt.where(LearningCandidate.conversation_id == conversation_id)
        stmt = stmt.order_by(desc(LearningCandidate.created_at)).limit(limit)
        res = await session.execute(stmt)
        return list(res.scalars().all())

    async def _claim_candidate(
        self,
        session: AsyncSession,
        candidate_id: int,
        processing_status: str,
    ) -> LearningCandidate:
        """
        Atomically claim a pending candidate for processing using a conditional SQL UPDATE.
        Ensures strictly one concurrent request can transition a candidate away from pending.
        """
        stmt = (
            update(LearningCandidate)
            .where(LearningCandidate.id == candidate_id)
            .where(LearningCandidate.status == "pending")
            .values(status=processing_status)
        )
        res = await session.execute(stmt)
        if res.rowcount != 1:
            cand = await session.get(LearningCandidate, candidate_id)
            if not cand:
                raise ValueError(f"Candidate #{candidate_id} not found.")
            raise CandidateConflictError(
                f"Candidate #{candidate_id} has already been {cand.status}."
            )
        await session.commit()
        cand = await session.get(LearningCandidate, candidate_id)
        assert cand is not None
        return cand

    async def promote_to_knowledge(
        self,
        session: AsyncSession,
        candidate_id: int,
        ingestion_service: KnowledgeIngestionService,
        reviewer_name: str = "admin",
        faq_question: str | None = None,
        faq_answer: str | None = None,
        scope_type: str = "global",
        scope_id: str | None = None,
        confirm_global_privacy: bool = False,
    ) -> bool:
        """Promote an approved candidate into the active RAG Knowledge Base with atomic claim."""
        if scope_type == "global" and not confirm_global_privacy:
            raise ValueError(
                "Promoting to global knowledge requires explicit privacy confirmation "
                "(`confirm_global_privacy=True`). Confirm this FAQ contains no customer-specific "
                "promises, credentials, or private facts."
            )

        cand = await self._claim_candidate(session, candidate_id, "processing_knowledge")

        q = (faq_question or cand.suggested_faq_q or cand.customer_question).strip()
        a = (faq_answer or cand.suggested_faq_a or cand.human_answer).strip()

        try:
            # Idempotency / provenance check: check if already promoted to a KnowledgeSource
            existing_source = (
                await session.execute(
                    select(KnowledgeSource).where(
                        KnowledgeSource.source_uri == f"candidate:{cand.id}"
                    )
                )
            ).scalar_one_or_none()

            if existing_source:
                cand.status = "promoted"
                cand.reviewed_by = reviewer_name
                cand.reviewed_at = datetime.now(UTC).replace(tzinfo=None)
                await session.commit()
                return True

            # 1. Create KnowledgeSource with candidate provenance in source_uri
            source = KnowledgeSource(
                title=f"FAQ: {q[:60]}",
                source_type="faq",
                source_uri=f"candidate:{cand.id}",
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
                scope_type=scope_type,
                scope_id=scope_id,
                is_faq=True,
                faq_question=q,
                metadata={
                    "candidate_id": cand.id,
                    "conversation_id": cand.conversation_id,
                    "inbound_message_id": cand.inbound_message_id,
                    "outbound_message_id": cand.outbound_message_id,
                    "reviewed_by": reviewer_name,
                    "approved_at": datetime.now(UTC).isoformat(),
                    "scope_type": scope_type,
                    "scope_id": scope_id,
                },
            )

            # 3. Update candidate status to promoted
            cand.status = "promoted"
            cand.reviewed_by = reviewer_name
            cand.reviewed_at = datetime.now(UTC).replace(tzinfo=None)
            await session.commit()
            logger.info(
                f"Promoted candidate #{cand.id} into Knowledge Base source #{source.id} (scope={scope_type})"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to promote candidate #{candidate_id} to knowledge: {e}")
            try:
                await session.rollback()
                # Failure semantics: because vector operations may have partial external side effects,
                # transition to failed_knowledge rather than returning to pending
                cand_fail = await session.get(LearningCandidate, candidate_id)
                if cand_fail:
                    cand_fail.status = "failed_knowledge"
                    await session.commit()
            except Exception:
                pass
            raise

    async def add_to_training(
        self,
        session: AsyncSession,
        candidate_id: int,
        system_instruction: str | None = None,
        reviewer_name: str = "admin",
    ) -> TrainingExample | None:
        """Add candidate to offline fine-tuning dataset with atomic claim."""
        cand = await self._claim_candidate(session, candidate_id, "processing_training")

        try:
            # Idempotency check: verify no training example exists for this candidate
            existing = (
                await session.execute(
                    select(TrainingExample).where(TrainingExample.source_candidate_id == cand.id)
                )
            ).scalar_one_or_none()
            if existing:
                cand.status = "approved"
                await session.commit()
                return existing

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
            cand.reviewed_by = reviewer_name
            cand.reviewed_at = datetime.now(UTC).replace(tzinfo=None)
            await session.commit()
            await session.refresh(example)
            return example
        except Exception as e:
            logger.error(f"Failed to add candidate #{candidate_id} to training: {e}")
            try:
                await session.rollback()
                # Recovery policy: mark as failed_training on durable DB failure
                cand_fail = await session.get(LearningCandidate, candidate_id)
                if cand_fail:
                    cand_fail.status = "failed_training"
                    await session.commit()
            except Exception:
                pass
            raise

    async def reject_candidate(
        self,
        session: AsyncSession,
        candidate_id: int,
        reviewer_name: str = "admin",
    ) -> bool:
        """Reject candidate with atomic claim."""
        cand = await self._claim_candidate(session, candidate_id, "processing_reject")
        cand.status = "rejected"
        cand.reviewed_by = reviewer_name
        cand.reviewed_at = datetime.now(UTC).replace(tzinfo=None)
        await session.commit()
        return True


learning_service = LearningCandidateService()
