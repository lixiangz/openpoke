"""Interaction agent helpers for prompt construction."""

import asyncio
import re
from html import escape
from pathlib import Path
from typing import Dict, List, Optional

from ...services.execution import get_agent_roster
from ...openrouter_client.client import request_embedding
from ...config import get_settings
from ...logging_config import logger

_prompt_path = Path(__file__).parent / "system_prompt.md"
SYSTEM_PROMPT = _prompt_path.read_text(encoding="utf-8").strip()

# Maximum number of agents to surface in the prompt
_MAX_AGENTS_IN_PROMPT = 15


# Load and return the pre-defined system prompt from markdown file
def build_system_prompt() -> str:
    """Return the static system prompt for the interaction agent."""
    return SYSTEM_PROMPT


# Build structured message with conversation history, active agents, and current turn
async def prepare_message_with_history(
    latest_text: str,
    transcript: str,
    message_type: str = "user",
) -> List[Dict[str, str]]:
    """Compose a message that bundles history, roster, and the latest turn."""
    sections: List[str] = []

    sections.append(_render_conversation_history(transcript))
    sections.append(f"<active_agents>\n{await _render_active_agents(latest_text)}\n</active_agents>")
    sections.append(_render_current_turn(latest_text, message_type))

    content = "\n\n".join(sections)
    return [{"role": "user", "content": content}]


# Format conversation transcript into XML tags for LLM context
def _render_conversation_history(transcript: str) -> str:
    history = transcript.strip()
    if not history:
        history = "None"
    return f"<conversation_history>\n{history}\n</conversation_history>"


def _cosine_similarity(a: List[float], b: List[float]) -> float:
    """Compute cosine similarity between two vectors using numpy."""
    import numpy as np
    a_arr = np.array(a, dtype=np.float64)
    b_arr = np.array(b, dtype=np.float64)
    norm_a = np.linalg.norm(a_arr)
    norm_b = np.linalg.norm(b_arr)
    if norm_a == 0.0 or norm_b == 0.0:
        return 0.0
    return float(np.dot(a_arr, b_arr) / (norm_a * norm_b))


async def _compute_and_store_embedding(agent_name: str) -> None:
    """Background task: compute and persist an embedding for an agent."""
    try:
        settings = get_settings()
        embedding = await request_embedding(
            agent_name,
            model=settings.embedding_model,
            api_key=settings.openrouter_api_key,
        )
        get_agent_roster().store_embedding(agent_name, embedding)
    except Exception as exc:
        logger.warning(f"Failed to compute embedding for agent '{agent_name}': {exc}")


# Format a relevance-filtered subset of execution agents into XML tags for LLM awareness
async def _render_active_agents(context: str = "") -> str:
    roster = get_agent_roster()
    roster.load()
    entries = roster.get_agent_entries()

    if not entries:
        return "None"

    context_lower = context.lower()

    # Partition: agents whose names appear in the current message are always included
    pinned: List[dict] = []
    rest: List[dict] = []
    for entry in entries:
        name = entry.get("name") or ""
        if name and re.search(r'\b' + re.escape(name.lower()) + r'\b', context_lower):
            pinned.append(entry)
        else:
            rest.append(entry)

    # Schedule background embedding for rest agents that don't have one yet
    for entry in rest:
        if entry.get("embedding") is None:
            name = entry.get("name") or ""
            if name:
                asyncio.create_task(_compute_and_store_embedding(name))

    # Semantic ranking if embeddings exist for >50% of rest agents; else recency
    rest_with_embeddings = [e for e in rest if e.get("embedding") is not None]
    if rest and len(rest_with_embeddings) > len(rest) * 0.5:
        settings = get_settings()
        try:
            query_embedding = await request_embedding(
                context or "general task",
                model=settings.embedding_model,
                api_key=settings.openrouter_api_key,
            )
            rest.sort(
                key=lambda e: _cosine_similarity(e.get("embedding") or [], query_embedding),
                reverse=True,
            )
        except Exception as exc:
            logger.debug(f"Embedding query failed, falling back to recency sort: {exc}")
            _sort_by_recency(rest)
    else:
        _sort_by_recency(rest)

    remaining_slots = max(0, _MAX_AGENTS_IN_PROMPT - len(pinned))
    selected = (pinned + rest[:remaining_slots])[:_MAX_AGENTS_IN_PROMPT]

    rendered: List[str] = []
    for entry in selected:
        name = escape(entry.get("name") or "agent", quote=True)
        rendered.append(f'<agent name="{name}" />')

    return "\n".join(rendered)


def _sort_by_recency(entries: List[dict]) -> None:
    """Sort agent entries by last_used descending, then use_count descending, in-place."""
    entries.sort(
        key=lambda e: (e.get("last_used") or "", e.get("use_count", 0)),
        reverse=True,
    )


# Wrap the current message in appropriate XML tags based on sender type
def _render_current_turn(latest_text: str, message_type: str) -> str:
    tag = "new_agent_message" if message_type == "agent" else "new_user_message"
    body = latest_text.strip()
    return f"<{tag}>\n{body}\n</{tag}>"
