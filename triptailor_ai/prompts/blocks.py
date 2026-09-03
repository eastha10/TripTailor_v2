"""Labelled data blocks embedded in prompts.

Every node hands the model its facts inside an explicitly delimited block::

    <<<CANDIDATE_PLACES
    [{"placeId": "...", ...}]
    CANDIDATE_PLACES>>>

Two reasons for the ceremony:

1. It makes "use only what is inside the block" a checkable instruction.
2. :class:`~triptailor_ai.providers.fake_provider.FakeModelProvider` reads the
   same blocks, so the whole graph can run offline without an API key while
   still exercising real prompt construction.
"""

from __future__ import annotations

import json
import re
from typing import Any

_TEMPLATE = "<<<{name}\n{payload}\n{name}>>>"


def render_block(name: str, payload: Any) -> str:
    """Render ``payload`` as a labelled JSON block."""

    text = json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    return _TEMPLATE.format(name=name, payload=text)


def extract_block(text: str, name: str) -> Any | None:
    """Return the parsed JSON payload of block ``name``, or ``None``."""

    pattern = re.compile(
        rf"<<<{re.escape(name)}\n(.*?)\n{re.escape(name)}>>>",
        re.DOTALL,
    )
    match = pattern.search(text)
    if match is None:
        return None
    try:
        return json.loads(match.group(1))
    except json.JSONDecodeError:
        return None
