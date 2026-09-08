"""Public facade.

The backend uses only this class.  LangGraph, prompts, providers and the
validator are implementation details behind it.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone
from typing import Any

from triptailor_ai.config.settings import Settings, get_settings
from triptailor_ai.exceptions import (
    NoViableCandidatesError,
    TripTailorAIError,
    UnknownGenerationError,
)
from triptailor_ai.graph.builder import build_planning_graph, graph_recursion_limit
from triptailor_ai.graph.routing import PLAN, PREPARE_INPUT, RETRIEVE
from triptailor_ai.graph.state import PlanningState, initial_state, state_summary
from triptailor_ai.logging_utils import configure_logging, log_event
from triptailor_ai.nodes.dependencies import PlanningDeps
from triptailor_ai.providers.router import ModelRouter
from triptailor_ai.retrieval.base import PlaceRetriever, TravelTimeProvider
from triptailor_ai.retrieval.service import RetrievalService
from triptailor_ai.schemas.generation import (
    GenerationMetadata,
    GenerationStatus,
    PreferenceSummary,
    RevisionRequest,
    TripPlanningResult,
)
from triptailor_ai.schemas.itinerary import Itinerary
from triptailor_ai.schemas.preference import GroupBudget
from triptailor_ai.schemas.trip import TripPlanningRequest
from triptailor_ai.schemas.validation import ValidationResult
from triptailor_ai.services.store import (
    GenerationStateStore,
    InMemoryGenerationStore,
)
from triptailor_ai.validation.validator import ItineraryValidator

#: Words that make a revision request need a fresh place search rather than a
#: re-plan over the existing candidates.
_RETRIEVAL_TRIGGERS: tuple[str, ...] = (
    "다른 곳",
    "다른 장소",
    "새로운",
    "새로",
    "추천을 바꿔",
    "후보",
    "지역",
    "말고",
    "빼고 다른",
)


class TripPlanningService:
    """Generate and revise itineraries.

    ``retriever`` is the one dependency a backend must supply in production;
    everything else has a working default.
    """

    def __init__(
        self,
        retriever: PlaceRetriever,
        *,
        model_router: ModelRouter | None = None,
        travel_time_provider: TravelTimeProvider | None = None,
        validator: ItineraryValidator | None = None,
        settings: Settings | None = None,
        store: GenerationStateStore | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        configure_logging(self.settings.log_level)
        self.model_router = model_router or ModelRouter(self.settings)
        self.retrieval = RetrievalService(
            retriever,
            travel_time_provider=travel_time_provider,
            max_candidates=self.settings.max_candidate_places,
        )
        self.deps = PlanningDeps(
            retrieval=self.retrieval,
            model_router=self.model_router,
            validator=validator or ItineraryValidator(settings=self.settings),
            settings=self.settings,
        )
        self.store: GenerationStateStore = store or InMemoryGenerationStore()
        self._graphs: dict[str, Any] = {}

    # ---- public API ------------------------------------------------------
    async def generate(
        self, request: TripPlanningRequest, *, generation_id: str | None = None
    ) -> TripPlanningResult:
        """Run the full pipeline for one trip."""

        run_id = generation_id or f"gen-{uuid.uuid4().hex[:12]}"
        state = initial_state(
            request=request,
            generation_id=run_id,
            max_repair_attempts=self.settings.max_repair_attempts,
        )
        return await self._run(state, entry_point=PREPARE_INPUT, request=request)

    async def revise(
        self,
        previous: TripPlanningResult | PlanningState | None,
        revision: RevisionRequest,
        *,
        request: TripPlanningRequest | None = None,
    ) -> TripPlanningResult:
        """Apply a natural-language change to an existing generation.

        Work already done is reused: preferences are never re-derived, and
        place retrieval only re-runs when the instruction actually calls for
        different places.
        """

        state = self._resolve_previous_state(previous, revision, request)
        entry_point = self._route_revision(revision)
        run_id = f"gen-{uuid.uuid4().hex[:12]}"

        revised: PlanningState = {
            **state,
            "generation_id": run_id,
            "revision_instruction": revision.instruction,
            "revision_target_days": list(revision.target_days),
            # A revision starts with a fresh repair budget and a clean verdict.
            "retry_count": 0,
            "max_repair_attempts": self.settings.max_repair_attempts,
            "validation_result": None,
            "validation_errors": [],
            "validation_warnings": [],
            "status": GenerationStatus.PLANNING,
            "node_traces": [],
            "error": None,
        }

        log_event(
            "generation.revise",
            generationId=run_id,
            previousGenerationId=revision.generation_id,
            entryPoint=entry_point,
            targetDays=revision.target_days,
        )
        return await self._run(
            revised,
            entry_point=entry_point,
            request=state["request"],
            revision_of=revision.generation_id,
            revision_instruction=revision.instruction,
        )

    async def aclose(self) -> None:
        await self.model_router.aclose()

    # ---- internals -------------------------------------------------------
    def _graph(self, entry_point: str) -> Any:
        if entry_point not in self._graphs:
            self._graphs[entry_point] = build_planning_graph(
                self.deps, entry_point=entry_point
            )
        return self._graphs[entry_point]

    async def _run(
        self,
        state: PlanningState,
        *,
        entry_point: str,
        request: TripPlanningRequest,
        revision_of: str | None = None,
        revision_instruction: str | None = None,
    ) -> TripPlanningResult:
        run_id = state["generation_id"]
        metadata = GenerationMetadata(
            generation_id=run_id,
            trip_id=request.trip_id,
            max_repair_attempts=self.settings.max_repair_attempts,
            provider_map=self.model_router.provider_map(),
            revision_of=revision_of,
            revision_instruction=revision_instruction,
        )
        log_event(
            "generation.start",
            generationId=run_id,
            tripId=request.trip_id,
            entryPoint=entry_point,
            participantCount=len(request.participants),
            providerMap=metadata.provider_map,
        )

        try:
            final: PlanningState = await self._graph(entry_point).ainvoke(
                state,
                config={
                    "recursion_limit": graph_recursion_limit(
                        self.settings.max_repair_attempts
                    )
                },
            )
        except NoViableCandidatesError as exc:
            # Not an incident: the group's own constraints leave nothing to
            # plan with. That is a decision for them, not a page for us.
            log_event(
                "generation.needs_input",
                generationId=run_id,
                code=exc.code,
                reason=exc.details.get("reason"),
            )
            return self._needs_input_result(request, metadata, exc)
        except TripTailorAIError as exc:
            log_event("generation.failed", generationId=run_id, code=exc.code, level=40)
            return self._failed_result(request, metadata, exc)
        except Exception as exc:  # noqa: BLE001 - never leak a raw traceback
            log_event(
                "generation.failed",
                generationId=run_id,
                code="UNEXPECTED",
                cause=f"{type(exc).__name__}",
                level=40,
            )
            return self._failed_result(
                request,
                metadata,
                TripTailorAIError(
                    "itinerary generation failed unexpectedly",
                    details={"cause": type(exc).__name__},
                ),
            )

        self.store.save(run_id, final)
        result = self._to_result(final, metadata, request)
        log_event("generation.finish", **state_summary(final))
        return result

    def _to_result(
        self,
        state: PlanningState,
        metadata: GenerationMetadata,
        request: TripPlanningRequest,
    ) -> TripPlanningResult:
        validation: ValidationResult = state.get("validation_result") or ValidationResult()
        traces = state.get("node_traces") or []

        metadata.finished_at = datetime.now(timezone.utc)
        metadata.repair_attempts = state.get("retry_count", 0)
        metadata.total_llm_retries = sum(t.llm_retry_count for t in traces)
        metadata.validation_error_count = validation.error_count
        metadata.validation_warning_count = validation.warning_count
        metadata.candidate_place_count = len(state.get("candidate_places") or [])
        metadata.node_traces = list(traces)

        return TripPlanningResult(
            generation_id=state["generation_id"],
            trip_id=request.trip_id,
            status=state.get("status", GenerationStatus.FAILED),
            itinerary=state.get("itinerary_draft"),
            validation=validation,
            preference_summary=PreferenceSummary(
                common_preferences=state.get("common_preferences") or [],
                hard_constraints=state.get("hard_constraints") or [],
                soft_preferences=state.get("soft_preferences") or [],
                conflicts=state.get("conflicts") or [],
                unresolved_issues=state.get("unresolved_issues") or [],
                repair_changes=state.get("repair_changes") or [],
                summary=state.get("consensus_summary"),
            ),
            candidate_places=state.get("candidate_places") or [],
            normalized_preferences=state.get("normalized_preferences") or [],
unresolved_issues=state.get("unresolved_issues") or [],
            repair_changes=state.get("repair_changes") or [],
            metadata=metadata,
            request=request,
        )

    @staticmethod
    def _needs_input_result(
        request: TripPlanningRequest,
        metadata: GenerationMetadata,
        exc: NoViableCandidatesError,
    ) -> TripPlanningResult:
        """A terminal result the group can act on, rather than an error page."""

        details = exc.details
        issues = [
            "현재 조건으로는 방문 가능한 장소를 찾지 못했습니다.",
        ]
        if details.get("excludedDietaryTags"):
            issues.append(
                "식이 제약으로 제외된 항목: "
                + ", ".join(sorted(details["excludedDietaryTags"]))
            )
        if details.get("excludedAccessibilityTags"):
            issues.append("이동 제약으로 접근성이 낮은 장소를 모두 제외했습니다.")
        if not details.get("retrieved"):
            issues.append(
                f"'{request.region.name}' 지역에서 검색된 장소 자체가 없습니다. "
                "지역 또는 기간을 조정해 주세요."
            )
        else:
            issues.append(
                f"검색된 {details['retrieved']}곳이 모두 하드 제약을 위반했습니다. "
                "제약을 완화하거나 지역을 넓혀 주세요."
            )

        metadata.finished_at = datetime.now(timezone.utc)
        return TripPlanningResult(
            generation_id=metadata.generation_id,
            trip_id=request.trip_id,
            status=GenerationStatus.NEEDS_INPUT,
            itinerary=None,
            metadata=metadata,
            request=request,
            unresolved_issues=issues,
        )

    @staticmethod
    def _failed_result(
        request: TripPlanningRequest,
        metadata: GenerationMetadata,
        exc: TripTailorAIError,
    ) -> TripPlanningResult:
        metadata.finished_at = datetime.now(timezone.utc)
        return TripPlanningResult(
            generation_id=metadata.generation_id,
            trip_id=request.trip_id,
            status=GenerationStatus.FAILED,
            itinerary=None,
            metadata=metadata,
            request=request,
            unresolved_issues=[exc.message],
            error=f"{exc.code}: {exc.message}",
            error_detail=_error_detail(exc),
        )

    def _resolve_previous_state(
        self,
        previous: TripPlanningResult | PlanningState | None,
        revision: RevisionRequest,
        request: TripPlanningRequest | None,
    ) -> PlanningState:
        if isinstance(previous, dict) and "request" in previous:
            return previous
        if isinstance(previous, TripPlanningResult):
            return self._state_from_result(previous, request)

        stored = self.store.load(revision.generation_id)
        if stored is not None:
            return stored
        raise UnknownGenerationError(
            f"generation '{revision.generation_id}' is not available for revision; "
            "pass the previous TripPlanningResult explicitly",
            details={"generationId": revision.generation_id},
        )

    def _state_from_result(
        self, result: TripPlanningResult, request: TripPlanningRequest | None
    ) -> PlanningState:
        """Rebuild graph state from a persisted result.

        This is what makes a stateless backend possible: everything the graph
        needs downstream of the consensus node is carried in the result.
        """

        trip_request = request or result.request
        if trip_request is None:
            raise UnknownGenerationError(
                "cannot revise without the original TripPlanningRequest; pass "
                "request=... or persist TripPlanningResult.request",
                details={"generationId": result.generation_id},
            )

        summary = result.preference_summary
        state = initial_state(
            request=trip_request,
            generation_id=result.generation_id,
            max_repair_attempts=self.settings.max_repair_attempts,
        )
        state.update(
            normalized_preferences=result.normalized_preferences,
            common_preferences=summary.common_preferences,
            hard_constraints=summary.hard_constraints,
            soft_preferences=summary.soft_preferences,
            conflicts=summary.conflicts,
            consensus_summary=summary.summary,
            candidate_places=result.candidate_places,
            itinerary_draft=result.itinerary or Itinerary(),
            unresolved_issues=list(result.unresolved_issues),
            # Deterministic, so recompute rather than trusting the payload.
            group_budget=RetrievalService.derive_group_budget(trip_request),
            retrieval_constraints=RetrievalService.derive_constraints(
                trip_request,
                result.normalized_preferences,
                limit=self.settings.max_candidate_places,
            ),
        )
        return state

    @staticmethod
    def _route_revision(revision: RevisionRequest) -> str:
        """Rule-based routing: re-plan by default, re-search only when asked.

        Deliberately not an LLM decision -- an unpredictable route would make
        latency and cost unpredictable too.
        """

        if revision.force_retrieval:
            return RETRIEVE
        instruction = revision.instruction or ""
        if any(trigger in instruction for trigger in _RETRIEVAL_TRIGGERS):
            return RETRIEVE
        if re.search(r"(다른|새).{0,4}(추천|코스|일정)", instruction):
            return RETRIEVE
        return PLAN


def build_default_service(
    retriever: PlaceRetriever, **kwargs: Any
) -> TripPlanningService:
    """Convenience constructor used by the examples and the FastAPI adapter."""

    return TripPlanningService(retriever, **kwargs)


def _error_detail(exc: TripTailorAIError) -> str | None:
    """Operator-facing cause, for logs and evaluation reports only.

    Carries the exception type and message so a rate limit is
    distinguishable from a dead endpoint. Never rendered to an end user, and
    never carries credentials -- the provider wrapper already strips those.
    """

    cause = exc.details.get("cause")
    return str(cause) if cause else None
