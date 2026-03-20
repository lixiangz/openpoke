"""System prompt for the Gmail search assistant."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

_prompt_path = Path(__file__).parent / "system_prompt.md"
_TEMPLATE = _prompt_path.read_text(encoding="utf-8").strip()


def get_system_prompt() -> str:
    """Generate system prompt with today's date for Gmail search assistant."""
    today = datetime.now().strftime("%Y/%m/%d")
    return _TEMPLATE.format(today=today)


__all__ = [
    "get_system_prompt",
]
