from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...logging_config import logger
from .models import EmailRuleRecord


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class EmailRuleStore:
    """Low-level persistence for email rules backed by SQLite."""

    def __init__(self, db_path: Path):
        self._db_path = db_path
        self._lock = threading.Lock()
        self._ensure_directory()
        self._ensure_schema()

    def _ensure_directory(self) -> None:
        try:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as exc:
            logger.warning(
                "email_rules directory creation failed",
                extra={"error": str(exc)},
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        schema_sql = """
        CREATE TABLE IF NOT EXISTS email_rules (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT NOT NULL,
            conditions TEXT NOT NULL,
            actions TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'active',
            match_count INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
        with self._lock, self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute(schema_sql)

    def insert(self, payload: Dict[str, Any]) -> int:
        with self._lock, self._connect() as conn:
            columns = ", ".join(payload.keys())
            placeholders = ", ".join([":" + key for key in payload.keys()])
            sql = f"INSERT INTO email_rules ({columns}) VALUES ({placeholders})"
            conn.execute(sql, payload)
            rule_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            return int(rule_id)

    def fetch_one(self, rule_id: int) -> Optional[EmailRuleRecord]:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM email_rules WHERE id = ?", (rule_id,)
            ).fetchone()
        return self._row_to_record(row) if row else None

    def update(self, rule_id: int, fields: Dict[str, Any]) -> bool:
        if not fields:
            return False
        assignments = ", ".join(f"{key} = :{key}" for key in fields.keys())
        sql = (
            f"UPDATE email_rules SET {assignments}, updated_at = :updated_at"
            " WHERE id = :rule_id"
        )
        payload = {
            **fields,
            "updated_at": _utc_now_iso(),
            "rule_id": rule_id,
        }
        with self._lock, self._connect() as conn:
            cursor = conn.execute(sql, payload)
            return cursor.rowcount > 0

    def list_active(self) -> List[EmailRuleRecord]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM email_rules WHERE status = 'active' ORDER BY id"
            ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def list_all(self) -> List[EmailRuleRecord]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM email_rules ORDER BY id"
            ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def delete(self, rule_id: int) -> bool:
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM email_rules WHERE id = ?", (rule_id,)
            )
            return cursor.rowcount > 0

    def increment_match_count(self, rule_id: int) -> None:
        with self._lock, self._connect() as conn:
            conn.execute(
                "UPDATE email_rules SET match_count = match_count + 1, updated_at = ? WHERE id = ?",
                (_utc_now_iso(), rule_id),
            )

    def clear_all(self) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM email_rules")

    def _row_to_record(self, row: sqlite3.Row) -> EmailRuleRecord:
        data = dict(row)
        return EmailRuleRecord.model_validate(data)


__all__ = ["EmailRuleStore"]
