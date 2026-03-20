from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict


class EmailRuleCondition(BaseModel):
    """Structured conditions for matching emails. Fields are AND-ed; None = wildcard."""

    sender_contains: Optional[str] = None
    subject_contains: Optional[str] = None
    body_contains: Optional[str] = None
    has_attachment: Optional[bool] = None


class EmailRuleAction(BaseModel):
    """Action to perform when a rule matches."""

    type: Literal["star", "archive", "label", "notify"]
    label_name: Optional[str] = None


class EmailRuleRecord(BaseModel):
    """Serialized email rule representation returned to callers."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    description: str
    conditions: str  # JSON-serialized EmailRuleCondition
    actions: str  # JSON-serialized list[EmailRuleAction]
    status: str  # "active" | "paused"
    match_count: int
    created_at: str
    updated_at: str


__all__ = ["EmailRuleCondition", "EmailRuleAction", "EmailRuleRecord"]
