"""Error hierarchy.

Raw provider exceptions (``openai.APIError``, httpx errors, ...) are never
propagated to callers.  They are wrapped so that the backend can map a small,
stable set of error types onto HTTP responses.
"""

from __future__ import annotations


class TripTailorAIError(Exception):
    """Base class for every error this package raises deliberately."""

    #: Stable machine-readable code, surfaced to the backend.
    code: str = "TRIPTAILOR_AI_ERROR"

    def __init__(self, message: str, *, details: dict[str, object] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}

    def to_dict(self) -> dict[str, object]:
        return {"code": self.code, "message": self.message, "details": self.details}


class ConfigurationError(TripTailorAIError):
    """Settings are missing or internally inconsistent (e.g. no API key)."""

    code = "CONFIGURATION_ERROR"


class ProviderUnavailableError(TripTailorAIError):
    """An LLM provider could not be reached or refused the request.

    The original exception is summarised in ``details['cause']`` -- never the
    raw object, and never anything containing credentials.
    """

    code = "PROVIDER_UNAVAILABLE"


class StructuredOutputError(TripTailorAIError):
    """The model failed to produce schema-valid output within the retry budget."""

    code = "STRUCTURED_OUTPUT_ERROR"


class RetrievalError(TripTailorAIError):
    """The place retriever failed or returned nothing usable."""

    code = "RETRIEVAL_ERROR"


class NoViableCandidatesError(RetrievalError):
    """The search worked, but nothing survives the group's hard constraints.

    Kept distinct from a plain :class:`RetrievalError` because the two need
    opposite responses: a broken retriever is an incident, while "your
    allergy rules out every restaurant we found" is a decision the group has
    to make. The first becomes ``FAILED``; this one becomes ``NEEDS_INPUT``.
    """

    code = "NO_VIABLE_CANDIDATES"


class PlanningError(TripTailorAIError):
    """The planner could not produce a usable draft."""

    code = "PLANNING_ERROR"


class ValidationError(TripTailorAIError):
    """Raised only for *internal* validator misuse.

    Plan-level rule violations are data (``ValidationResult``), not exceptions.
    """

    code = "VALIDATION_ERROR"


class RepairLimitExceeded(TripTailorAIError):
    """The repair loop hit ``MAX_REPAIR_ATTEMPTS`` without reaching a valid plan."""

    code = "REPAIR_LIMIT_EXCEEDED"


class UnknownGenerationError(TripTailorAIError):
    """``revise()`` was called with a generation this process does not hold."""

    code = "UNKNOWN_GENERATION"
