"""Execute rule actions against a matched email via Composio."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Dict, List

from ...logging_config import logger
from ..gmail.client import execute_gmail_tool
from .models import EmailRuleAction

if TYPE_CHECKING:
    from ..gmail.processing import ProcessedEmail


async def execute_rule_actions(
    email: "ProcessedEmail",
    actions: List[EmailRuleAction],
    composio_user_id: str,
) -> List[Dict[str, Any]]:
    """Execute all actions for a matched rule. Returns results for each action."""
    results: List[Dict[str, Any]] = []

    for action in actions:
        try:
            result = await asyncio.to_thread(
                _execute_single_action, email, action, composio_user_id
            )
            results.append({"action": action.type, "status": "ok", **result})
        except Exception as exc:
            logger.warning(
                "Email rule action failed",
                extra={
                    "action_type": action.type,
                    "email_id": email.id,
                    "error": str(exc),
                },
            )
            results.append({"action": action.type, "status": "error", "error": str(exc)})

    return results


def _execute_single_action(
    email: "ProcessedEmail",
    action: EmailRuleAction,
    composio_user_id: str,
) -> Dict[str, Any]:
    if action.type == "star":
        execute_gmail_tool(
            "GMAIL_ADD_LABEL_TO_EMAIL",
            composio_user_id,
            arguments={"message_id": email.id, "add_label_ids": ["STARRED"]},
        )
        return {"detail": f"Starred email {email.id}"}

    if action.type == "archive":
        execute_gmail_tool(
            "GMAIL_ADD_LABEL_TO_EMAIL",
            composio_user_id,
            arguments={"message_id": email.id, "remove_label_ids": ["INBOX"]},
        )
        return {"detail": f"Archived email {email.id}"}

    if action.type == "label":
        label_name = action.label_name
        execute_gmail_tool(
            "GMAIL_ADD_LABEL_TO_EMAIL",
            composio_user_id,
            arguments={"message_id": email.id, "add_label_ids": [label_name]},
        )
        return {"detail": f"Labeled email {email.id} with '{label_name}'"}

    if action.type == "notify":
        return {
            "detail": "notify",
            "summary": f"Rule matched: {email.subject} from {email.sender}",
        }

    return {"detail": f"Unknown action type: {action.type}"}


__all__ = ["execute_rule_actions"]
