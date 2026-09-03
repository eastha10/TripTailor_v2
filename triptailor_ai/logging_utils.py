"""Structured, credential-free logging.

Every record carries ``generationId``/``tripId``/``node`` so a single run can
be reconstructed from logs.  Prompts are logged only when ``LOG_PROMPTS=true``,
because they contain participant free text.
"""

from __future__ import annotations

import json
import logging
from typing import Any

_LOGGER_NAME = "triptailor_ai"
#: Never emitted, whatever a caller passes in.
_REDACTED_KEYS = {"api_key", "apikey", "authorization", "openai_api_key", "qwen_api_key", "token"}


def get_logger() -> logging.Logger:
    return logging.getLogger(_LOGGER_NAME)


def configure_logging(level: str = "INFO") -> None:
    logger = get_logger()
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
        logger.addHandler(handler)
    logger.setLevel(level.upper())


def log_event(event: str, /, level: int = logging.INFO, **fields: Any) -> None:
    """Emit one structured event as a JSON payload."""

    safe = {k: v for k, v in fields.items() if k.lower() not in _REDACTED_KEYS}
    get_logger().log(level, "%s %s", event, json.dumps(safe, ensure_ascii=False, default=str))
