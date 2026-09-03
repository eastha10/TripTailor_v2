"""Runtime dependencies bound into node closures by the graph builder."""

from __future__ import annotations

from dataclasses import dataclass, field

from triptailor_ai.config.settings import Settings, get_settings
from triptailor_ai.providers.router import ModelRouter
from triptailor_ai.retrieval.service import RetrievalService
from triptailor_ai.validation.validator import ItineraryValidator


@dataclass(slots=True)
class PlanningDeps:
    """Everything the nodes need from the outside world."""

    retrieval: RetrievalService
    model_router: ModelRouter
    validator: ItineraryValidator = field(default=None)  # type: ignore[assignment]
    settings: Settings = field(default=None)  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.settings is None:
            self.settings = self.model_router.settings or get_settings()
        if self.validator is None:
            self.validator = ItineraryValidator(settings=self.settings)
