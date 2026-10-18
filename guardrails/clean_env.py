"""Step 7: build a subprocess environment with no secrets for the coding agent.

Any shell command the agent runs (tests, git) should never see API keys,
tokens, or other secrets from the orchestrator's own environment - least
privilege, not "the agent happens not to misuse what it could see."
"""
from __future__ import annotations

import os

# only pass through what a normal dev shell command genuinely needs
SAFE_ENV_ALLOWLIST = {"PATH", "HOME", "LANG", "LC_ALL", "LC_CTYPE", "PYTHONPATH", "VIRTUAL_ENV", "TERM"}


def clean_env_for_agent() -> dict[str, str]:
    """Return a copy of the environment with secrets stripped - no
    *_KEY, *_TOKEN, *_SECRET, *_PASSWORD variables survive, and only an
    explicit allowlist of harmless variables passes through unconditionally."""
    blocked_suffixes = ("_KEY", "_TOKEN", "_SECRET", "_PASSWORD", "_CREDENTIALS")
    cleaned: dict[str, str] = {}
    for key, value in os.environ.items():
        if key in SAFE_ENV_ALLOWLIST:
            cleaned[key] = value
            continue
        if any(key.upper().endswith(suffix) for suffix in blocked_suffixes):
            continue
        # anything else (e.g. plain app config) passes through; only
        # obviously-secret-shaped names are stripped.
        cleaned[key] = value
    return cleaned
