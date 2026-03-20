"""Email rule tool schemas and actions for the execution agent."""

from __future__ import annotations

import json
from functools import partial
from typing import Any, Callable, Dict, List, Optional

from server.services.email_rules import (
    EmailRuleAction,
    EmailRuleCondition,
    EmailRuleRecord,
    get_email_rule_service,
)
from server.services.execution import get_execution_agent_logs

_SCHEMAS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "createEmailRule",
            "description": (
                "Create an email rule that automatically acts on incoming emails "
                "matching the given conditions. Parse the user's natural language "
                "into structured conditions yourself."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Short descriptive name for the rule (e.g. 'Star emails from Alice').",
                    },
                    "description": {
                        "type": "string",
                        "description": "The original natural language instruction from the user.",
                    },
                    "conditions": {
                        "type": "object",
                        "description": "Conditions to match (AND-ed). At least one must be non-null.",
                        "properties": {
                            "sender_contains": {
                                "type": "string",
                                "description": "Case-insensitive substring to match in sender address.",
                            },
                            "subject_contains": {
                                "type": "string",
                                "description": "Case-insensitive substring to match in subject.",
                            },
                            "body_contains": {
                                "type": "string",
                                "description": "Case-insensitive substring to match in email body.",
                            },
                            "has_attachment": {
                                "type": "boolean",
                                "description": "Match emails with (true) or without (false) attachments.",
                            },
                        },
                        "additionalProperties": False,
                    },
                    "actions": {
                        "type": "array",
                        "description": "List of actions to perform on matching emails.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "type": {
                                    "type": "string",
                                    "enum": ["star", "archive", "label", "notify"],
                                    "description": "Action type.",
                                },
                                "label_name": {
                                    "type": "string",
                                    "description": "Gmail label name (required when type is 'label').",
                                },
                            },
                            "required": ["type"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["name", "description", "conditions", "actions"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "listEmailRules",
            "description": "List all email rules.",
            "parameters": {
                "type": "object",
                "properties": {},
                "required": [],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "deleteEmailRule",
            "description": "Delete an email rule by ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "rule_id": {
                        "type": "integer",
                        "description": "ID of the rule to delete.",
                    },
                },
                "required": ["rule_id"],
                "additionalProperties": False,
            },
        },
    },
]

_LOG_STORE = get_execution_agent_logs()
_RULE_SERVICE = get_email_rule_service()


def get_schemas() -> List[Dict[str, Any]]:
    """Return email rule tool schemas."""
    return _SCHEMAS


def _rule_record_to_payload(record: EmailRuleRecord) -> Dict[str, Any]:
    return {
        "id": record.id,
        "name": record.name,
        "description": record.description,
        "conditions": json.loads(record.conditions),
        "actions": json.loads(record.actions),
        "status": record.status,
        "match_count": record.match_count,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def _create_email_rule_tool(
    *,
    agent_name: str,
    name: str,
    description: str,
    conditions: Any,
    actions: Any,
) -> Dict[str, Any]:
    try:
        parsed_conditions = EmailRuleCondition(**(conditions if isinstance(conditions, dict) else {}))
        parsed_actions = [
            EmailRuleAction(**(a if isinstance(a, dict) else {})) for a in (actions or [])
        ]
        record = _RULE_SERVICE.create_rule(
            name=name,
            description=description,
            conditions=parsed_conditions,
            actions=parsed_actions,
        )
    except Exception as exc:
        _LOG_STORE.record_action(
            agent_name,
            description=f"createEmailRule failed | error={exc}",
        )
        return {"error": str(exc)}

    _LOG_STORE.record_action(
        agent_name,
        description=f"createEmailRule succeeded | rule_id={record.id}",
    )
    return _rule_record_to_payload(record)


def _list_email_rules_tool(*, agent_name: str) -> Dict[str, Any]:
    try:
        records = _RULE_SERVICE.list_rules()
    except Exception as exc:
        _LOG_STORE.record_action(
            agent_name,
            description=f"listEmailRules failed | error={exc}",
        )
        return {"error": str(exc)}

    _LOG_STORE.record_action(
        agent_name,
        description=f"listEmailRules succeeded | count={len(records)}",
    )
    return {"rules": [_rule_record_to_payload(r) for r in records]}


def _delete_email_rule_tool(*, agent_name: str, rule_id: Any) -> Dict[str, Any]:
    try:
        rule_id_int = int(rule_id)
    except (TypeError, ValueError):
        return {"error": "rule_id must be an integer"}

    try:
        deleted = _RULE_SERVICE.delete_rule(rule_id_int)
    except Exception as exc:
        _LOG_STORE.record_action(
            agent_name,
            description=f"deleteEmailRule failed | id={rule_id} | error={exc}",
        )
        return {"error": str(exc)}

    if not deleted:
        return {"error": f"Email rule {rule_id_int} not found"}

    _LOG_STORE.record_action(
        agent_name,
        description=f"deleteEmailRule succeeded | rule_id={rule_id_int}",
    )
    return {"deleted": True, "rule_id": rule_id_int}


def build_registry(agent_name: str) -> Dict[str, Callable[..., Any]]:
    """Return email rule tool callables bound to a specific agent."""
    return {
        "createEmailRule": partial(_create_email_rule_tool, agent_name=agent_name),
        "listEmailRules": partial(_list_email_rules_tool, agent_name=agent_name),
        "deleteEmailRule": partial(_delete_email_rule_tool, agent_name=agent_name),
    }


__all__ = [
    "build_registry",
    "get_schemas",
]
