"""Adapters: HTTP surface and legacy-shape mapping.

Importing this package does **not** pull in FastAPI; import
``triptailor_ai.adapters.api`` explicitly when you need the HTTP app.
"""

from triptailor_ai.adapters.compatibility import (
    DROPPED_FIELDS,
    describe_loss,
    to_legacy_item,
    to_legacy_items,
    to_legacy_payload,
)

__all__ = [
    "DROPPED_FIELDS",
    "describe_loss",
    "to_legacy_item",
    "to_legacy_items",
    "to_legacy_payload",
]
