"""Pure rule evaluation engine — no LLM calls, no side effects."""

from __future__ import annotations

import json
from typing import List, Protocol, Tuple

from .models import EmailRuleAction, EmailRuleCondition, EmailRuleRecord


class EmailLike(Protocol):
    """Structural type for objects that can be evaluated against rules."""

    @property
    def sender(self) -> str: ...
    @property
    def subject(self) -> str: ...
    @property
    def clean_text(self) -> str: ...
    @property
    def has_attachments(self) -> bool: ...


def evaluate_rules(
    email: EmailLike,
    rules: List[EmailRuleRecord],
) -> List[Tuple[EmailRuleRecord, List[EmailRuleAction]]]:
    """Return (rule, actions) pairs for every rule that matches the email.

    Conditions are AND-ed. None fields act as wildcards (always match).
    """
    matches: List[Tuple[EmailRuleRecord, List[EmailRuleAction]]] = []

    for rule in rules:
        conditions = EmailRuleCondition.model_validate_json(rule.conditions)
        if _matches(email, conditions):
            actions = [EmailRuleAction(**a) for a in json.loads(rule.actions)]
            matches.append((rule, actions))

    return matches


def _matches(email: EmailLike, conditions: EmailRuleCondition) -> bool:
    if conditions.sender_contains is not None:
        if conditions.sender_contains.lower() not in email.sender.lower():
            return False

    if conditions.subject_contains is not None:
        if conditions.subject_contains.lower() not in email.subject.lower():
            return False

    if conditions.body_contains is not None:
        if conditions.body_contains.lower() not in email.clean_text.lower():
            return False

    if conditions.has_attachment is not None:
        if conditions.has_attachment != email.has_attachments:
            return False

    return True


__all__ = ["evaluate_rules"]
