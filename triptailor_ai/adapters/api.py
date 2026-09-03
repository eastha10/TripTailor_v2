"""Standalone FastAPI adapter.

This is a thin translation layer: HTTP in, :class:`TripPlanningService` call,
JSON out.  The core package never imports FastAPI, so the same service can be
called directly in-process by a Python backend.

Run with::

    uvicorn triptailor_ai.adapters.api:app --port 8100
"""

from __future__ import annotations

import os
from pathlib import Path
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import Field

from triptailor_ai.config.settings import Settings, get_settings
from triptailor_ai.exceptions import (
    ConfigurationError,
    ProviderUnavailableError,
    RetrievalError,
    StructuredOutputError,
    TripTailorAIError,
    UnknownGenerationError,
)
from triptailor_ai.retrieval.base import PlaceRetriever
from triptailor_ai.retrieval.json_retriever import JsonPlaceRetriever
from triptailor_ai.schemas.common import AiBaseModel
from triptailor_ai.schemas.generation import RevisionRequest, TripPlanningResult
from triptailor_ai.schemas.trip import TripPlanningRequest
from triptailor_ai.services.planning_service import TripPlanningService

#: Bundled synthetic fixture, used only when PLACES_JSON_PATH is unset.
BUNDLED_PLACES = Path(__file__).resolve().parents[2] / "examples" / "sample_places.json"

_ERROR_STATUS: dict[type[TripTailorAIError], int] = {
    ConfigurationError: 500,
    ProviderUnavailableError: 503,
    StructuredOutputError: 502,
    RetrievalError: 503,
    UnknownGenerationError: 404,
}


class ReviseBody(AiBaseModel):
    """Body for ``POST /ai/v1/itinerary/revise``.

    Pass ``previous`` (the result you persisted) for stateless operation.
    Omit it only when the same process produced the generation.
    """

    revision: RevisionRequest
    previous: TripPlanningResult | None = None
    request: TripPlanningRequest | None = None


class HealthResponse(AiBaseModel):
    status: str = "ok"
    version: str
    default_provider: str
    provider_map: dict[str, str] = Field(default_factory=dict)
    retriever: str
    #: True while the server is serving the bundled demo fixture.
    using_synthetic_places: bool


def build_retriever(settings: Settings) -> tuple[PlaceRetriever, str, bool]:
    """Resolve the retriever for standalone mode.

    A production deployment injects its own retriever via
    :func:`create_app`; the JSON file is a demo convenience.
    """

    if settings.places_json_path:
        path = Path(settings.places_json_path)
        return JsonPlaceRetriever(path), f"JsonPlaceRetriever({path})", False
    return (
        JsonPlaceRetriever(BUNDLED_PLACES),
        f"JsonPlaceRetriever({BUNDLED_PLACES.name}, SYNTHETIC DEMO DATA)",
        True,
    )


def create_app(
    *,
    service: TripPlanningService | None = None,
    settings: Settings | None = None,
) -> FastAPI:
    resolved = settings or get_settings()
    retriever_label = "injected"
    synthetic = False

    if service is None:
        retriever, retriever_label, synthetic = build_retriever(resolved)
        service = TripPlanningService(retriever, settings=resolved)

    app = FastAPI(
        title="TripTailor AI",
        version=_package_version(),
        description=(
            "Group Preference & Itinerary Orchestrator. "
            "Standalone adapter around TripPlanningService."
        ),
    )
    app.state.service = service
    app.state.settings = resolved

    @app.exception_handler(TripTailorAIError)
    async def _handle_domain_error(_: Request, exc: TripTailorAIError) -> JSONResponse:
        status = next(
            (code for kind, code in _ERROR_STATUS.items() if isinstance(exc, kind)), 500
        )
        return JSONResponse(status_code=status, content={"error": exc.to_dict()})

    @app.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(
            version=_package_version(),
            default_provider=resolved.default_llm_provider.value,
            # From settings, not from live clients: a health check must not
            # fail merely because a credential is missing.
            provider_map=resolved.provider_map(),
            retriever=retriever_label,
            using_synthetic_places=synthetic,
        )

    @app.post("/ai/v1/itinerary/generate", response_model=TripPlanningResult)
    async def generate(payload: TripPlanningRequest) -> TripPlanningResult:
        return await service.generate(payload)

    @app.post("/ai/v1/itinerary/revise", response_model=TripPlanningResult)
    async def revise(payload: ReviseBody) -> TripPlanningResult:
        return await service.revise(
            payload.previous, payload.revision, request=payload.request
        )

    return app


def _package_version() -> str:
    try:
        from importlib.metadata import version

        return version("triptailor-ai")
    except Exception:  # noqa: BLE001 - running from a source checkout
        return "0.1.0"


#: Module-level ASGI app for ``uvicorn triptailor_ai.adapters.api:app``.
app = create_app()


def main() -> None:
    """Console-script entry point (``triptailor-ai-serve``)."""

    import uvicorn

    uvicorn.run(
        "triptailor_ai.adapters.api:app",
        host=os.getenv("AI_HOST", "0.0.0.0"),
        port=int(os.getenv("AI_PORT", "8100")),
        reload=os.getenv("AI_RELOAD", "false").lower() == "true",
    )
