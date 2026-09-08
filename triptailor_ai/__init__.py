"""TripTailor AI -- Group Preference & Itinerary Orchestrator.

동행자 선호 통합형 여행 일정 설계 에이전트.

The backend-facing surface is :class:`TripPlanningService` plus the schemas in
:mod:`triptailor_ai.schemas`.  Everything else (LangGraph, prompts, providers)
is an implementation detail.

::

    from triptailor_ai import TripPlanningService, TripPlanningRequest

    service = TripPlanningService(retriever=my_retriever)
    result = await service.generate(TripPlanningRequest.model_validate(payload))
"""

from triptailor_ai.config.settings import ProviderName, Settings, get_settings
from triptailor_ai.exceptions import (
    ConfigurationError,
    NoViableCandidatesError,
    PlanningError,
    ProviderUnavailableError,
    RepairLimitExceeded,
    RetrievalError,
    StructuredOutputError,
    TripTailorAIError,
    UnknownGenerationError,
)
from triptailor_ai.providers.base import ChatMessage, ModelProvider
from triptailor_ai.providers.fake_provider import FakeModelProvider
from triptailor_ai.providers.router import ModelRouter
from triptailor_ai.retrieval.base import (
    PlaceRetriever,
    RetrievalConstraints,
    TravelTimeProvider,
)
from triptailor_ai.retrieval.in_memory import InMemoryPlaceRetriever
from triptailor_ai.retrieval.json_retriever import JsonPlaceRetriever
from triptailor_ai.retrieval.travel_time import (
    NullTravelTimeProvider,
    StaticTravelTimeProvider,
)
from triptailor_ai.schemas.generation import (
    GenerationMetadata,
    GenerationStatus,
    PreferenceSummary,
    RevisionRequest,
    TripPlanningResult,
)
from triptailor_ai.schemas.itinerary import (
    Itinerary,
    ItineraryDay,
    ItineraryItem,
    LegacyItineraryItem,
)
from triptailor_ai.schemas.place import PlaceCandidate, TravelTimeEstimate
from triptailor_ai.schemas.preference import Conflict, NormalizedPreference
from triptailor_ai.schemas.trip import (
    AccommodationType,
    BudgetBand,
    ParticipantInput,
    Region,
    TravelPeriod,
    TripPlanningRequest,
    TripStatus,
)
from triptailor_ai.schemas.validation import (
    Severity,
    ValidationCode,
    ValidationIssue,
    ValidationResult,
)
from triptailor_ai.services.planning_service import TripPlanningService
from triptailor_ai.validation.validator import ItineraryValidator

__version__ = "0.1.0"

__all__ = [
    "AccommodationType",
    "BudgetBand",
    "ChatMessage",
    "Conflict",
    "ConfigurationError",
    "FakeModelProvider",
    "GenerationMetadata",
    "GenerationStatus",
    "InMemoryPlaceRetriever",
    "Itinerary",
    "ItineraryDay",
    "ItineraryItem",
    "ItineraryValidator",
    "JsonPlaceRetriever",
    "LegacyItineraryItem",
    "ModelProvider",
    "ModelRouter",
    "NoViableCandidatesError",
    "NormalizedPreference",
    "NullTravelTimeProvider",
    "ParticipantInput",
    "PlaceCandidate",
    "PlaceRetriever",
    "PlanningError",
    "PreferenceSummary",
    "ProviderName",
    "ProviderUnavailableError",
    "Region",
    "RepairLimitExceeded",
    "RetrievalConstraints",
    "RetrievalError",
    "RevisionRequest",
    "Settings",
    "Severity",
    "StaticTravelTimeProvider",
    "StructuredOutputError",
    "TravelPeriod",
    "TravelTimeEstimate",
    "TravelTimeProvider",
    "TripPlanningRequest",
    "TripPlanningResult",
    "TripPlanningService",
    "TripStatus",
    "TripTailorAIError",
    "UnknownGenerationError",
    "ValidationCode",
    "ValidationIssue",
    "ValidationResult",
    "__version__",
    "get_settings",
]
