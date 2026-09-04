"""Environment-driven configuration.

Loading settings must never require an API key: the package has to import and
start cleanly offline (``fake`` provider), so credential checks happen when a
provider is *built*, not when settings are read.
"""

from __future__ import annotations

from enum import Enum
from functools import lru_cache
from typing import Literal

from typing import Any

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from triptailor_ai.exceptions import ConfigurationError


class ProviderName(str, Enum):
    OPENAI = "openai"
    QWEN = "qwen"
    FAKE = "fake"


#: Node names that may override the default provider/model.
NODE_KEYS: tuple[str, ...] = ("normalizer", "consensus", "planner", "repair", "explanation")


class Settings(BaseSettings):
    """All runtime configuration, read from the environment / ``.env``."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # ---- general -------------------------------------------------------
    app_env: Literal["local", "dev", "prod", "test"] = "local"
    log_level: str = "INFO"
    #: Logging full prompts is off by default: prompts contain participant text.
    log_prompts: bool = False

    # ---- provider selection --------------------------------------------
    default_llm_provider: ProviderName = ProviderName.FAKE
    default_llm_model: str | None = None

    normalizer_llm_provider: ProviderName | None = None
    normalizer_llm_model: str | None = None
    consensus_llm_provider: ProviderName | None = None
    consensus_llm_model: str | None = None
    planner_llm_provider: ProviderName | None = None
    planner_llm_model: str | None = None
    repair_llm_provider: ProviderName | None = None
    repair_llm_model: str | None = None
    explanation_llm_provider: ProviderName | None = None
    explanation_llm_model: str | None = None

    # ---- OpenAI ---------------------------------------------------------
    openai_api_key: str | None = None
    openai_model: str = "gpt-4o-mini"
    openai_base_url: str | None = None
    openai_timeout_seconds: float = 60.0
    #: How structured output is requested. ``function_calling`` is the most
    #: broadly supported; ``prompt`` disables native support entirely.
    openai_structured_method: Literal[
        "function_calling", "json_schema", "json_mode", "prompt"
    ] = "function_calling"

    # ---- Qwen (vLLM OpenAI-compatible server) ----------------------------
    qwen_base_url: str = "http://localhost:8000/v1"
    qwen_api_key: str = "local"
    qwen_served_model_name: str = "qwen"
    qwen_timeout_seconds: float = 120.0
    #: vLLM may or may not accept ``response_format``; off by default so that
    #: the provider falls back to prompt-guided JSON + Pydantic validation.
    qwen_supports_json_schema: bool = False

    # ---- generation behaviour -------------------------------------------
    temperature: float = 0.2
    max_output_tokens: int = 4096
    #: Schema-correction retries for a single LLM call (our loop).
    max_llm_retries: int = Field(default=2, ge=0, le=5)
    #: Transport retries inside the provider SDK: 429 rate limits and 5xx.
    #:
    #: Distinct from ``max_llm_retries``, which corrects bad *content*. A batch
    #: run (evaluation, backfill) will hit rate limits, and those need backoff
    #: rather than being reported as an unavailable provider -- an evaluation
    #: run had 20 of 40 scenarios die this way while the API was healthy.
    max_transport_retries: int = Field(default=4, ge=0, le=10)
    #: Business-level repair loops after a failed validation.
    max_repair_attempts: int = Field(default=2, ge=0, le=5)
    #: Upper bound on candidates handed to the planner prompt.
    max_candidate_places: int = Field(default=40, ge=1)
    #: Replace display names with P1/P2/... in every prompt.
    pseudonymize_participants: bool = True

    # ---- validation tuning ----------------------------------------------
    #: Minutes of slack required on top of a known travel time.
    travel_time_buffer_minutes: int = Field(default=10, ge=0)
    #: Warn when a day exceeds this many scheduled minutes.
    max_daily_scheduled_minutes: int = Field(default=12 * 60, ge=60)
    #: Warn when a day has more stops than this.
    max_items_per_day: int = Field(default=8, ge=1)
    #: Windows in which a meal stop is expected, as minutes past midnight.
    #: Kept as four scalars so they are settable from plain environment
    #: variables; read them through the tuple properties below.
    lunch_start_minutes: int = Field(default=11 * 60, ge=0, le=24 * 60)
    lunch_end_minutes: int = Field(default=14 * 60 + 30, ge=0, le=24 * 60)
    dinner_start_minutes: int = Field(default=17 * 60 + 30, ge=0, le=24 * 60)
    dinner_end_minutes: int = Field(default=21 * 60, ge=0, le=24 * 60)

    @property
    def lunch_window_minutes(self) -> tuple[int, int]:
        return (self.lunch_start_minutes, self.lunch_end_minutes)

    @property
    def dinner_window_minutes(self) -> tuple[int, int]:
        return (self.dinner_start_minutes, self.dinner_end_minutes)

    # ---- retrieval -------------------------------------------------------
    #: Path used by ``JsonPlaceRetriever`` when the service builds a default.
    places_json_path: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _blank_means_unset(cls, data: Any) -> Any:
        """Treat an empty ``.env`` value as "not configured".

        ``.env`` files list every knob, most of them blank
        (``PLANNER_LLM_PROVIDER=``). Without this, that empty string is fed
        straight to the field validator and a copied ``.env.example`` fails to
        load at all -- which is exactly what the README tells people to do.
        """

        if not isinstance(data, dict):
            return data
        return {
            key: value
            for key, value in data.items()
            if not (isinstance(value, str) and not value.strip())
        }

    @model_validator(mode="after")
    def _validate_ranges(self) -> "Settings":
        if not 0.0 <= self.temperature <= 2.0:
            raise ValueError("TEMPERATURE must be between 0.0 and 2.0")
        for meal in ("lunch", "dinner"):
            start = getattr(self, f"{meal}_start_minutes")
            end = getattr(self, f"{meal}_end_minutes")
            if start >= end:
                raise ValueError(
                    f"{meal.upper()}_START_MINUTES must be before {meal.upper()}_END_MINUTES"
                )
        return self

    # ---- node resolution -------------------------------------------------
    def provider_for(self, node_key: str) -> ProviderName:
        """Provider for ``node_key``, falling back to the default."""

        self._assert_known_node(node_key)
        override: ProviderName | None = getattr(self, f"{node_key}_llm_provider")
        return override or self.default_llm_provider

    def model_for(self, node_key: str) -> str | None:
        """Model name for ``node_key``.

        Resolution order: node override -> global default -> provider default.
        ``None`` means "let the provider choose its configured model".
        """

        self._assert_known_node(node_key)
        override: str | None = getattr(self, f"{node_key}_llm_model")
        if override:
            return override
        return self.default_llm_model

    @staticmethod
    def _assert_known_node(node_key: str) -> None:
        if node_key not in NODE_KEYS:
            raise ConfigurationError(
                f"unknown node key '{node_key}'; expected one of {list(NODE_KEYS)}"
            )

    def provider_map(self) -> dict[str, str]:
        """``{node: "provider:model"}`` from configuration alone.

        Reports the intended wiring without constructing clients, so it stays
        usable in a health check even when credentials are missing.
        """

        return {
            key: f"{self.provider_for(key).value}:{self.model_for(key) or 'default'}"
            for key in NODE_KEYS
        }

    def require_openai_key(self) -> str:
        if not self.openai_api_key:
            raise ConfigurationError(
                "OPENAI_API_KEY is not set but an OpenAI-backed node was requested"
            )
        return self.openai_api_key


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Process-wide settings singleton (cache-cleared in tests)."""

    return Settings()


def reset_settings_cache() -> None:
    get_settings.cache_clear()
