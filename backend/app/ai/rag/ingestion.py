"""
Knowledge ingestion pipeline: chunking, embedding, database sync, and vector upsert.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.providers.embeddings import EmbeddingProvider
from app.ai.rag.chunking import SemanticChunker, chunker
from app.ai.rag.vector_store import VectorStore
from app.models.ai import KnowledgeChunk, KnowledgeDocument, KnowledgeSource

logger = logging.getLogger("ai.rag.ingestion")

KNOWLEDGE_COLLECTION = "knowledge_chunks"


class KnowledgeIngestionService:
    """Orchestrates document indexing into the relational DB and vector store."""

    def __init__(
        self,
        embedding_provider: EmbeddingProvider,
        vector_store: VectorStore,
        chunk_engine: SemanticChunker = chunker,
    ) -> None:
        self.embeddings = embedding_provider
        self.vector_store = vector_store
        self.chunker = chunk_engine

    async def ingest_document(
        self,
        session: AsyncSession,
        source_id: int,
        title: str,
        content: str,
        scope_type: str = "global",
        scope_id: str | None = None,
        is_faq: bool = False,
        faq_question: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> KnowledgeDocument:
        """Process, chunk, embed, and store a document."""
        doc = KnowledgeDocument(
            source_id=source_id,
            title=title,
            content=content,
            scope_type=scope_type,
            scope_id=scope_id,
            metadata_json=json.dumps(metadata or {}),
        )
        session.add(doc)
        await session.flush()
        await session.refresh(doc)

        # 1. Chunk content
        if is_faq and faq_question:
            chunks = self.chunker.chunk_faq(faq_question, content, metadata)
        else:
            chunks = self.chunker.chunk_text(content, metadata)

        doc.chunk_count = len(chunks)

        if not chunks:
            await session.commit()
            return doc

        # 2. Compute embeddings
        texts = [c.content for c in chunks]
        vectors = await self.embeddings.embed_documents(texts)

        # 3. Create DB chunk records
        db_chunks: list[KnowledgeChunk] = []
        for idx, (c, vec) in enumerate(zip(chunks, vectors)):
            kc = KnowledgeChunk(
                document_id=doc.id,
                source_id=source_id,
                chunk_index=idx,
                content=c.content,
                token_count=c.token_count,
                vector_id=f"kc_{doc.id}_{idx}",
                scope_type=scope_type,
                scope_id=scope_id,
                metadata_json=json.dumps(c.metadata),
            )
            session.add(kc)
            db_chunks.append(kc)

        await session.flush()

        # 4. Upsert into Vector Store
        points = [
            {
                "id": kc.vector_id,
                "vector": vec,
                "payload": {
                    "document_id": doc.id,
                    "source_id": source_id,
                    "chunk_id": kc.id,
                    "chunk_index": kc.chunk_index,
                    "scope_type": scope_type,
                    "scope_id": scope_id,
                    "title": title,
                    "content": kc.content,
                },
            }
            for kc, vec in zip(db_chunks, vectors)
        ]
        await self.vector_store.upsert(KNOWLEDGE_COLLECTION, points)
        await session.commit()
        await session.refresh(doc)
        logger.info(
            f"Ingested document #{doc.id} ('{title}') with {len(chunks)} chunks into {KNOWLEDGE_COLLECTION}"
        )
        return doc

    async def delete_document(
        self,
        session: AsyncSession,
        document_id: int,
    ) -> bool:
        """Delete document from DB and purge vectors from vector store."""
        stmt = select(KnowledgeChunk).where(KnowledgeChunk.document_id == document_id)
        res = await session.execute(stmt)
        chunks = list(res.scalars().all())
        vector_ids = [c.vector_id for c in chunks if c.vector_id]

        if vector_ids:
            await self.vector_store.delete(KNOWLEDGE_COLLECTION, vector_ids)

        await session.execute(delete(KnowledgeDocument).where(KnowledgeDocument.id == document_id))
        await session.commit()
        logger.info(f"Deleted document #{document_id} and {len(vector_ids)} vectors")
        return True

    async def delete_source(
        self,
        session: AsyncSession,
        source_id: int,
    ) -> bool:
        """Delete an entire knowledge source, its documents, and vectors."""
        stmt = select(KnowledgeChunk).where(KnowledgeChunk.source_id == source_id)
        res = await session.execute(stmt)
        chunks = list(res.scalars().all())
        vector_ids = [c.vector_id for c in chunks if c.vector_id]

        if vector_ids:
            await self.vector_store.delete(KNOWLEDGE_COLLECTION, vector_ids)

        await session.execute(delete(KnowledgeSource).where(KnowledgeSource.id == source_id))
        await session.commit()
        logger.info(f"Deleted source #{source_id} and purged {len(vector_ids)} vectors")
        return True
