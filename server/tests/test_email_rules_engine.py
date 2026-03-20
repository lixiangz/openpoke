"""Tests for the email rule evaluation engine."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List, Optional

from server.services.email_rules.engine import evaluate_rules
from server.services.email_rules.models import (
    EmailRuleAction,
    EmailRuleCondition,
    EmailRuleRecord,
)


@dataclass(frozen=True)
class FakeEmail:
    """Minimal stand-in for ProcessedEmail."""

    id: str = "msg-1"
    thread_id: Optional[str] = None
    query: str = ""
    subject: str = "Hello"
    sender: str = "alice@example.com"
    recipient: str = "me@example.com"
    timestamp: datetime = datetime(2026, 1, 1, tzinfo=timezone.utc)
    label_ids: List[str] = field(default_factory=list)
    clean_text: str = "This is the body"
    has_attachments: bool = False
    attachment_count: int = 0
    attachment_filenames: List[str] = field(default_factory=list)


def _make_rule(
    conditions: EmailRuleCondition,
    actions: Optional[List[EmailRuleAction]] = None,
    rule_id: int = 1,
    status: str = "active",
) -> EmailRuleRecord:
    if actions is None:
        actions = [EmailRuleAction(type="star")]
    return EmailRuleRecord(
        id=rule_id,
        name="test rule",
        description="test",
        conditions=conditions.model_dump_json(),
        actions=f"[{', '.join(a.model_dump_json() for a in actions)}]",
        status=status,
        match_count=0,
        created_at="2026-01-01T00:00:00Z",
        updated_at="2026-01-01T00:00:00Z",
    )


class TestEvaluateRules:
    def test_sender_contains_match(self):
        rule = _make_rule(EmailRuleCondition(sender_contains="alice"))
        matches = evaluate_rules(FakeEmail(), [rule])
        assert len(matches) == 1
        assert matches[0][0].id == 1

    def test_sender_contains_miss(self):
        rule = _make_rule(EmailRuleCondition(sender_contains="bob"))
        matches = evaluate_rules(FakeEmail(), [rule])
        assert len(matches) == 0

    def test_subject_contains_match(self):
        rule = _make_rule(EmailRuleCondition(subject_contains="hello"))
        matches = evaluate_rules(FakeEmail(), [rule])
        assert len(matches) == 1

    def test_body_contains_match(self):
        rule = _make_rule(EmailRuleCondition(body_contains="body"))
        matches = evaluate_rules(FakeEmail(), [rule])
        assert len(matches) == 1

    def test_and_logic_all_match(self):
        rule = _make_rule(
            EmailRuleCondition(sender_contains="alice", subject_contains="hello")
        )
        matches = evaluate_rules(FakeEmail(), [rule])
        assert len(matches) == 1

    def test_and_logic_partial_miss(self):
        rule = _make_rule(
            EmailRuleCondition(sender_contains="alice", subject_contains="goodbye")
        )
        matches = evaluate_rules(FakeEmail(), [rule])
        assert len(matches) == 0

    def test_case_insensitivity(self):
        rule = _make_rule(EmailRuleCondition(sender_contains="ALICE"))
        matches = evaluate_rules(FakeEmail(), [rule])
        assert len(matches) == 1

    def test_has_attachment_true(self):
        rule = _make_rule(EmailRuleCondition(has_attachment=True))
        matches = evaluate_rules(FakeEmail(has_attachments=True), [rule])
        assert len(matches) == 1

    def test_has_attachment_false_mismatch(self):
        rule = _make_rule(EmailRuleCondition(has_attachment=True))
        matches = evaluate_rules(FakeEmail(has_attachments=False), [rule])
        assert len(matches) == 0

    def test_none_fields_are_wildcards(self):
        rule = _make_rule(EmailRuleCondition(sender_contains="alice"))
        email = FakeEmail(subject="Anything", clean_text="Whatever")
        matches = evaluate_rules(email, [rule])
        assert len(matches) == 1

    def test_no_rules_returns_empty(self):
        matches = evaluate_rules(FakeEmail(), [])
        assert matches == []

    def test_multiple_rules_match(self):
        rule1 = _make_rule(EmailRuleCondition(sender_contains="alice"), rule_id=1)
        rule2 = _make_rule(EmailRuleCondition(subject_contains="hello"), rule_id=2)
        matches = evaluate_rules(FakeEmail(), [rule1, rule2])
        assert len(matches) == 2

    def test_actions_deserialized(self):
        actions = [EmailRuleAction(type="star"), EmailRuleAction(type="archive")]
        rule = _make_rule(EmailRuleCondition(sender_contains="alice"), actions=actions)
        matches = evaluate_rules(FakeEmail(), [rule])
        assert len(matches[0][1]) == 2
        assert matches[0][1][0].type == "star"
        assert matches[0][1][1].type == "archive"
