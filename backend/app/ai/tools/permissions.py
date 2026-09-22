"""
Tool permissions and governance metadata.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ToolPermission:
    """Permissions and safety profile for an executable tool."""

    name: str
    description: str
    read_only: bool = True
    writes_data: bool = False
    external_side_effect: bool = False
    requires_human_approval: bool = False

    def is_safe_for_auto(self) -> bool:
        """Determines if the tool can be safely executed automatically by the agent."""
        return not self.requires_human_approval and not (
            self.writes_data and self.external_side_effect
        )
