"""
Centralized Alembic migration helpers and dynamic head resolution.
"""

from __future__ import annotations

import functools
import logging
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

logger = logging.getLogger("services.migration")

EXPECTED_HEAD_FALLBACK = "g4c5d6e7f8a9"


@functools.lru_cache(maxsize=1)
def get_expected_alembic_head() -> str:
    """Dynamically resolve the expected current Alembic head revision from migration scripts."""
    try:
        backend_dir = Path(__file__).resolve().parent.parent.parent
        alembic_ini = backend_dir / "alembic.ini"
        if alembic_ini.exists():
            config = Config(str(alembic_ini))
            config.set_main_option("script_location", str(backend_dir / "alembic"))
            script = ScriptDirectory.from_config(config)
            head = script.get_current_head()
            if head:
                return head
    except Exception as e:
        logger.warning(f"Could not dynamically read Alembic head revision: {e}")
    return EXPECTED_HEAD_FALLBACK
