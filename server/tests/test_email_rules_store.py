"""Tests for the email rule SQLite store."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from server.services.email_rules.store import EmailRuleStore, _utc_now_iso


@pytest.fixture
def store(tmp_path: Path) -> EmailRuleStore:
    return EmailRuleStore(tmp_path / "test_rules.db")


def _sample_payload(**overrides) -> dict:
    now = _utc_now_iso()
    base = {
        "name": "Test Rule",
        "description": "star from alice",
        "conditions": '{"sender_contains": "alice"}',
        "actions": '[{"type": "star"}]',
        "status": "active",
        "match_count": 0,
        "created_at": now,
        "updated_at": now,
    }
    base.update(overrides)
    return base


class TestEmailRuleStore:
    def test_insert_and_fetch_one(self, store: EmailRuleStore):
        rule_id = store.insert(_sample_payload())
        record = store.fetch_one(rule_id)
        assert record is not None
        assert record.id == rule_id
        assert record.name == "Test Rule"
        assert record.status == "active"

    def test_list_active_filters_by_status(self, store: EmailRuleStore):
        store.insert(_sample_payload(name="Active Rule", status="active"))
        store.insert(_sample_payload(name="Paused Rule", status="paused"))
        active = store.list_active()
        assert len(active) == 1
        assert active[0].name == "Active Rule"

    def test_list_all(self, store: EmailRuleStore):
        store.insert(_sample_payload(name="Rule 1"))
        store.insert(_sample_payload(name="Rule 2", status="paused"))
        all_rules = store.list_all()
        assert len(all_rules) == 2

    def test_delete(self, store: EmailRuleStore):
        rule_id = store.insert(_sample_payload())
        assert store.delete(rule_id) is True
        assert store.fetch_one(rule_id) is None

    def test_delete_nonexistent(self, store: EmailRuleStore):
        assert store.delete(999) is False

    def test_increment_match_count(self, store: EmailRuleStore):
        rule_id = store.insert(_sample_payload())
        store.increment_match_count(rule_id)
        store.increment_match_count(rule_id)
        record = store.fetch_one(rule_id)
        assert record is not None
        assert record.match_count == 2

    def test_update(self, store: EmailRuleStore):
        rule_id = store.insert(_sample_payload())
        updated = store.update(rule_id, {"status": "paused"})
        assert updated is True
        record = store.fetch_one(rule_id)
        assert record is not None
        assert record.status == "paused"

    def test_clear_all(self, store: EmailRuleStore):
        store.insert(_sample_payload(name="Rule 1"))
        store.insert(_sample_payload(name="Rule 2"))
        store.clear_all()
        assert store.list_all() == []
