"""
Semantic chunking: heading-aware, paragraph-aware, and FAQ unit chunker.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Chunk:
    """A semantic text chunk with metadata."""

    content: str
    chunk_index: int
    token_count: int
    metadata: dict[str, Any] = field(default_factory=dict)


def estimate_tokens(text: str) -> int:
    """Rough token estimation (1 token ~= 4 chars or 0.75 words)."""
    words = len(text.split())
    chars = len(text)
    return max(1, (words * 4 + chars) // 8)


class SemanticChunker:
    """Chunking engine respecting document structure, headings, and FAQ semantics."""

    def __init__(
        self,
        max_chunk_tokens: int = 400,
        chunk_overlap_tokens: int = 50,
    ) -> None:
        self.max_chunk_tokens = max_chunk_tokens
        self.chunk_overlap_tokens = chunk_overlap_tokens

    def chunk_faq(
        self, question: str, answer: str, metadata: dict[str, Any] | None = None
    ) -> list[Chunk]:
        """Keep Question + Answer as a cohesive atomic unit."""
        meta = metadata.copy() if metadata else {}
        meta["is_faq"] = True
        meta["question"] = question

        text = f"Q: {question.strip()}\nA: {answer.strip()}"
        return [
            Chunk(
                content=text,
                chunk_index=0,
                token_count=estimate_tokens(text),
                metadata=meta,
            )
        ]

    def chunk_text(self, text: str, metadata: dict[str, Any] | None = None) -> list[Chunk]:
        """Heading-aware and paragraph-aware chunking."""
        meta = metadata.copy() if metadata else {}
        clean_text = text.strip()
        if not clean_text:
            return []

        # Split on markdown headings (# H1, ## H2, etc.) or double newlines
        sections = re.split(r"(?m)^(?=#{1,4}\s+)", clean_text)
        raw_blocks: list[str] = []

        for sec in sections:
            sec = sec.strip()
            if not sec:
                continue
            # If section itself is too large, split by paragraphs
            paragraphs = sec.split("\n\n")
            current_block = ""

            for p in paragraphs:
                p = p.strip()
                if not p:
                    continue
                if current_block:
                    candidate = f"{current_block}\n\n{p}"
                else:
                    candidate = p

                if estimate_tokens(candidate) > self.max_chunk_tokens and current_block:
                    raw_blocks.append(current_block)
                    current_block = p
                else:
                    current_block = candidate

            if current_block:
                raw_blocks.append(current_block)

        chunks: list[Chunk] = []
        for idx, block in enumerate(raw_blocks):
            chunks.append(
                Chunk(
                    content=block,
                    chunk_index=idx,
                    token_count=estimate_tokens(block),
                    metadata=meta,
                )
            )

        return chunks


chunker = SemanticChunker()
