"""Tests for _render_active_agents - context pinning, recency sorting, and cap."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from server.agents.interaction_agent.agent import _render_active_agents, _MAX_AGENTS_IN_PROMPT


def _make_roster(entries: list[dict]) -> MagicMock:
    mock = MagicMock()
    mock.get_agent_entries.return_value = entries
    return mock


def _entry(name: str, last_used: str | None = None, use_count: int = 0) -> dict:
    return {"name": name, "last_used": last_used, "use_count": use_count}


def _names_from_result(result: str) -> list[str]:
    """Extract agent names from rendered XML lines."""
    names = []
    for line in result.strip().splitlines():
        if 'name="' in line:
            names.append(line.split('name="')[1].split('"')[0])
    return names


@pytest.fixture(autouse=True)
def patch_roster_load():
    """Prevent file I/O: the roster load() call is a no-op in these tests."""
    with patch("server.agents.interaction_agent.agent.get_agent_roster") as mock_factory:
        yield mock_factory


@pytest.fixture(autouse=True)
def patch_create_task():
    """Suppress background embedding tasks in tests."""
    with patch("server.agents.interaction_agent.agent.asyncio.create_task"):
        yield


# --- Empty roster ---

@pytest.mark.asyncio
async def test_empty_roster_returns_none(patch_roster_load: MagicMock) -> None:
    patch_roster_load.return_value = _make_roster([])
    assert await _render_active_agents() == "None"


# --- Rendering ---

@pytest.mark.asyncio
async def test_single_agent_renders_correctly(patch_roster_load: MagicMock) -> None:
    patch_roster_load.return_value = _make_roster([_entry("Email to Alice", "2026-03-17T10:00:00", 5)])
    result = await _render_active_agents()
    assert '<agent name="Email to Alice" />' in result


@pytest.mark.asyncio
async def test_special_characters_are_escaped(patch_roster_load: MagicMock) -> None:
    patch_roster_load.return_value = _make_roster([_entry('Agent <"Special">')])
    result = await _render_active_agents()
    assert "<" not in result.replace("<agent", "").replace("/>", "")


# --- Cap at MAX_AGENTS_IN_PROMPT ---

@pytest.mark.asyncio
async def test_caps_at_max_agents(patch_roster_load: MagicMock) -> None:
    entries = [_entry(f"Agent {i}", f"2026-03-{i:02d}T00:00:00", i) for i in range(1, 21)]
    patch_roster_load.return_value = _make_roster(entries)

    result = await _render_active_agents()
    assert len(_names_from_result(result)) == _MAX_AGENTS_IN_PROMPT


@pytest.mark.asyncio
async def test_fewer_than_max_agents_all_shown(patch_roster_load: MagicMock) -> None:
    entries = [_entry(f"Agent {i}") for i in range(5)]
    patch_roster_load.return_value = _make_roster(entries)

    result = await _render_active_agents()
    assert len(_names_from_result(result)) == 5


# --- Context pinning ---

@pytest.mark.asyncio
async def test_context_pinning_includes_mentioned_agent(patch_roster_load: MagicMock) -> None:
    # Fill up to the cap with recent agents, plus one old dormant agent
    recent = [_entry(f"Recent Agent {i}", f"2026-03-{i:02d}T00:00:00", i) for i in range(1, _MAX_AGENTS_IN_PROMPT + 1)]
    dormant = _entry("Q3 Budget", "2025-01-01T00:00:00", 1)
    patch_roster_load.return_value = _make_roster([dormant] + recent)

    result = await _render_active_agents("Let's review the Q3 Budget")
    assert "Q3 Budget" in result


@pytest.mark.asyncio
async def test_context_pinning_case_insensitive(patch_roster_load: MagicMock) -> None:
    patch_roster_load.return_value = _make_roster([_entry("Tokyo Restaurant")])
    result = await _render_active_agents("check on the tokyo restaurant booking")
    assert "Tokyo Restaurant" in result


@pytest.mark.asyncio
async def test_context_pinned_agent_not_duplicated(patch_roster_load: MagicMock) -> None:
    patch_roster_load.return_value = _make_roster([_entry("Q3 Budget", "2026-03-17T10:00:00", 5)])
    result = await _render_active_agents("Check Q3 Budget please")
    assert len(_names_from_result(result)) == 1


@pytest.mark.asyncio
async def test_context_pinning_respects_cap(patch_roster_load: MagicMock) -> None:
    # 2 pinned + 20 non-pinned should still cap at MAX
    pinned = [_entry(f"Pinned {i}", "2025-01-01T00:00:00", 1) for i in range(2)]
    rest = [_entry(f"Recent {i}", f"2026-03-{i:02d}T00:00:00", i) for i in range(1, 21)]
    patch_roster_load.return_value = _make_roster(pinned + rest)

    context = "check Pinned 0 and Pinned 1"
    result = await _render_active_agents(context)
    names = _names_from_result(result)

    assert len(names) == _MAX_AGENTS_IN_PROMPT
    assert "Pinned 0" in names
    assert "Pinned 1" in names


# --- Recency ordering ---

@pytest.mark.asyncio
async def test_most_recent_agent_appears_first(patch_roster_load: MagicMock) -> None:
    entries = [
        _entry("Old Agent",  "2025-01-01T00:00:00", 1),
        _entry("New Agent",  "2026-03-17T00:00:00", 1),
        _entry("Mid Agent",  "2026-01-01T00:00:00", 1),
    ]
    patch_roster_load.return_value = _make_roster(entries)

    names = _names_from_result(await _render_active_agents())
    assert names == ["New Agent", "Mid Agent", "Old Agent"]


@pytest.mark.asyncio
async def test_use_count_breaks_recency_tie(patch_roster_load: MagicMock) -> None:
    same_ts = "2026-03-17T10:00:00"
    entries = [
        _entry("Low Use",  same_ts, 1),
        _entry("High Use", same_ts, 10),
    ]
    patch_roster_load.return_value = _make_roster(entries)

    names = _names_from_result(await _render_active_agents())
    assert names[0] == "High Use"


@pytest.mark.asyncio
async def test_agents_with_no_last_used_sorted_last(patch_roster_load: MagicMock) -> None:
    entries = [
        _entry("Never Used", None, 0),
        _entry("Recent",     "2026-03-17T00:00:00", 1),
    ]
    patch_roster_load.return_value = _make_roster(entries)

    names = _names_from_result(await _render_active_agents())
    assert names[0] == "Recent"
    assert names[-1] == "Never Used"


# --- Pinned agents ordering ---

@pytest.mark.asyncio
async def test_pinned_agents_appear_before_recency_sorted(patch_roster_load: MagicMock) -> None:
    """Context-pinned agents should be listed before the recency-sorted rest."""
    entries = [
        _entry("Very Recent",  "2099-12-31T23:59:59", 100),
        _entry("Pinned Agent", "2020-01-01T00:00:00", 1),
    ]
    patch_roster_load.return_value = _make_roster(entries)

    names = _names_from_result(await _render_active_agents("Pinned Agent"))
    assert names[0] == "Pinned Agent"
    assert names[1] == "Very Recent"


@pytest.mark.asyncio
async def test_multiple_pinned_agents_all_appear_first(patch_roster_load: MagicMock) -> None:
    entries = [
        _entry("Recent",  "2099-12-31T23:59:59", 100),
        _entry("Alpha",   "2020-01-01T00:00:00", 1),
        _entry("Beta",    "2020-01-01T00:00:00", 1),
    ]
    patch_roster_load.return_value = _make_roster(entries)

    names = _names_from_result(await _render_active_agents("Check Alpha and Beta"))
    assert names[0] == "Alpha"
    assert names[1] == "Beta"
    assert names[2] == "Recent"


# --- More than MAX_AGENTS pinned ---

@pytest.mark.asyncio
async def test_more_pinned_than_cap_clamps_to_max(patch_roster_load: MagicMock) -> None:
    """If more agents are pinned than the cap, the total is still capped at _MAX_AGENTS_IN_PROMPT."""
    pinned = [_entry(f"P{i}", "2020-01-01T00:00:00", 1) for i in range(_MAX_AGENTS_IN_PROMPT + 3)]
    unpinned = [_entry("Extra", "2099-01-01T00:00:00", 99)]
    patch_roster_load.return_value = _make_roster(pinned + unpinned)

    # Build context that mentions all pinned agents
    context = " ".join(f"P{i}" for i in range(_MAX_AGENTS_IN_PROMPT + 3))
    names = _names_from_result(await _render_active_agents(context))

    # Total is capped at _MAX_AGENTS_IN_PROMPT even when all are pinned
    assert len(names) == _MAX_AGENTS_IN_PROMPT
    assert "Extra" not in names


# --- Entry with missing/empty name ---

@pytest.mark.asyncio
async def test_entry_with_no_name_key_uses_fallback(patch_roster_load: MagicMock) -> None:
    """An entry with no name should render with the fallback 'agent' name."""
    patch_roster_load.return_value = _make_roster([{"last_used": None, "use_count": 0}])
    result = await _render_active_agents()
    assert '<agent name="agent" />' in result


@pytest.mark.asyncio
async def test_entry_with_empty_name_uses_fallback(patch_roster_load: MagicMock) -> None:
    patch_roster_load.return_value = _make_roster([_entry("")])
    result = await _render_active_agents()
    assert '<agent name="agent" />' in result


# --- Default context (no context) ---

@pytest.mark.asyncio
async def test_no_context_shows_agents_by_recency(patch_roster_load: MagicMock) -> None:
    """Calling with no context arg should work and sort by recency."""
    entries = [
        _entry("Old",  "2020-01-01T00:00:00", 1),
        _entry("New",  "2026-03-17T00:00:00", 1),
    ]
    patch_roster_load.return_value = _make_roster(entries)

    names = _names_from_result(await _render_active_agents())
    assert names == ["New", "Old"]


# --- All agents with None last_used ---

@pytest.mark.asyncio
async def test_all_agents_none_last_used_still_renders(patch_roster_load: MagicMock) -> None:
    entries = [_entry(f"Agent {i}", None, 0) for i in range(3)]
    patch_roster_load.return_value = _make_roster(entries)

    names = _names_from_result(await _render_active_agents())
    assert len(names) == 3


# --- prepare_message_with_history ---

@pytest.mark.asyncio
async def test_prepare_message_includes_active_agents_section(patch_roster_load: MagicMock) -> None:
    from server.agents.interaction_agent.agent import prepare_message_with_history

    patch_roster_load.return_value = _make_roster([_entry("My Agent", "2026-03-17T00:00:00", 1)])

    messages = await prepare_message_with_history("hello", "prior transcript")
    content = messages[0]["content"]

    assert "<active_agents>" in content
    assert "My Agent" in content
    assert "<conversation_history>" in content
    assert "<new_user_message>" in content


@pytest.mark.asyncio
async def test_prepare_message_agent_type_uses_agent_tag(patch_roster_load: MagicMock) -> None:
    from server.agents.interaction_agent.agent import prepare_message_with_history

    patch_roster_load.return_value = _make_roster([])

    messages = await prepare_message_with_history("report done", "", message_type="agent")
    content = messages[0]["content"]

    assert "<new_agent_message>" in content
    assert "<new_user_message>" not in content


@pytest.mark.asyncio
async def test_prepare_message_empty_history_shows_none(patch_roster_load: MagicMock) -> None:
    from server.agents.interaction_agent.agent import prepare_message_with_history

    patch_roster_load.return_value = _make_roster([])

    messages = await prepare_message_with_history("hi", "")
    content = messages[0]["content"]

    assert "<conversation_history>\nNone\n</conversation_history>" in content


@pytest.mark.asyncio
async def test_prepare_message_context_pins_agents_from_latest_text(patch_roster_load: MagicMock) -> None:
    """The latest_text is used as context for pinning agents in the active agents section."""
    from server.agents.interaction_agent.agent import prepare_message_with_history

    entries = [
        _entry("Very Recent",  "2099-12-31T23:59:59", 100),
        _entry("My Project",   "2020-01-01T00:00:00", 1),
    ]
    # Fill up to cap so that without pinning, "My Project" would be excluded
    filler = [_entry(f"Filler {i}", f"2026-03-{i+1:02d}T00:00:00", 50) for i in range(_MAX_AGENTS_IN_PROMPT - 1)]
    patch_roster_load.return_value = _make_roster(entries + filler)

    messages = await prepare_message_with_history("Update on My Project please", "some history")
    content = messages[0]["content"]

    assert "My Project" in content
