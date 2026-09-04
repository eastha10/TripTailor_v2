"""Deterministic validation result schemas.

Validation verdicts are produced by Python code only.  The LLM never decides
whether a plan is valid; it only *reacts* to these issues in the repair node.
"""

from __future__ import annotations

from enum import Enum

from pydantic import Field

from triptailor_ai.schemas.common import AiBaseModel


class Severity(str, Enum):
    ERROR = "ERROR"
    WARNING = "WARNING"
    INFO = "INFO"


class ValidationCode(str, Enum):
    """Closed set of validation outcomes.

    ``*_UNVERIFIED`` codes exist so that "we had no data" is never reported as
    "this check passed".
    """

    PLACE_NOT_GROUNDED = "PLACE_NOT_GROUNDED"
    OUTSIDE_TRAVEL_PERIOD = "OUTSIDE_TRAVEL_PERIOD"
    INVALID_TIME_RANGE = "INVALID_TIME_RANGE"
    SCHEDULE_OVERLAP = "SCHEDULE_OVERLAP"
    PLACE_CLOSED = "PLACE_CLOSED"
    OUTSIDE_OPENING_HOURS = "OUTSIDE_OPENING_HOURS"
    OPENING_HOURS_UNVERIFIED = "OPENING_HOURS_UNVERIFIED"
    INSUFFICIENT_TRAVEL_TIME = "INSUFFICIENT_TRAVEL_TIME"
    TRAVEL_TIME_UNVERIFIED = "TRAVEL_TIME_UNVERIFIED"
    BUDGET_EXCEEDED = "BUDGET_EXCEEDED"
    BUDGET_UNVERIFIED = "BUDGET_UNVERIFIED"
    DIETARY_CONSTRAINT_VIOLATION = "DIETARY_CONSTRAINT_VIOLATION"
    DIETARY_DATA_UNVERIFIED = "DIETARY_DATA_UNVERIFIED"
    MOBILITY_CONSTRAINT_VIOLATION = "MOBILITY_CONSTRAINT_VIOLATION"
    MOBILITY_DATA_UNVERIFIED = "MOBILITY_DATA_UNVERIFIED"
    MISSING_MEAL_SLOT = "MISSING_MEAL_SLOT"
    EMPTY_ITINERARY = "EMPTY_ITINERARY"
    EMPTY_DAY = "EMPTY_DAY"
    NOTHING_VALIDATED = "NOTHING_VALIDATED"
    EXCESSIVE_DAILY_LOAD = "EXCESSIVE_DAILY_LOAD"
    DAY_DATE_MISMATCH = "DAY_DATE_MISMATCH"
    OUTSIDE_EVENT_PERIOD = "OUTSIDE_EVENT_PERIOD"
    EVENT_PERIOD_UNVERIFIED = "EVENT_PERIOD_UNVERIFIED"
    ACCOMMODATION_AS_STOP = "ACCOMMODATION_AS_STOP"
    MISSING_ACCOMMODATION = "MISSING_ACCOMMODATION"
    OVERLAPPING_STAY = "OVERLAPPING_STAY"
    STAY_OUTSIDE_TRAVEL_PERIOD = "STAY_OUTSIDE_TRAVEL_PERIOD"
    DUPLICATE_ITEM_ID = "DUPLICATE_ITEM_ID"
    DUPLICATE_PLACE = "DUPLICATE_PLACE"
    IMPLAUSIBLE_STAY_DURATION = "IMPLAUSIBLE_STAY_DURATION"


class ValidationIssue(AiBaseModel):
    code: ValidationCode
    severity: Severity
    #: Itinerary items this issue points at (may be empty for plan-wide issues).
    item_ids: list[str] = Field(default_factory=list)
    message: str
    #: Machine-readable facts backing the verdict, for logs and repair prompts.
    evidence: dict[str, object] = Field(default_factory=dict)
    #: A concrete, bounded instruction the repair planner can act on.
    repair_hint: str | None = None
    rule_id: str | None = None


class ValidationResult(AiBaseModel):
    is_valid: bool = True
    errors: list[ValidationIssue] = Field(default_factory=list)
    warnings: list[ValidationIssue] = Field(default_factory=list)
    #: Rule ids that actually ran, so "not checked" is distinguishable.
    checked_rules: list[str] = Field(default_factory=list)
    #: Rule ids skipped because required data was absent.
    skipped_rules: list[str] = Field(default_factory=list)

    @property
    def error_count(self) -> int:
        return len(self.errors)

    @property
    def warning_count(self) -> int:
        return len(self.warnings)

    def issues(self) -> list[ValidationIssue]:
        return [*self.errors, *self.warnings]
