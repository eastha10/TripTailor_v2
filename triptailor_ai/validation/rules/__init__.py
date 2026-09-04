"""Independent, deterministic constraint rules."""

from triptailor_ai.validation.rules.base import Rule, ValidationContext, issue
from triptailor_ai.validation.rules.accommodation_rule import AccommodationRule
from triptailor_ai.validation.rules.budget_rule import BudgetRule
from triptailor_ai.validation.rules.completeness_rule import CompletenessRule
from triptailor_ai.validation.rules.daily_load_rule import DailyLoadRule
from triptailor_ai.validation.rules.date_rule import DateRule
from triptailor_ai.validation.rules.event_period_rule import EventPeriodRule
from triptailor_ai.validation.rules.dietary_rule import DietaryRule
from triptailor_ai.validation.rules.mobility_rule import MobilityRule
from triptailor_ai.validation.rules.opening_hours_rule import OpeningHoursRule
from triptailor_ai.validation.rules.overlap_rule import OverlapRule
from triptailor_ai.validation.rules.place_grounding_rule import PlaceGroundingRule
from triptailor_ai.validation.rules.time_rule import TimeRangeRule
from triptailor_ai.validation.rules.travel_time_rule import TravelTimeRule

#: Execution order: grounding first, because later rules read place data.
DEFAULT_RULES: tuple[Rule, ...] = (
    # Runs unconditionally, so an empty plan can never be reported as valid.
    CompletenessRule(),
    PlaceGroundingRule(),
    DateRule(),
    TimeRangeRule(),
    OverlapRule(),
    OpeningHoursRule(),
    EventPeriodRule(),
    AccommodationRule(),
    TravelTimeRule(),
    BudgetRule(),
    DietaryRule(),
    MobilityRule(),
    DailyLoadRule(),
)

__all__ = [
    "DEFAULT_RULES",
    "AccommodationRule",
    "BudgetRule",
    "CompletenessRule",
    "DailyLoadRule",
    "DateRule",
    "DietaryRule",
    "EventPeriodRule",
    "MobilityRule",
    "OpeningHoursRule",
    "OverlapRule",
    "PlaceGroundingRule",
    "Rule",
    "TimeRangeRule",
    "TravelTimeRule",
    "ValidationContext",
    "issue",
]
