"""Rule protocol and the context every rule reads from.

Rules are pure functions of the context: no I/O, no LLM, no clock.  That is
what makes a validation verdict reproducible and testable in isolation.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from typing import Iterable

from triptailor_ai.config.settings import Settings
from triptailor_ai.schemas.itinerary import Itinerary
from triptailor_ai.schemas.place import PlaceCandidate, TravelTimeEstimate
from triptailor_ai.schemas.preference import GroupBudget, NormalizedPreference
from triptailor_ai.schemas.trip import TripPlanningRequest
from triptailor_ai.schemas.validation import Severity, ValidationCode, ValidationIssue


@dataclass(slots=True)
class ValidationContext:
    """Everything a rule may look at."""

    request: TripPlanningRequest
    itinerary: Itinerary
    #: ``placeId -> PlaceCandidate`` for the retrieved candidate set.
    candidates: dict[str, PlaceCandidate]
    settings: Settings
    hard_constraints: list[NormalizedPreference] = field(default_factory=list)
    #: ``(fromPlaceId, toPlaceId) -> estimate``; missing means unknown.
    travel_times: dict[tuple[str, str], TravelTimeEstimate] = field(default_factory=dict)
    group_budget: GroupBudget = field(default_factory=GroupBudget)

    @property
    def participant_count(self) -> int:
        return len(self.request.participants)

    def place_for(self, place_id: str) -> PlaceCandidate | None:
        return self.candidates.get(place_id)


class Rule(abc.ABC):
    """One independent constraint check."""

    #: Stable identifier, reported in ``checkedRules`` / ``skippedRules``.
    rule_id: str = "rule"
    description: str = ""

    def is_applicable(self, context: ValidationContext) -> bool:
        """Whether the rule has the data it needs to say anything at all."""

        return bool(context.itinerary.all_items())

    @abc.abstractmethod
    def check(self, context: ValidationContext) -> Iterable[ValidationIssue]:
        """Yield issues.  Yielding nothing means the rule found no problem."""


def issue(
    code: ValidationCode,
    severity: Severity,
    message: str,
    *,
    rule_id: str,
    item_ids: Iterable[str] = (),
    evidence: dict[str, object] | None = None,
    repair_hint: str | None = None,
) -> ValidationIssue:
    """Small constructor so rules stay readable."""

    return ValidationIssue(
        code=code,
        severity=severity,
        item_ids=list(item_ids),
        message=message,
        evidence=evidence or {},
        repair_hint=repair_hint,
        rule_id=rule_id,
    )
