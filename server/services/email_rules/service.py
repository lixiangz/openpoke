from __future__ import annotations

import json
from typing import List, Optional

from ...logging_config import logger
from .models import EmailRuleAction, EmailRuleCondition, EmailRuleRecord
from .store import EmailRuleStore, _utc_now_iso


class EmailRuleService:
    """High-level email rule management."""

    def __init__(self, store: EmailRuleStore):
        self._store = store

    def create_rule(
        self,
        *,
        name: str,
        description: str,
        conditions: EmailRuleCondition,
        actions: List[EmailRuleAction],
    ) -> EmailRuleRecord:
        non_none = {k: v for k, v in conditions.model_dump().items() if v is not None}
        if not non_none:
            raise ValueError("At least one condition must be specified (all fields are None)")

        if not actions:
            raise ValueError("At least one action must be specified")

        for action in actions:
            if action.type == "label" and not action.label_name:
                raise ValueError("label_name is required for actions of type 'label'")

        timestamp = _utc_now_iso()
        payload = {
            "name": name,
            "description": description,
            "conditions": conditions.model_dump_json(),
            "actions": json.dumps([a.model_dump() for a in actions]),
            "status": "active",
            "match_count": 0,
            "created_at": timestamp,
            "updated_at": timestamp,
        }
        rule_id = self._store.insert(payload)
        created = self._store.fetch_one(rule_id)
        if not created:
            raise RuntimeError("Failed to load email rule after insert")
        logger.info("Email rule created", extra={"rule_id": rule_id, "rule_name": name})
        return created

    def list_rules(self) -> List[EmailRuleRecord]:
        return self._store.list_all()

    def list_active_rules(self) -> List[EmailRuleRecord]:
        return self._store.list_active()

    def pause_rule(self, rule_id: int) -> Optional[EmailRuleRecord]:
        updated = self._store.update(rule_id, {"status": "paused"})
        return self._store.fetch_one(rule_id) if updated else None

    def resume_rule(self, rule_id: int) -> Optional[EmailRuleRecord]:
        updated = self._store.update(rule_id, {"status": "active"})
        return self._store.fetch_one(rule_id) if updated else None

    def delete_rule(self, rule_id: int) -> bool:
        return self._store.delete(rule_id)

    def increment_match_count(self, rule_id: int) -> None:
        self._store.increment_match_count(rule_id)

    def clear_all(self) -> None:
        self._store.clear_all()


__all__ = ["EmailRuleService"]
