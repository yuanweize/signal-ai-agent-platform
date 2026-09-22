"""
Memory candidate extraction and PII/privacy redaction.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class MemoryCandidate:
    """Extracted memory item candidate prior to persistence."""

    content: str
    memory_type: str  # preference | fact | case | constraint
    importance: int
    is_safe: bool = True
    rejection_reason: str | None = None


# Patterns for sensitive credentials that must NEVER be persisted
SENSITIVE_PATTERNS = [
    re.compile(r"(?i)(?:password|passwd|pwd)\s*[:=]\s*\S+"),
    re.compile(r"(?i)sk-[a-zA-Z0-9]{20,}"),
    re.compile(r"\b(?:\d[ -]*?){13,16}\b"),  # Credit card pattern
    re.compile(r"(?i)(?:api_key|token|secret)\s*[:=]\s*['\"]?\S+"),
]

# Patterns indicative of durable customer preferences or key facts
PREFERENCE_PATTERNS = [
    (
        re.compile(r"(?i)(?:prefer|preference for|always choose|usually want)\s+(.+)"),
        "preference",
        4,
    ),
    (re.compile(r"(?i)(?:deliver to|my address is|delivery address)\s+(.+)"), "constraint", 4),
    (re.compile(r"(?i)(?:allergic to|allergy to)\s+(.+)"), "constraint", 5),
    (
        re.compile(
            r"(?i)(?:speak|language is)\s+(english|czech|chinese|mandarin|spanish|german)",
            re.IGNORECASE,
        ),
        "preference",
        4,
    ),
    (re.compile(r"(?i)(?:company is|my company|working at)\s+(.+)"), "fact", 3),
]


def redact_sensitive_pii(text: str) -> tuple[str, bool]:
    """Redact passwords, credit cards, or API secrets. Returns (redacted_text, was_redacted)."""
    redacted = text
    found_sensitive = False
    for pat in SENSITIVE_PATTERNS:
        if pat.search(redacted):
            found_sensitive = True
            redacted = pat.sub("[REDACTED_SECRET]", redacted)
    return redacted, found_sensitive


class MemoryExtractor:
    """Extracts durable facts and preferences from customer turns while rejecting secrets."""

    def extract_candidates(self, user_text: str) -> list[MemoryCandidate]:
        clean_text, was_sensitive = redact_sensitive_pii(user_text)
        if was_sensitive:
            # If user provided a raw secret, do not extract as memory
            return []

        candidates: list[MemoryCandidate] = []
        for pat, mem_type, importance in PREFERENCE_PATTERNS:
            match = pat.search(clean_text)
            if match:
                extracted = clean_text.strip()
                candidates.append(
                    MemoryCandidate(
                        content=extracted,
                        memory_type=mem_type,
                        importance=importance,
                        is_safe=True,
                    )
                )
                break  # Pick top match per turn

        return candidates


memory_extractor = MemoryExtractor()
