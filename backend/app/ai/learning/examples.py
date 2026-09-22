"""
Training example dataset export pipeline (JSONL formatting for fine-tuning).
"""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ai import TrainingExample


class TrainingDatasetExporter:
    """Exports approved examples into standard OpenAI/JSONL fine-tuning format."""

    async def export_jsonl(self, session: AsyncSession) -> str:
        stmt = select(TrainingExample).where(TrainingExample.is_approved.is_(True))
        res = await session.execute(stmt)
        examples = list(res.scalars().all())

        lines = []
        for ex in examples:
            entry = {
                "messages": [
                    {
                        "role": "system",
                        "content": ex.system_instruction
                        or "You are a helpful customer service assistant.",
                    },
                    {"role": "user", "content": ex.input_context},
                    {"role": "assistant", "content": ex.target_response},
                ]
            }
            lines.append(json.dumps(entry, ensure_ascii=False))

        return "\n".join(lines)


dataset_exporter = TrainingDatasetExporter()
