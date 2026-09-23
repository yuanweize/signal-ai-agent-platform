# Signal Market Bot — Backend Application
import os

# Normalize NO_PROXY to strip IPv6 entries (e.g. ::1) that trigger httpx.InvalidURL parser bug
for _k in ("NO_PROXY", "no_proxy"):
    if _k in os.environ and ":" in os.environ[_k]:
        os.environ[_k] = ",".join(
            _p.strip() for _p in os.environ[_k].split(",") if not _p.strip().startswith(":")
        )
