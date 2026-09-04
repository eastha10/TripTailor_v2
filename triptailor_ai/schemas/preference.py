"""Normalized preference + consensus schemas.

These are the structures the LLM is allowed to produce.  Every normalized
preference keeps a pointer back to the participant and the exact source
sentence it came from, so a human reviewer can always audit *why* the plan
looks the way it does.
"""

from __future__ import annotations

from enum import Enum

from pydantic import Field

from triptailor_ai.schemas.common import AiBaseModel


class PreferenceCategory(str, Enum):
    """Closed vocabulary for normalized preferences.

    A closed enum keeps the LLM from inventing new category names, which in
    turn keeps downstream deterministic rules (dietary, mobility, budget)
    able to find what they need.
    """

    ACTIVITY = "ACTIVITY"
    FOOD = "FOOD"
    DIETARY = "DIETARY"
    ACCOMMODATION = "ACCOMMODATION"
    BUDGET = "BUDGET"
    MOBILITY = "MOBILITY"
    PACE = "PACE"
    MUST_VISIT = "MUST_VISIT"
    AVOID = "AVOID"
    AVAILABILITY = "AVAILABILITY"
    ATMOSPHERE = "ATMOSPHERE"
    OTHER = "OTHER"


class ConstraintType(str, Enum):
    HARD = "HARD"
    SOFT = "SOFT"


class Priority(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class NormalizedPreference(AiBaseModel):
    """One atomic, traceable preference extracted from one source sentence."""

    preference_id: str
    participant_id: str
    #: Which questionnaire field the text came from, e.g. ``"mustHaves"``.
    source_field: str
    #: Verbatim substring of the participant's answer. Never paraphrased.
    source_text: str
    category: PreferenceCategory
    #: Short canonical value, e.g. ``"오름/자연"``, ``"no_raw_fish"``.
    value: str
    priority: Priority = Priority.MEDIUM
    constraint_type: ConstraintType = ConstraintType.SOFT
    #: Model self-reported confidence in the interpretation, 0.0 - 1.0.
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    #: Free-text tags used by the retriever for semantic matching.
    tags: list[str] = Field(default_factory=list)

    @property
    def is_hard(self) -> bool:
        return self.constraint_type is ConstraintType.HARD


class NormalizedPreferenceSet(AiBaseModel):
    """Structured-output envelope for the normalizer node."""

    preferences: list[NormalizedPreference] = Field(default_factory=list)


class CommonPreference(AiBaseModel):
    """A preference that several participants share."""

    label: str
    category: PreferenceCategory
    participant_ids: list[str] = Field(default_factory=list)
    preference_ids: list[str] = Field(default_factory=list)
    #: ``len(participant_ids) / total participants`` -- computed, not invented.
    support_ratio: float = Field(default=0.0, ge=0.0, le=1.0)


class Conflict(AiBaseModel):
    """An explicitly surfaced disagreement between participants.

    Conflicts are never silently resolved in favour of one participant; they
    are reported to the human reviewer with compromise options.
    """

    conflict_id: str
    involved_participant_ids: list[str] = Field(default_factory=list)
    related_preference_ids: list[str] = Field(default_factory=list)
    reason: str
    possible_compromises: list[str] = Field(default_factory=list)
    #: ``True`` when at least one side of the conflict is a HARD constraint.
    blocking: bool = False


class ConsensusDraft(AiBaseModel):
    """Structured-output envelope for the consensus node.

    Deliberately narrow: it asks the model only for the two things that need
    judgement -- what the group shares and where it disagrees. The hard/soft
    split and the individual-preference list are recomputed from the
    normalizer's output, so asking the model to repeat them would spend
    tokens on data we discard and enlarge the output for no gain.
    """

    common_preferences: list[CommonPreference] = Field(default_factory=list)
    conflicts: list[Conflict] = Field(default_factory=list)
    summary: str | None = None


class ConsensusAnalysis(AiBaseModel):
    """Full consensus view assembled in code from a :class:`ConsensusDraft`."""

    common_preferences: list[CommonPreference] = Field(default_factory=list)
    individual_preferences: list[NormalizedPreference] = Field(default_factory=list)
    hard_constraints: list[NormalizedPreference] = Field(default_factory=list)
    soft_preferences: list[NormalizedPreference] = Field(default_factory=list)
    conflicts: list[Conflict] = Field(default_factory=list)
    #: One or two sentences the UI can show above the plan.
    summary: str | None = None


class GroupBudget(AiBaseModel):
    """Deterministically derived group budget envelope (not LLM-produced)."""

    #: Most restrictive participant upper bound, per person, whole trip.
    per_person_cap_krw: int | None = None
    limiting_participant_ids: list[str] = Field(default_factory=list)
    #: ``True`` when participants sit in different bands.
    has_band_mismatch: bool = False
