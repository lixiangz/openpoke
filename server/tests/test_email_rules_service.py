"""Tests for the email rule service."""

from __future__ import annotations

from pathlib import Path

import pytest

from server.services.email_rules.models import EmailRuleAction, EmailRuleCondition
from server.services.email_rules.service import EmailRuleService
from server.services.email_rules.store import EmailRuleStore


@pytest.fixture
def service(tmp_path: Path) -> EmailRuleService:
    store = EmailRuleStore(tmp_path / "test_rules.db")
    return EmailRuleService(store)


class TestEmailRuleService:
    def test_create_rule_rejects_empty_conditions(self, service: EmailRuleService):
        with pytest.raises(ValueError, match="At least one condition"):
            service.create_rule(
                name="Bad Rule",
                description="no conditions",
                conditions=EmailRuleCondition(),
                actions=[EmailRuleAction(type="star")],
            )

    def test_create_rule_rejects_empty_actions(self, service: EmailRuleService):
        with pytest.raises(ValueError, match="At least one action"):
            service.create_rule(
                name="Bad Rule",
                description="no actions",
                conditions=EmailRuleCondition(sender_contains="alice"),
                actions=[],
            )

    def test_create_rule_rejects_label_without_label_name(self, service: EmailRuleService):
        with pytest.raises(ValueError, match="label_name is required"):
            service.create_rule(
                name="Bad Label Rule",
                description="label without name",
                conditions=EmailRuleCondition(sender_contains="alice"),
                actions=[EmailRuleAction(type="label")],
            )

    def test_create_rule_succeeds(self, service: EmailRuleService):
        record = service.create_rule(
            name="Star from Alice",
            description="Star anything from alice",
            conditions=EmailRuleCondition(sender_contains="alice"),
            actions=[EmailRuleAction(type="star")],
        )
        assert record.id >= 1
        assert record.name == "Star from Alice"
        assert record.status == "active"
        assert record.match_count == 0

    def test_pause_and_resume_rule(self, service: EmailRuleService):
        record = service.create_rule(
            name="Test",
            description="test",
            conditions=EmailRuleCondition(sender_contains="x"),
            actions=[EmailRuleAction(type="star")],
        )

        paused = service.pause_rule(record.id)
        assert paused is not None
        assert paused.status == "paused"

        resumed = service.resume_rule(record.id)
        assert resumed is not None
        assert resumed.status == "active"

    def test_list_rules(self, service: EmailRuleService):
        service.create_rule(
            name="R1",
            description="r1",
            conditions=EmailRuleCondition(sender_contains="a"),
            actions=[EmailRuleAction(type="star")],
        )
        service.create_rule(
            name="R2",
            description="r2",
            conditions=EmailRuleCondition(subject_contains="b"),
            actions=[EmailRuleAction(type="archive")],
        )
        assert len(service.list_rules()) == 2

    def test_list_active_rules(self, service: EmailRuleService):
        r1 = service.create_rule(
            name="R1",
            description="r1",
            conditions=EmailRuleCondition(sender_contains="a"),
            actions=[EmailRuleAction(type="star")],
        )
        service.create_rule(
            name="R2",
            description="r2",
            conditions=EmailRuleCondition(subject_contains="b"),
            actions=[EmailRuleAction(type="archive")],
        )
        service.pause_rule(r1.id)
        active = service.list_active_rules()
        assert len(active) == 1
        assert active[0].name == "R2"

    def test_delete_rule(self, service: EmailRuleService):
        record = service.create_rule(
            name="Temp",
            description="temp",
            conditions=EmailRuleCondition(sender_contains="x"),
            actions=[EmailRuleAction(type="star")],
        )
        assert service.delete_rule(record.id) is True
        assert len(service.list_rules()) == 0

    def test_delete_nonexistent(self, service: EmailRuleService):
        assert service.delete_rule(999) is False

    def test_clear_all(self, service: EmailRuleService):
        service.create_rule(
            name="R1",
            description="r1",
            conditions=EmailRuleCondition(sender_contains="a"),
            actions=[EmailRuleAction(type="star")],
        )
        service.clear_all()
        assert len(service.list_rules()) == 0
