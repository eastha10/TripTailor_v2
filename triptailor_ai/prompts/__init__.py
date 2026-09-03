"""Prompt construction + prompt versioning.

Every prompt carries a version string that is recorded in
``GenerationMetadata.node_traces``, so an evaluation result can always be tied
back to the exact prompt that produced it.
"""

from triptailor_ai.prompts.blocks import extract_block, render_block
from triptailor_ai.prompts.consensus import (
    CONSENSUS_PROMPT_VERSION,
    build_consensus_messages,
)
from triptailor_ai.prompts.explanation import (
    EXPLANATION_PROMPT_VERSION,
    build_explanation_messages,
)
from triptailor_ai.prompts.normalizer import (
    NORMALIZER_PROMPT_VERSION,
    build_normalizer_messages,
)
from triptailor_ai.prompts.planner import PLANNER_PROMPT_VERSION, build_planner_messages
from triptailor_ai.prompts.pseudonymize import Pseudonymizer
from triptailor_ai.prompts.repair import REPAIR_PROMPT_VERSION, build_repair_messages

#: node key -> prompt version, recorded in generation metadata.
PROMPT_VERSIONS: dict[str, str] = {
    "normalizer": NORMALIZER_PROMPT_VERSION,
    "consensus": CONSENSUS_PROMPT_VERSION,
    "planner": PLANNER_PROMPT_VERSION,
    "repair": REPAIR_PROMPT_VERSION,
    "explanation": EXPLANATION_PROMPT_VERSION,
}

__all__ = [
    "CONSENSUS_PROMPT_VERSION",
    "EXPLANATION_PROMPT_VERSION",
    "NORMALIZER_PROMPT_VERSION",
    "PLANNER_PROMPT_VERSION",
    "PROMPT_VERSIONS",
    "REPAIR_PROMPT_VERSION",
    "Pseudonymizer",
    "build_consensus_messages",
    "build_explanation_messages",
    "build_normalizer_messages",
    "build_planner_messages",
    "build_repair_messages",
    "extract_block",
    "render_block",
]
