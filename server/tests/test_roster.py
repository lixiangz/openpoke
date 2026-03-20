"""Tests for AgentRoster - storage, metadata, and legacy migration."""

import json
import pytest
from pathlib import Path

from server.services.execution.roster import AgentRoster


@pytest.fixture
def roster(tmp_path: Path) -> AgentRoster:
    return AgentRoster(tmp_path / "roster.json")


# --- Basic CRUD ---

def test_new_roster_is_empty(roster: AgentRoster) -> None:
    assert roster.get_agents() == []
    assert roster.get_agent_entries() == []


def test_add_agent_stores_metadata(roster: AgentRoster) -> None:
    roster.add_agent("Email to Alice")
    entries = roster.get_agent_entries()

    assert len(entries) == 1
    assert entries[0]["name"] == "Email to Alice"
    assert entries[0]["use_count"] == 1
    assert entries[0]["last_used"] is not None


def test_add_agent_deduplication(roster: AgentRoster) -> None:
    roster.add_agent("Email to Alice")
    roster.add_agent("Email to Alice")
    assert len(roster.get_agents()) == 1


def test_get_agents_returns_names_only(roster: AgentRoster) -> None:
    roster.add_agent("Agent A")
    roster.add_agent("Agent B")
    assert roster.get_agents() == ["Agent A", "Agent B"]


def test_get_agent_entries_returns_full_metadata(roster: AgentRoster) -> None:
    roster.add_agent("Agent A")
    entry = roster.get_agent_entries()[0]
    assert "name" in entry
    assert "use_count" in entry
    assert "last_used" in entry


# --- touch_agent ---

def test_touch_agent_increments_use_count(roster: AgentRoster) -> None:
    roster.add_agent("Agent A")
    roster.touch_agent("Agent A")
    assert roster.get_agent_entries()[0]["use_count"] == 2


def test_touch_agent_updates_last_used(roster: AgentRoster) -> None:
    roster.add_agent("Agent A")
    first_ts = roster.get_agent_entries()[0]["last_used"]
    roster.touch_agent("Agent A")
    second_ts = roster.get_agent_entries()[0]["last_used"]
    # Timestamps are ISO strings; second >= first
    assert second_ts >= first_ts


def test_touch_nonexistent_agent_is_noop(roster: AgentRoster) -> None:
    roster.touch_agent("Ghost Agent")
    assert roster.get_agents() == []


def test_touch_updates_correct_agent(roster: AgentRoster) -> None:
    roster.add_agent("Agent A")
    roster.add_agent("Agent B")
    roster.touch_agent("Agent B")

    entries = {e["name"]: e for e in roster.get_agent_entries()}
    assert entries["Agent A"]["use_count"] == 1
    assert entries["Agent B"]["use_count"] == 2


# --- Persistence ---

def test_persist_and_reload(tmp_path: Path) -> None:
    path = tmp_path / "roster.json"
    roster = AgentRoster(path)
    roster.add_agent("Persist Test")
    roster.touch_agent("Persist Test")

    reloaded = AgentRoster(path)
    entries = reloaded.get_agent_entries()
    assert len(entries) == 1
    assert entries[0]["name"] == "Persist Test"
    assert entries[0]["use_count"] == 2


def test_clear_removes_all(roster: AgentRoster) -> None:
    roster.add_agent("A")
    roster.add_agent("B")
    roster.clear()
    assert roster.get_agents() == []


# --- Legacy migration ---

def test_load_migrates_legacy_string_format(tmp_path: Path) -> None:
    path = tmp_path / "roster.json"
    path.write_text(json.dumps(["Alice Agent", "Bob Agent"]))

    roster = AgentRoster(path)
    entries = roster.get_agent_entries()

    assert len(entries) == 2
    assert entries[0]["name"] == "Alice Agent"
    assert entries[0]["use_count"] == 0
    assert entries[0]["last_used"] is None
    assert entries[1]["name"] == "Bob Agent"


def test_migrated_legacy_entries_are_resaved_as_dicts(tmp_path: Path) -> None:
    path = tmp_path / "roster.json"
    path.write_text(json.dumps(["Legacy Agent"]))

    roster = AgentRoster(path)
    roster.touch_agent("Legacy Agent")  # Triggers a save

    reloaded = AgentRoster(path)
    entries = reloaded.get_agent_entries()
    assert entries[0]["use_count"] == 1  # Migrated, then touched once


# --- Load edge cases ---

def test_load_corrupted_json_resets_to_empty(tmp_path: Path) -> None:
    """Corrupted roster.json should be handled gracefully, not crash."""
    path = tmp_path / "roster.json"
    path.write_text("{not valid json!!")

    roster = AgentRoster(path)
    assert roster.get_agents() == []
    assert roster.get_agent_entries() == []


def test_load_mixed_legacy_and_dict_entries(tmp_path: Path) -> None:
    """A roster with both legacy strings and dict entries migrates correctly."""
    path = tmp_path / "roster.json"
    mixed = [
        "LegacyOnly",
        {"name": "DictAgent", "last_used": "2026-01-01T00:00:00", "use_count": 5},
    ]
    path.write_text(json.dumps(mixed))

    roster = AgentRoster(path)
    entries = roster.get_agent_entries()

    assert len(entries) == 2
    assert entries[0]["name"] == "LegacyOnly"
    assert entries[0]["use_count"] == 0
    assert entries[0]["last_used"] is None
    assert entries[1]["name"] == "DictAgent"
    assert entries[1]["use_count"] == 5


def test_load_non_list_json_resets_to_empty(tmp_path: Path) -> None:
    """A roster file containing a non-list (e.g. a dict) should not crash."""
    path = tmp_path / "roster.json"
    path.write_text(json.dumps({"unexpected": "format"}))

    roster = AgentRoster(path)
    # data is a dict, not a list, so the `isinstance(data, list)` branch is skipped
    # and self._agents stays as []
    assert roster.get_agents() == []


def test_load_list_with_dict_missing_name_key_is_skipped(tmp_path: Path) -> None:
    """Dicts without a 'name' key in the roster list are silently dropped."""
    path = tmp_path / "roster.json"
    data = [
        {"name": "Good", "last_used": None, "use_count": 0},
        {"no_name_field": True, "use_count": 3},
    ]
    path.write_text(json.dumps(data))

    roster = AgentRoster(path)
    entries = roster.get_agent_entries()
    assert len(entries) == 1
    assert entries[0]["name"] == "Good"


# --- Save edge cases ---

def test_save_creates_parent_directories(tmp_path: Path) -> None:
    """save() should create parent dirs if they don't exist."""
    path = tmp_path / "nested" / "deep" / "roster.json"
    AgentRoster(path)
    # Constructor calls load() -> path doesn't exist -> calls save()
    assert path.exists()


def test_save_retry_on_blocking_io_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """save() retries on BlockingIOError, then succeeds."""
    import fcntl
    path = tmp_path / "roster.json"
    roster = AgentRoster(path)

    call_count = 0
    original_flock = fcntl.flock

    def _flaky_flock(fd, operation):
        nonlocal call_count
        if operation & fcntl.LOCK_EX:
            call_count += 1
            if call_count <= 2:
                raise BlockingIOError("locked")
        return original_flock(fd, operation)

    monkeypatch.setattr(fcntl, "flock", _flaky_flock)
    monkeypatch.setattr("time.sleep", lambda _: None)  # don't actually sleep

    roster.add_agent("RetryTest")
    # add_agent calls save() internally; it should have retried and succeeded
    reloaded = AgentRoster(path)
    assert "RetryTest" in reloaded.get_agents()


def test_save_all_retries_exhausted_does_not_crash(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """If all lock retries fail, save() logs a warning but doesn't raise."""
    import fcntl
    path = tmp_path / "roster.json"
    roster = AgentRoster(path)

    def _always_block(_, operation: int) -> None:
        if operation & fcntl.LOCK_EX:
            raise BlockingIOError("always locked")

    monkeypatch.setattr(fcntl, "flock", _always_block)
    monkeypatch.setattr("time.sleep", lambda _: None)

    # Should not raise
    roster.add_agent("FailTest")


# --- Clear edge cases ---

def test_clear_when_file_does_not_exist(tmp_path: Path) -> None:
    """clear() should not crash if the roster file was already deleted."""
    path = tmp_path / "roster.json"
    roster = AgentRoster(path)
    path.unlink()  # manually remove before clear
    roster.clear()
    assert roster.get_agents() == []


def test_clear_removes_file_from_disk(tmp_path: Path) -> None:
    path = tmp_path / "roster.json"
    roster = AgentRoster(path)
    roster.add_agent("A")
    assert path.exists()
    roster.clear()
    assert not path.exists()


# --- get_agent_entries returns a copy ---

def test_get_agent_entries_returns_copy(roster: AgentRoster) -> None:
    """Mutating the returned list should not affect the internal roster."""
    roster.add_agent("Agent A")
    entries = roster.get_agent_entries()
    entries.clear()
    assert len(roster.get_agent_entries()) == 1


# --- touch_agent accumulation ---

def test_touch_agent_accumulates_over_multiple_calls(roster: AgentRoster) -> None:
    roster.add_agent("Agent A")
    for _ in range(5):
        roster.touch_agent("Agent A")
    assert roster.get_agent_entries()[0]["use_count"] == 6  # 1 from add + 5 touches


# --- add_agent with empty string ---

def test_add_agent_empty_name_is_stored(roster: AgentRoster) -> None:
    """add_agent does not validate names; empty string is allowed."""
    roster.add_agent("")
    assert roster.get_agents() == [""]
