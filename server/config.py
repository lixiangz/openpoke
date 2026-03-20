"""Simplified configuration management."""

import os
from functools import lru_cache
from pathlib import Path
from typing import List, Optional

from pydantic import BaseModel, Field


def _load_env_file() -> None:
    """Load .env from root directory if present."""
    env_path = Path(__file__).parent.parent / ".env"
    if not env_path.is_file():
        return
    try:
        for line in env_path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped and not stripped.startswith("#") and "=" in stripped:
                key, value = stripped.split("=", 1)
                key, value = key.strip(), value.strip().strip("'\"")
                if key and value and key not in os.environ:
                    os.environ[key] = value
    except Exception:
        pass


_load_env_file()


DEFAULT_APP_NAME = "OpenPoke Server"
DEFAULT_APP_VERSION = "0.3.0"


def _env_int(name: str, fallback: int) -> int:
    try:
        return int(os.getenv(name, str(fallback)))
    except (TypeError, ValueError):
        return fallback


class Settings(BaseModel):
    """Application settings with lightweight env fallbacks."""

    # App metadata
    app_name: str = Field(default=DEFAULT_APP_NAME)
    app_version: str = Field(default=DEFAULT_APP_VERSION)

    # Server runtime
    server_host: str = Field(default=os.getenv("OPENPOKE_HOST", "0.0.0.0"))
    server_port: int = Field(default=_env_int("OPENPOKE_PORT", 8001))

    # LLM model selection - tiered by task complexity.
    # Override via env vars: INTERACTION_AGENT_MODEL, EXECUTION_AGENT_MODEL, etc.
    # Interaction agent orchestrates user intent — use the most capable model.
    interaction_agent_model: str = Field(default=os.getenv("INTERACTION_AGENT_MODEL", "openai/gpt-4.1"))
    # Execution agents run multi-step tool loops — mid-tier is sufficient.
    execution_agent_model: str = Field(default=os.getenv("EXECUTION_AGENT_MODEL", "openai/gpt-4.1-mini"))
    execution_agent_search_model: str = Field(default=os.getenv("EXECUTION_AGENT_SEARCH_MODEL", "openai/gpt-4.1-mini"))
    # Summarization and classification are simple tasks — use the cheapest model.
    summarizer_model: str = Field(default=os.getenv("SUMMARIZER_MODEL", "openai/gpt-4.1-nano"))
    email_classifier_model: str = Field(default=os.getenv("EMAIL_CLASSIFIER_MODEL", "openai/gpt-4.1-nano"))

    # Max tokens per task — prevents runaway token usage on bounded tasks.
    # Set to None (omit from env) to let the model decide.
    summarizer_max_tokens: int = Field(default=_env_int("SUMMARIZER_MAX_TOKENS", 1024))
    email_classifier_max_tokens: int = Field(default=_env_int("EMAIL_CLASSIFIER_MAX_TOKENS", 1024))

    # Prompt caching — only active for anthropic/* models; ignored otherwise.
    # Set ENABLE_PROMPT_CACHING=false to disable even for Anthropic models.
    enable_prompt_caching: bool = Field(
        default=os.getenv("ENABLE_PROMPT_CACHING", "auto") != "false"
    )

    # Embedding model for semantic agent roster selection.
    # Must support the /embeddings endpoint via OpenRouter.
    embedding_model: str = Field(
        default=os.getenv("EMBEDDING_MODEL", "openai/text-embedding-3-small")
    )

    # Credentials / integrations
    openrouter_api_key: Optional[str] = Field(default=os.getenv("OPENROUTER_API_KEY"))
    composio_gmail_auth_config_id: Optional[str] = Field(default=os.getenv("COMPOSIO_GMAIL_AUTH_CONFIG_ID"))
    composio_api_key: Optional[str] = Field(default=os.getenv("COMPOSIO_API_KEY"))

    # HTTP behaviour
    cors_allow_origins_raw: str = Field(default=os.getenv("OPENPOKE_CORS_ALLOW_ORIGINS", "*"))
    enable_docs: bool = Field(default=os.getenv("OPENPOKE_ENABLE_DOCS", "1") != "0")
    docs_url: Optional[str] = Field(default=os.getenv("OPENPOKE_DOCS_URL", "/docs"))

    # Interaction agent context window — drop oldest iteration pairs when exceeded.
    # Increase if you need more in-loop context; decrease to save cost on long sessions.
    interaction_agent_max_context_tokens: int = Field(
        default=_env_int("INTERACTION_AGENT_MAX_CONTEXT_TOKENS", 80000)
    )

    # Execution agent context window — drop oldest iteration pairs when exceeded.
    execution_agent_max_context_tokens: int = Field(
        default=_env_int("EXECUTION_AGENT_MAX_CONTEXT_TOKENS", 40000)
    )

    # Maximum number of execution agents that can run concurrently.
    max_concurrent_execution_agents: int = Field(
        default=_env_int("MAX_CONCURRENT_EXECUTION_AGENTS", 3)
    )

    # Summarisation controls
    # Lower in dev to test summarisation quickly; raise in prod to reduce API calls.
    conversation_summary_threshold: int = Field(
        default=_env_int("CONVERSATION_SUMMARY_THRESHOLD", 100)
    )
    # Raise in prod so the model retains more immediate context.
    conversation_summary_tail_size: int = Field(
        default=_env_int("CONVERSATION_SUMMARY_TAIL_SIZE", 10)
    )
    # Trigger summarization when total unsummarized payload exceeds this many chars.
    # Catches large-email conversations before the message-count threshold fires.
    # Prod recommended: 100000
    conversation_summary_char_threshold: int = Field(
        default=_env_int("CONVERSATION_SUMMARY_CHAR_THRESHOLD", 20000)
    )

    @property
    def cors_allow_origins(self) -> List[str]:
        """Parse CORS origins from comma-separated string."""
        if self.cors_allow_origins_raw.strip() in {"", "*"}:
            return ["*"]
        return [origin.strip() for origin in self.cors_allow_origins_raw.split(",") if origin.strip()]

    @property
    def resolved_docs_url(self) -> Optional[str]:
        """Return documentation URL when docs are enabled."""
        return (self.docs_url or "/docs") if self.enable_docs else None

    @property
    def summarization_enabled(self) -> bool:
        """Flag indicating conversation summarisation is active."""
        return self.conversation_summary_threshold > 0


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
