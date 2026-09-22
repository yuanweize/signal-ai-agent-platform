"""
Agent Skills registry and progressive loader.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger("ai.skills")


@dataclass
class Skill:
    """Skill definition loaded from SKILL.md."""

    name: str
    description: str
    version: str = "1.0.0"
    scope: str = "all"  # all | group | dm
    body: str = ""
    path: Path | None = None
    is_enabled: bool = True

    def summary(self) -> dict[str, Any]:
        """Return progressive summary without the body to conserve context."""
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "scope": self.scope,
            "is_enabled": self.is_enabled,
        }


class SkillRegistry:
    """Discovers, registers, and progressively loads skills from the skills directory."""

    def __init__(self, skills_dir: Path | None = None) -> None:
        # Default to repo root / skills
        if skills_dir is None:
            backend_dir = Path(__file__).resolve().parent.parent.parent.parent
            self.skills_dir = backend_dir.parent / "skills"
        else:
            self.skills_dir = Path(skills_dir)
        self._skills: dict[str, Skill] = {}
        self.discover()

    def discover(self) -> dict[str, Skill]:
        """Scan skills_dir for SKILL.md files and register their metadata."""
        if not self.skills_dir.exists() or not self.skills_dir.is_dir():
            logger.warning(f"Skills directory {self.skills_dir} not found.")
            return self._skills

        for skill_path in self.skills_dir.iterdir():
            if skill_path.is_dir():
                md_file = skill_path / "SKILL.md"
                if md_file.is_file():
                    try:
                        skill = self._parse_skill_file(md_file)
                        self._skills[skill.name] = skill
                    except Exception as e:
                        logger.error(f"Failed to parse skill at {md_file}: {e}")

        logger.info(f"Discovered {len(self._skills)} skills in {self.skills_dir}")
        return self._skills

    def _parse_skill_file(self, file_path: Path) -> Skill:
        raw = file_path.read_text(encoding="utf-8")
        if raw.startswith("---"):
            parts = raw.split("---", 2)
            if len(parts) >= 3:
                frontmatter_raw = parts[1]
                body = parts[2].strip()
                data = yaml.safe_load(frontmatter_raw) or {}
                return Skill(
                    name=data.get("name", file_path.parent.name),
                    description=data.get("description", ""),
                    version=str(data.get("version", "1.0.0")),
                    scope=data.get("scope", "all"),
                    body=body,
                    path=file_path,
                    is_enabled=True,
                )
        return Skill(
            name=file_path.parent.name,
            description="Operational skill",
            body=raw.strip(),
            path=file_path,
            is_enabled=True,
        )

    def list_skills(self) -> list[Skill]:
        return list(self._skills.values())

    def get_summaries(self, scope: str | None = None) -> list[dict[str, Any]]:
        """Return lightweight summaries for routing, filtered by scope."""
        summaries = []
        for s in self._skills.values():
            if not s.is_enabled:
                continue
            if scope and s.scope != "all" and s.scope != scope:
                continue
            summaries.append(s.summary())
        return summaries

    def get_skill(self, name: str) -> Skill | None:
        return self._skills.get(name)

    def load_body(self, name: str) -> str:
        """Progressively load full skill instructions on demand."""
        skill = self._skills.get(name)
        if not skill:
            return ""
        if not skill.body and skill.path and skill.path.exists():
            parsed = self._parse_skill_file(skill.path)
            skill.body = parsed.body
        return skill.body

    def set_enabled(self, name: str, enabled: bool) -> bool:
        skill = self._skills.get(name)
        if skill:
            skill.is_enabled = enabled
            return True
        return False


skill_registry = SkillRegistry()
