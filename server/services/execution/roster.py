"""Simple agent roster management - agent names with usage metadata."""

import json
import fcntl
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from ...logging_config import logger


class AgentRoster:
    """Roster that stores agents with recency and frequency metadata in a JSON file."""

    def __init__(self, roster_path: Path):
        self._roster_path = roster_path
        self._agents: list[dict] = []
        self.load()

    def load(self) -> None:
        """Load agents from roster.json, handling both legacy (list[str]) and current formats."""
        if self._roster_path.exists():
            try:
                with open(self._roster_path, 'r') as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        self._agents = []
                        for item in data:
                            if isinstance(item, str):
                                # Migrate legacy format: plain string → dict
                                self._agents.append({
                                    "name": item,
                                    "last_used": None,
                                    "use_count": 0,
                                })
                            elif isinstance(item, dict) and "name" in item:
                                self._agents.append(item)
            except Exception as exc:
                logger.warning(f"Failed to load roster.json: {exc}")
                self._agents = []
        else:
            self._agents = []
            self.save()

    def save(self) -> None:
        """Save agents to roster.json with file locking."""
        max_retries = 5
        retry_delay = 0.1

        for attempt in range(max_retries):
            try:
                self._roster_path.parent.mkdir(parents=True, exist_ok=True)

                with open(self._roster_path, 'w') as f:
                    fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                    try:
                        json.dump(self._agents, f, indent=2)
                        return
                    finally:
                        fcntl.flock(f.fileno(), fcntl.LOCK_UN)

            except BlockingIOError:
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    retry_delay *= 2
                else:
                    logger.warning("Failed to acquire lock on roster.json after retries")
            except Exception as exc:
                logger.warning(f"Failed to save roster.json: {exc}")
                break

    def add_agent(self, agent_name: str) -> None:
        """Add a new agent to the roster with initial usage metadata."""
        self.load()
        if not any(a["name"] == agent_name for a in self._agents):
            self._agents.append({
                "name": agent_name,
                "last_used": datetime.now(timezone.utc).isoformat(),
                "use_count": 1,
            })
            self.save()

    def touch_agent(self, agent_name: str) -> None:
        """Update last_used timestamp and increment use_count for an existing agent."""
        self.load()
        for agent in self._agents:
            if agent["name"] == agent_name:
                agent["last_used"] = datetime.now(timezone.utc).isoformat()
                agent["use_count"] = agent.get("use_count", 0) + 1
                self.save()
                return

    def get_agents(self) -> list[str]:
        """Get list of all agent names."""
        return [a["name"] for a in self._agents]

    def get_agent_entries(self) -> list[dict]:
        """Get full agent entries including usage metadata."""
        return list(self._agents)

    def get_embedding(self, agent_name: str) -> Optional[List[float]]:
        """Return the stored embedding for an agent, or None if not yet computed."""
        for agent in self._agents:
            if agent["name"] == agent_name:
                return agent.get("embedding")
        return None

    def store_embedding(self, agent_name: str, embedding: List[float]) -> None:
        """Persist an embedding for an agent in-place and save to disk."""
        for agent in self._agents:
            if agent["name"] == agent_name:
                agent["embedding"] = embedding
                self.save()
                return

    def clear(self) -> None:
        """Clear the agent roster."""
        self._agents = []
        try:
            if self._roster_path.exists():
                self._roster_path.unlink()
            logger.info("Cleared agent roster")
        except Exception as exc:
            logger.warning(f"Failed to clear roster.json: {exc}")


_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
_ROSTER_PATH = _DATA_DIR / "execution_agents" / "roster.json"

_agent_roster = AgentRoster(_ROSTER_PATH)


def get_agent_roster() -> AgentRoster:
    """Get the singleton roster instance."""
    return _agent_roster
