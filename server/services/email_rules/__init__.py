from __future__ import annotations

from pathlib import Path

from .models import EmailRuleAction, EmailRuleCondition, EmailRuleRecord
from .service import EmailRuleService
from .store import EmailRuleStore


_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
_default_db_path = _DATA_DIR / "email_rules.db"
_email_rule_store = EmailRuleStore(_default_db_path)
_email_rule_service = EmailRuleService(_email_rule_store)


def get_email_rule_service() -> EmailRuleService:
    return _email_rule_service


__all__ = [
    "EmailRuleAction",
    "EmailRuleCondition",
    "EmailRuleRecord",
    "EmailRuleService",
    "get_email_rule_service",
]
