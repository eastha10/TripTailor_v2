"""Run the scenario suite against one or more provider configurations.

Same scenarios, same retriever, same validator -- only the model wiring
changes.  That is what makes an OpenAI vs. Qwen vs. hybrid comparison mean
something.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Callable, Iterable

from pydantic import Field

from triptailor_ai.config.settings import Settings
from triptailor_ai.evaluation.metrics import (
    AggregateMetrics,
    ScenarioMetrics,
    aggregate,
    score_result,
)
from triptailor_ai.evaluation.scenarios import (
    CORE_SCENARIO_IDS,
    EvaluationScenario,
    build_scenarios,
    select_scenarios,
)
from triptailor_ai.retrieval.in_memory import InMemoryPlaceRetriever
from triptailor_ai.schemas.common import AiBaseModel
from triptailor_ai.schemas.generation import GenerationStatus, TripPlanningResult
from triptailor_ai.services.planning_service import TripPlanningService

#: Builds a service for one scenario. Receives the scenario's synthetic places.
ServiceFactory = Callable[[EvaluationScenario], TripPlanningService]


class EvaluationReport(AiBaseModel):
    label: str
    aggregate: AggregateMetrics
    scenarios: list[ScenarioMetrics] = Field(default_factory=list)

    def to_json(self, indent: int = 2) -> str:
        return self.model_dump_json(by_alias=True, indent=indent)

    def write(self, path: str | Path) -> Path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(self.to_json(), encoding="utf-8")
        return target


def default_service_factory(settings: Settings) -> ServiceFactory:
    """Service factory that uses each scenario's own synthetic place set."""

    def factory(scenario: EvaluationScenario) -> TripPlanningService:
        return TripPlanningService(
            InMemoryPlaceRetriever(scenario.places), settings=settings
        )

    return factory


async def run_scenario(
    scenario: EvaluationScenario, service: TripPlanningService
) -> tuple[TripPlanningResult, ScenarioMetrics]:
    result = await service.generate(scenario.request)
    metrics = score_result(
        result,
        scenario_id=scenario.scenario_id,
        expects_conflict=scenario.expectations.expects_conflict,
    )
    failures = check_expectations(scenario, result)
    metrics.expectation_failures = failures
    metrics.expectations_met = not failures
    return result, metrics


def check_expectations(
    scenario: EvaluationScenario, result: TripPlanningResult
) -> list[str]:
    """Assert the *product* requirements, not merely schema validity."""

    expectations = scenario.expectations
    failures: list[str] = []

    if result.status not in expectations.allowed_statuses:
        allowed = ", ".join(s.value for s in expectations.allowed_statuses)
        failures.append(f"status={result.status.value}, expected one of [{allowed}]")

    conflicts = result.preference_summary.conflicts
    if expectations.expects_conflict and not conflicts:
        failures.append("expected at least one surfaced conflict, found none")

    scheduled = {item.place_id for item in (result.itinerary.all_items() if result.itinerary else [])}
    forbidden = scheduled & set(expectations.forbidden_place_ids)
    if forbidden:
        failures.append(f"hard-constraint places were scheduled: {sorted(forbidden)}")

    if expectations.expects_unresolved_issue and not result.unresolved_issues:
        failures.append("expected an unresolved issue to be reported, found none")

    # Grounding is non-negotiable in every scenario.
    candidate_ids = {place.place_id for place in result.candidate_places}
    ungrounded = scheduled - candidate_ids
    if ungrounded:
        failures.append(f"ungrounded placeIds in plan: {sorted(ungrounded)}")

    return failures


async def run_suite(
    *,
    label: str,
    service_factory: ServiceFactory,
    scenarios: Iterable[EvaluationScenario] | None = None,
    provider_map: dict[str, str] | None = None,
    progress: Callable[[int, int, ScenarioMetrics], None] | None = None,
    partial_path: str | Path | None = None,
) -> EvaluationReport:
    """Run the suite, reporting as it goes.

    A local 7B model takes hours over 40 scenarios. Writing nothing until the
    end means a run that stalls, is interrupted, or is simply slow yields
    nothing at all -- and cannot be checked while it is going. So each scenario
    is reported through ``progress`` and, if ``partial_path`` is set, the
    report so far is rewritten after every scenario.
    """

    suite = list(scenarios if scenarios is not None else build_scenarios())
    metrics: list[ScenarioMetrics] = []

    for index, scenario in enumerate(suite, start=1):
        service = service_factory(scenario)
        try:
            _, scenario_metrics = await run_scenario(scenario, service)
        finally:
            await service.aclose()
        metrics.append(scenario_metrics)

        # Persist before notifying, so a progress handler (or anything the
        # operator runs on seeing the line) can read the file it describes.
        if partial_path is not None:
            EvaluationReport(
                label=label,
                aggregate=aggregate(label, metrics, provider_map=provider_map),
                scenarios=metrics,
            ).write(partial_path)
        if progress is not None:
            progress(index, len(suite), scenario_metrics)

    return EvaluationReport(
        label=label,
        aggregate=aggregate(label, metrics, provider_map=provider_map),
        scenarios=metrics,
    )


def _scenarios_from_env() -> list[EvaluationScenario] | None:
    """Scenario selection from the environment.

        EVAL_SCENARIOS=core          the representative ten
        EVAL_SCENARIOS=s04,s26       exactly these
        EVAL_SCENARIOS=10            the first ten
        (unset)                      all forty
    """

    import os

    raw = (os.getenv("EVAL_SCENARIOS") or "").strip()
    if not raw:
        return None
    if raw.lower() == "core":
        return select_scenarios(ids=CORE_SCENARIO_IDS)
    if raw.isdigit():
        return select_scenarios(limit=int(raw))
    return select_scenarios(ids=[part.strip() for part in raw.split(",") if part.strip()])


def _print_progress(index: int, total: int, metrics: ScenarioMetrics) -> None:
    """One line per scenario, flushed immediately.

    A multi-hour run must be observable while it runs, not only afterwards.
    """

    import sys

    mark = "ok  " if metrics.expectations_met else "FAIL"
    detail = "" if metrics.expectations_met else f"  {'; '.join(metrics.expectation_failures)[:70]}"
    print(
        f"  [{index:>2}/{total}] {metrics.scenario_id:<4} {mark} "
        f"{metrics.status.value:<12} repairs={metrics.repair_count}{detail}",
        file=sys.stderr,
        flush=True,
    )


def main() -> int:
    """CLI: ``python -m triptailor_ai.evaluation.runner [output.json]``.

    Uses whatever provider configuration the environment specifies, so::

        DEFAULT_LLM_PROVIDER=fake   python -m triptailor_ai.evaluation.runner
        DEFAULT_LLM_PROVIDER=openai python -m triptailor_ai.evaluation.runner openai.json
    """

    import sys

    settings = Settings()
    label = settings.default_llm_provider.value
    chosen = _scenarios_from_env()
    report = asyncio.run(
        run_suite(
            label=label,
            service_factory=default_service_factory(settings),
            scenarios=chosen,
            provider_map=settings.provider_map(),
            progress=_print_progress,
            partial_path=(f"{sys.argv[1]}.partial" if len(sys.argv) > 1 else None),
        )
    )

    summary = report.aggregate
    print(json.dumps(summary.model_dump(by_alias=True), ensure_ascii=False, indent=2))
    for scenario in report.scenarios:
        if not scenario.expectations_met:
            print(f"  FAIL {scenario.scenario_id}: {'; '.join(scenario.expectation_failures)}")

    # A FAILED scenario never produced a plan at all -- usually the provider,
    # not the system. Report it separately from an expectation miss, and print
    # the cause: "3 scenarios FAILED" with no reason is not diagnosable.
    failed = [m for m in report.scenarios if m.status is GenerationStatus.FAILED]
    if failed:
        print(f"\n{len(failed)}개 시나리오가 계획을 생성하지 못했습니다 (provider/system 오류):")
        for scenario in failed:
            print(f"  {scenario.scenario_id}: {scenario.error or '(원인 미기록)'}")
        print(
            "  이 실패는 모델 품질이 아니라 실행 환경 문제일 수 있습니다. "
            "단독 재실행으로 확인하세요."
        )

    if len(sys.argv) > 1:
        print(f"\nwrote {report.write(sys.argv[1])}")

    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
