"""Minimal environment variable helpers with .env fallback."""

from __future__ import annotations

import os
from pathlib import Path


_ENV_LOADED = False


def _candidate_env_files() -> list[Path]:
    """Return likely .env file locations for this workspace."""
    here = Path(__file__).resolve().parent
    cwd = Path.cwd().resolve()

    candidates = [cwd / ".env"]
    if here != cwd:
        candidates.append(here / ".env")

    unique_candidates: list[Path] = []
    seen: set[Path] = set()
    for path in candidates:
        if path not in seen:
            seen.add(path)
            unique_candidates.append(path)
    return unique_candidates


def load_local_env() -> None:
    """Load key=value pairs from a local .env file into os.environ once."""
    global _ENV_LOADED
    if _ENV_LOADED:
        return

    for env_file in _candidate_env_files():
        if not env_file.exists():
            continue

        for raw_line in env_file.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value
        break

    _ENV_LOADED = True


def get_env_value(name: str, default: str = "") -> str:
    """Read an environment variable, loading local .env when needed."""
    value = os.getenv(name, "")
    if value:
        return value

    load_local_env()
    return os.getenv(name, default)
