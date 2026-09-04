"""Itinerary validator: runs every rule and aggregates the verdict.

No LLM is involved.  ``is_valid`` is true iff no rule produced an ERROR.
Rules that could not run are reported in ``skipped_rules`` so that "unchecked"
is never mistaken for "checked and fine".
"""

from __future__ import annotations

from triptailor_ai.config.settings import Settings, get_settings
from triptailor_ai.exceptions import ValidationError
from triptailor_ai.schemas.itinerary import Itinerary
from triptailor_ai.schemas.place import PlaceCandidate, TravelTimeEstimate
from triptailor_ai.schemas.preference import GroupBudget, NormalizedPreference
from triptailor_ai.schemas.trip import TripPlanningRequest
from triptailor_ai.schemas.validation import Severity, ValidationResult
from triptailor_ai.validation.rules import DEFAULT_RULES, Rule, ValidationContext


class ItineraryValidator:
    """Deterministic constraint checker."""

    def __init__(
        self,
        rules: tuple[Rule, ...] | list[Rule] | None = None,
        *,
        settings: Settings | None = None,
    ) -> None:
        self.rules: tuple[Rule, ...] = tuple(rules if rules is not None else DEFAULT_RULES)
        self.settings = settings or get_settings()
        duplicate = _first_duplicate([r.rule_id for r in self.rules])
        if duplicate:
            raise ValidationError(f"duplicate rule_id in validator: {duplicate}")

    def validate(
        self,
        *,
        request: TripPlanningRequest,
        itinerary: Itinerary,
        candidates: list[PlaceCandidate] | dict[str, PlaceCandidate],
        hard_constraints: list[NormalizedPreference] | None = None,
        travel_times: list[TravelTimeEstimate] | None = None,
        group_budget: GroupBudget | None = None,
    ) -> ValidationResult:
        context = ValidationContext(
            request=request,
            itinerary=itinerary,
            candidates=_as_place_map(candidates),
            settings=self.settings,
            hard_constraints=list(hard_constraints or []),
            travel_times={
                (t.from_place_id, t.to_place_id): t for t in (travel_times or [])
            },
            group_budget=group_budget or GroupBudget(),
        )

        result = ValidationResult()
        for rule in self.rules:
            if not rule.is_applicable(context):
                result.skipped_rules.append(rule.rule_id)
                continue
            result.checked_rules.append(rule.rule_id)
            for found in rule.check(context):
                if found.severity is Severity.ERROR:
                    result.errors.append(found)
                else:
                    result.warnings.append(found)

        result.is_valid = not result.errors
        return result


def _as_place_map(
    candidates: list[PlaceCandidate] | dict[str, PlaceCandidate],
) -> dict[str, PlaceCandidate]:
    if isinstance(candidates, dict):
        return dict(candidates)
    return {place.place_id: place for place in candidates}


def _first_duplicate(values: list[str]) -> str | None:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            return value
        seen.add(value)
    return None
