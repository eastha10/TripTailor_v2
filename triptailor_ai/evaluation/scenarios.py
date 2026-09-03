"""Synthetic evaluation scenarios.

**All place data and all participant answers here are invented.**  They exist
to exercise specific failure modes, not to describe real trips or real
businesses.

The suite is deliberately adversarial: half of these scenarios *should* end in
``NEEDS_INPUT`` or surface a conflict.  A configuration that quietly returns a
pretty plan for scenario 4 (allergy vs. seafood) is worse than one that stops
and says it cannot.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any, Iterable

from pydantic import Field

from triptailor_ai.retrieval.json_retriever import load_places
from triptailor_ai.schemas.common import AiBaseModel, Weekday
from triptailor_ai.schemas.generation import GenerationStatus
from triptailor_ai.schemas.place import PlaceCandidate
from triptailor_ai.schemas.trip import TripPlanningRequest

BUNDLED_PLACES = Path(__file__).resolve().parents[2] / "examples" / "sample_places.json"

START = date(2026, 9, 12)  # Saturday
END = date(2026, 9, 14)  # Monday


class ScenarioExpectations(AiBaseModel):
    """What a *correct* system should do -- not what any given model does."""

    #: Statuses that count as an acceptable outcome.
    allowed_statuses: list[GenerationStatus] = Field(
        default_factory=lambda: [GenerationStatus.NEEDS_REVIEW]
    )
    #: A conflict must (or must not) be surfaced to the reviewer.
    expects_conflict: bool = False
    #: These places must never appear in the plan.
    forbidden_place_ids: list[str] = Field(default_factory=list)
    #: At least one unresolved issue must be reported.
    expects_unresolved_issue: bool = False


class EvaluationScenario(AiBaseModel):
    scenario_id: str
    title: str
    rationale: str
    request: TripPlanningRequest
    places: list[PlaceCandidate]
    expectations: ScenarioExpectations = Field(default_factory=ScenarioExpectations)


def _participant(
    pid: str,
    *,
    budget: str = "FROM_200000_TO_400000_KRW",
    accommodation: str = "NO_PREFERENCE",
    dates: str = "전 일정 참여 가능",
    must: str | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    return {
        "participantId": pid,
        "displayName": f"참여자 {pid}",
        "availableDateText": dates,
        "budgetBand": budget,
        "accommodationType": accommodation,
        "mustHaves": must,
        "additionalNotes": notes,
    }


def _request(scenario_id: str, participants: list[dict[str, Any]], **overrides) -> TripPlanningRequest:
    payload = {
        "tripId": f"trip-eval-{scenario_id}",
        "region": {"regionId": "jeju", "name": "제주"},
        "travelPeriod": {"startDate": START.isoformat(), "endDate": END.isoformat()},
        "participantLimit": len(participants),
        "participants": participants,
    }
    payload.update(overrides)
    return TripPlanningRequest.model_validate(payload)


def _places(*, exclude: tuple[str, ...] = (), only: tuple[str, ...] | None = None) -> list[PlaceCandidate]:
    all_places = load_places(BUNDLED_PLACES)
    if only is not None:
        return [p for p in all_places if p.place_id in only]
    return [p for p in all_places if p.place_id not in exclude]


def _strip_opening_hours(places: list[PlaceCandidate]) -> list[PlaceCandidate]:
    return [p.model_copy(update={"opening_hours": None, "closed_days": []}) for p in places]


def _without_food(places: list[PlaceCandidate]) -> list[PlaceCandidate]:
    """Drop everywhere you could eat, so meal coverage becomes impossible."""

    markers = {"restaurant", "food", "cafe", "맛집", "식당", "카페", "시장"}
    return [
        p
        for p in places
        if not ({c.lower() for c in (*p.categories, *p.tags)} & markers)
    ]


def _free_only(places: list[PlaceCandidate]) -> list[PlaceCandidate]:
    return [p for p in places if not p.estimated_cost_per_person]


def _closed_on(places: list[PlaceCandidate], weekday: Weekday) -> list[PlaceCandidate]:
    return [p.model_copy(update={"closed_days": [weekday]}) for p in places]


def _half_missing_hours(places: list[PlaceCandidate]) -> list[PlaceCandidate]:
    """Half the candidates have opening hours, half do not."""

    return [
        p if index % 2 == 0 else p.model_copy(update={"opening_hours": None})
        for index, p in enumerate(places)
    ]


def build_scenarios() -> list[EvaluationScenario]:
    """The 20-scenario evaluation suite."""

    scenarios: list[EvaluationScenario] = []

    def add(
        scenario_id: str,
        title: str,
        rationale: str,
        participants: list[dict[str, Any]],
        places: list[PlaceCandidate],
        expectations: ScenarioExpectations | None = None,
        **request_overrides,
    ) -> None:
        scenarios.append(
            EvaluationScenario(
                scenario_id=scenario_id,
                title=title,
                rationale=rationale,
                request=_request(scenario_id, participants, **request_overrides),
                places=places,
                expectations=expectations or ScenarioExpectations(),
            )
        )

    # 1 -- baseline: everyone wants the same thing.
    add(
        "s01",
        "선호가 거의 일치하는 그룹",
        "충돌이 없을 때 불필요한 conflict를 만들어내지 않는지 확인한다.",
        [
            _participant("p1", must="바다 보이는 곳", notes="조용한 카페가 좋아요"),
            _participant("p2", must="바다 보이는 곳", notes="조용한 분위기 선호합니다"),
        ],
        _places(),
        ScenarioExpectations(expects_conflict=False),
    )

    # 2 -- cheap budget vs. expensive must-have.
    add(
        "s02",
        "낮은 예산과 비싼 필수 항목 충돌",
        "예산 상한이 가장 낮은 참여자를 기준으로 계획하고 충돌을 드러내야 한다.",
        [
            _participant("p1", budget="UP_TO_200000_KRW", notes="가성비 위주로 다니고 싶어요"),
            _participant("p2", budget="FROM_400000_TO_600000_KRW", must="고급 맛집은 꼭 가야 해요"),
        ],
        _places(),
        ScenarioExpectations(expects_conflict=True, expects_unresolved_issue=True),
    )

    # 3 -- participants available on different dates.
    add(
        "s03",
        "참여 가능 날짜 충돌",
        "참여 날짜는 HARD 제약이므로 반드시 미해결 이슈로 보고되어야 한다.",
        [
            _participant("p1", dates="12일과 13일만 가능합니다"),
            _participant("p2", dates="14일에만 참여 가능해요"),
        ],
        _places(),
        ScenarioExpectations(expects_unresolved_issue=True),
    )

    # 4 -- allergy vs. seafood preference. The allergy must win.
    add(
        "s04",
        "알레르기와 음식 선호 충돌",
        "명시적 알레르기는 HARD이므로 해당 장소가 절대 배치되면 안 된다.",
        [
            _participant("p1", notes="갑각류 알레르기가 있어서 해산물은 먹을 수 없어요"),
            _participant("p2", must="해산물 맛집은 꼭 가고 싶어요"),
        ],
        _places(),
        ScenarioExpectations(
            expects_conflict=True,
            forbidden_place_ids=["jeju-005", "jeju-010"],
        ),
    )

    # 5 -- mobility limit vs. hiking wish.
    add(
        "s05",
        "보행 제약과 등산 선호 충돌",
        "보행 HARD 제약이 있으면 등산/계단 장소는 후보 단계에서 제거되어야 한다.",
        [
            _participant("p1", notes="무릎 때문에 오래 걷는 건 불가능해요"),
            _participant("p2", must="한라산 등산은 꼭 하고 싶어요"),
        ],
        _places(),
        ScenarioExpectations(
            expects_conflict=True,
            forbidden_place_ids=["jeju-001", "jeju-009", "jeju-002"],
        ),
    )

    # 6 -- barely any candidate data.
    add(
        "s06",
        "장소 데이터 부족",
        "후보가 3곳뿐일 때 없는 장소를 지어내지 않고 부족함을 보고해야 한다.",
        [_participant("p1", notes="아무거나 좋아요"), _participant("p2")],
        _places(only=("jeju-007", "jeju-013", "jeju-016")),
        # Three places for a three-day trip cannot yield a complete itinerary.
        # Reporting that honestly (NEEDS_INPUT) is a correct outcome here --
        # arguably more correct than shipping a plan with no dinners.
        ScenarioExpectations(
            allowed_statuses=[
                GenerationStatus.NEEDS_REVIEW,
                GenerationStatus.NEEDS_INPUT,
            ],
            expects_unresolved_issue=True,
        ),
    )

    # 7 -- everything closed on the middle day.
    add(
        "s07",
        "휴무일 충돌",
        "일요일 휴무 장소만 남았을 때 휴무일 배치를 잡아내야 한다.",
        [_participant("p1", notes="박물관 같은 실내가 좋아요")],
        [
            p.model_copy(update={"closed_days": [Weekday.SUN]})
            for p in _places(only=("jeju-006", "jeju-011", "jeju-013", "jeju-015"))
        ],
        ScenarioExpectations(
            allowed_statuses=[GenerationStatus.NEEDS_REVIEW, GenerationStatus.NEEDS_INPUT]
        ),
    )

    # 8 -- night-only venue scheduled during the day.
    add(
        "s08",
        "영업시간 위반 유도",
        "야간 전용 장소를 낮에 배치하면 OUTSIDE_OPENING_HOURS로 걸려야 한다.",
        [_participant("p1", notes="야경 보는 걸 좋아해요")],
        _places(only=("jeju-014", "jeju-013", "jeju-016", "jeju-007")),
        ScenarioExpectations(
            allowed_statuses=[GenerationStatus.NEEDS_REVIEW, GenerationStatus.NEEDS_INPUT]
        ),
    )

    # 9 -- long transfers between far-apart places.
    add(
        "s09",
        "장거리 이동",
        "이동시간 제공자가 없으면 TRAVEL_TIME_UNVERIFIED 경고가 남아야 한다.",
        [_participant("p1", must="섬 동쪽과 서쪽 모두 가보고 싶어요")],
        _places(only=("jeju-005", "jeju-007", "jeju-015", "jeju-012", "jeju-013")),
        ScenarioExpectations(expects_unresolved_issue=True),
    )

    # 10 -- vague free text.
    add(
        "s10",
        "모호한 자유 텍스트",
        "모호한 문장을 HARD 제약으로 과잉 해석하면 안 된다.",
        [
            _participant("p1", notes="그냥 편하게 다니면 좋겠어요"),
            _participant("p2", notes="음... 잘 모르겠어요"),
        ],
        _places(),
        ScenarioExpectations(),
    )

    # 11 -- directly opposed activity preferences.
    add(
        "s11",
        "정반대 활동 선호",
        "활동적/휴식 선호가 정반대일 때 한쪽을 임의로 버리지 않아야 한다.",
        [
            _participant("p1", notes="액티비티 위주로 빡빡하게 다니고 싶어요"),
            _participant("p2", notes="조용히 쉬엄쉬엄 여유롭게 다니고 싶어요"),
        ],
        _places(),
        ScenarioExpectations(expects_conflict=True),
    )

    # 12 -- no free text at all.
    add(
        "s12",
        "자유 응답이 비어 있음",
        "구조화 필드만 있을 때도 실패하지 않고 계획해야 한다.",
        [
            {"participantId": "p1", "budgetBand": "UP_TO_200000_KRW"},
            {"participantId": "p2", "accommodationType": "HOTEL"},
        ],
        _places(),
        ScenarioExpectations(expects_unresolved_issue=True),
    )

    # 13 -- single participant, single day.
    add(
        "s13",
        "1인 당일 여행",
        "최소 규모 입력에서도 그래프가 정상 종료되어야 한다.",
        [_participant("p1", notes="카페 투어 하고 싶어요")],
        _places(),
        ScenarioExpectations(),
        travelPeriod={"startDate": START.isoformat(), "endDate": START.isoformat()},
    )

    # 14 -- larger group, many competing wishes.
    add(
        "s14",
        "5인 대규모 그룹",
        "참여자가 늘어도 공통 선호를 뽑아내고 충돌을 정리해야 한다.",
        [
            _participant("p1", notes="자연 위주로"),
            _participant("p2", notes="맛집 위주로"),
            _participant("p3", notes="카페 위주로", budget="UP_TO_200000_KRW"),
            _participant("p4", notes="박물관 같은 실내가 좋아요"),
            _participant("p5", notes="사진 찍기 좋은 곳", budget="FROM_400000_TO_600000_KRW"),
        ],
        _places(),
        ScenarioExpectations(expects_conflict=True),
    )

    # 15 -- no opening-hours data anywhere.
    add(
        "s15",
        "영업시간 데이터 전무",
        "데이터가 없으면 PASS가 아니라 UNVERIFIED로 남겨야 한다.",
        [_participant("p1", notes="맛집 위주로 다니고 싶어요")],
        _strip_opening_hours(_places()),
        ScenarioExpectations(expects_unresolved_issue=True),
    )

    # 16 -- vegetarian hard constraint.
    add(
        "s16",
        "채식 HARD 제약",
        "채식 제약이 있으면 육류/해산물 태그 장소가 배치되면 안 된다.",
        [_participant("p1", notes="비건이라 고기와 해산물은 먹을 수 없어요")],
        _places(),
        ScenarioExpectations(forbidden_place_ids=["jeju-004", "jeju-005", "jeju-010"]),
    )

    # 17 -- one must-have that is not in the candidate set at all.
    add(
        "s17",
        "후보에 없는 필수 장소",
        "요청한 장소가 후보에 없으면 지어내지 말고 미반영으로 남겨야 한다.",
        [_participant("p1", must="우도 등대는 꼭 가야 해요")],
        _places(exclude=("jeju-001", "jeju-017")),
        ScenarioExpectations(expects_unresolved_issue=True),
    )

    # 18 -- long trip, thin candidate pool.
    add(
        "s18",
        "긴 일정 대비 부족한 후보",
        "일수 대비 후보가 모자라면 같은 장소를 중복 배치하지 말아야 한다.",
        [_participant("p1", notes="여유롭게 다니고 싶어요")],
        _places(only=("jeju-007", "jeju-013", "jeju-016", "jeju-012")),
        ScenarioExpectations(
            allowed_statuses=[GenerationStatus.NEEDS_REVIEW, GenerationStatus.NEEDS_INPUT]
        ),
        travelPeriod={"startDate": START.isoformat(), "endDate": "2026-09-17"},
    )

    # 19 -- everyone on the lowest budget band.
    add(
        "s19",
        "전원 최저 예산",
        "예산 밴드가 같으면 충돌로 보고하지 않아야 한다.",
        [
            _participant("p1", budget="UP_TO_200000_KRW", notes="저렴하게 다니고 싶어요"),
            _participant("p2", budget="UP_TO_200000_KRW", notes="가성비 좋은 곳 위주로"),
        ],
        _places(),
        ScenarioExpectations(expects_conflict=False),
    )

    # 20 -- accommodation preferences all different.
    add(
        "s20",
        "숙소 취향이 모두 다름",
        "숙소 선호는 SOFT이므로 일정 생성을 실패시키면 안 된다.",
        [
            _participant("p1", accommodation="HOTEL"),
            _participant("p2", accommodation="GUESTHOUSE"),
            _participant("p3", accommodation="RESORT_OR_POOL_VILLA"),
        ],
        _places(),
        ScenarioExpectations(),
    )

    # ---------------------------------------------------------------
    # 21-40: added after real-model runs exposed failure modes the first
    # twenty did not reach. Several of these exist specifically to check
    # that a *conditional* escalation stays a warning when the candidate
    # data cannot support a fix.
    # ---------------------------------------------------------------

    add(
        "s21",
        "식사 가능한 후보가 전무",
        "식사 장소가 없으면 식사 누락을 ERROR로 올리면 안 된다(고칠 수 없음).",
        [_participant("p1", notes="자연 위주로 다니고 싶어요")],
        _without_food(_places()),
        ScenarioExpectations(expects_unresolved_issue=True),
    )

    add(
        "s22",
        "후보 수 = 일자 수",
        "후보가 빠듯하면 중복을 ERROR로 올려 무의미한 수정 루프를 돌리면 안 된다.",
        [_participant("p1")],
        _places(only=("jeju-007", "jeju-013", "jeju-016")),
        ScenarioExpectations(
            allowed_statuses=[
                GenerationStatus.NEEDS_REVIEW,
                GenerationStatus.NEEDS_INPUT,
            ]
        ),
    )

    add(
        "s23",
        "모든 장소가 토요일 휴무",
        "여행 첫날(토)에 아무데도 열지 않으면 정직하게 보고해야 한다.",
        [_participant("p1", notes="관광지 위주로")],
        _closed_on(_places(), Weekday.SAT),
        ScenarioExpectations(
            allowed_statuses=[
                GenerationStatus.NEEDS_REVIEW,
                GenerationStatus.NEEDS_INPUT,
            ],
            expects_unresolved_issue=True,
        ),
    )

    add(
        "s24",
        "무료 장소만 존재",
        "비용 정보가 0인 후보만 있어도 예산 검증이 정상 동작해야 한다.",
        [_participant("p1", budget="UP_TO_200000_KRW", notes="돈을 아끼고 싶어요")],
        _free_only(_places()),
        ScenarioExpectations(expects_unresolved_issue=True),
    )

    add(
        "s25",
        "복합 알레르기",
        "여러 하드 식이 제약이 동시에 걸려도 모두 적용되어야 한다.",
        [
            _participant(
                "p1",
                notes="땅콩 알레르기가 있고 해산물과 유제품도 먹을 수 없어요",
            ),
            _participant("p2", must="맛집 투어 하고 싶어요"),
        ],
        _places(),
        ScenarioExpectations(
            forbidden_place_ids=["jeju-005", "jeju-010", "jeju-003", "jeju-008"]
        ),
    )

    add(
        "s26",
        "휠체어 사용자",
        "휠체어는 명시적 물리 제약이므로 반드시 HARD로 처리되어야 한다.",
        [
            _participant("p1", notes="휠체어를 사용해서 계단이나 등산로는 갈 수 없어요"),
            _participant("p2", must="오름에 올라가 보고 싶어요"),
        ],
        _places(),
        ScenarioExpectations(
            expects_conflict=True,
            forbidden_place_ids=["jeju-001", "jeju-002", "jeju-009"],
        ),
    )

    add(
        "s27",
        "5인 전원 다른 필수 장소",
        "필수 희망이 5개로 갈릴 때 임의로 버리지 말고 미반영을 보고해야 한다.",
        [
            _participant("p1", must="성산일출봉은 꼭"),
            _participant("p2", must="한라산 등산은 꼭"),
            _participant("p3", must="박물관은 꼭"),
            _participant("p4", must="해변은 꼭"),
            _participant("p5", must="시장 구경은 꼭"),
        ],
        _places(),
        ScenarioExpectations(expects_unresolved_issue=True),
    )

    add(
        "s28",
        "매우 긴 자유 텍스트",
        "장문에서도 원문 그대로의 sourceText를 유지해야 한다.",
        [
            _participant(
                "p1",
                notes=(
                    "저는 사실 여행을 정말 좋아하는데요, 특히 바다를 보는 걸 좋아합니다. "
                    "아침에는 조금 늦게 일어나는 편이라 오전 일정은 여유로웠으면 좋겠고, "
                    "점심은 현지 음식으로 먹고 싶어요. 다만 매운 음식은 잘 못 먹습니다. "
                    "오후에는 카페에서 좀 쉬다가 저녁에 야경을 보면 완벽할 것 같아요. "
                    "숙소는 깨끗하기만 하면 상관없습니다. 예산은 너무 빡빡하지 않았으면 해요."
                ),
            )
        ],
        _places(),
        ScenarioExpectations(),
    )

    add(
        "s29",
        "한영 혼용 입력",
        "혼용 표기에서도 정규화가 깨지지 않아야 한다.",
        [
            _participant("p1", notes="I prefer quiet cafe, 사진 찍기 좋은 곳이면 좋겠어요"),
            _participant("p2", must="local food 맛집 필수입니다"),
        ],
        _places(),
        ScenarioExpectations(),
    )

    add(
        "s30",
        "1명만 응답, 나머지 공백",
        "응답이 없는 참여자를 지어내지 말고 부족함을 보고해야 한다.",
        [
            _participant("p1", notes="자연 위주로 다니고 싶어요"),
            {"participantId": "p2"},
            {"participantId": "p3"},
        ],
        _places(),
        ScenarioExpectations(expects_unresolved_issue=True),
    )

    add(
        "s31",
        "필수 장소가 휴무일에만 열림",
        "휴무 충돌은 수정으로 풀리거나, 안 되면 정직하게 보고되어야 한다.",
        [_participant("p1", must="바다뷰 카페 한담은 꼭 가고 싶어요")],
        [
            p.model_copy(update={"closed_days": [Weekday.SAT, Weekday.SUN, Weekday.MON]})
            if p.place_id == "jeju-003"
            else p
            for p in _places()
        ],
        ScenarioExpectations(
            forbidden_place_ids=["jeju-003"], expects_unresolved_issue=True
        ),
    )

    add(
        "s32",
        "4박 5일 장기 일정",
        "일정이 길어져도 모든 날이 채워지고 장소가 중복되면 안 된다.",
        [
            _participant("p1", notes="자연과 맛집을 골고루"),
            _participant("p2", notes="카페와 사진 찍기 좋은 곳"),
        ],
        _places(),
        ScenarioExpectations(
            allowed_statuses=[
                GenerationStatus.NEEDS_REVIEW,
                GenerationStatus.NEEDS_INPUT,
            ]
        ),
        travelPeriod={"startDate": START.isoformat(), "endDate": "2026-09-16"},
    )

    add(
        "s33",
        "예산 밴드 3단계 모두 존재",
        "가장 낮은 상한이 그룹 상한이 되어야 하고 충돌로 보고되어야 한다.",
        [
            _participant("p1", budget="UP_TO_200000_KRW"),
            _participant("p2", budget="FROM_200000_TO_400000_KRW"),
            _participant("p3", budget="FROM_400000_TO_600000_KRW"),
        ],
        _places(),
        ScenarioExpectations(expects_conflict=True, expects_unresolved_issue=True),
    )

    add(
        "s34",
        "부정 표현만 있는 응답",
        "'싫다'만 있는 입력에서 긍정 선호를 지어내면 안 된다.",
        [
            _participant("p1", notes="시끄러운 곳은 싫고 사람 많은 데도 별로예요"),
            _participant("p2", notes="등산은 싫어요. 비싼 곳도 피하고 싶어요"),
        ],
        _places(),
        ScenarioExpectations(),
    )

    add(
        "s35",
        "시간대 제약 명시",
        "'아침 일찍은 불가' 같은 시간 제약을 반영하거나 미반영으로 보고해야 한다.",
        [
            _participant("p1", notes="아침 일찍은 못 일어나요. 10시 이후에 시작했으면 좋겠어요"),
            _participant("p2", notes="저녁 늦게까지 다니는 건 힘들어요"),
        ],
        _places(),
        ScenarioExpectations(),
    )

    add(
        "s36",
        "영업시간 정보가 절반만 존재",
        "일부만 아는 상태에서 아는 것은 검사하고 모르는 것은 UNVERIFIED로 남겨야 한다.",
        [_participant("p1", notes="관광지와 맛집을 골고루")],
        _half_missing_hours(_places()),
        ScenarioExpectations(expects_unresolved_issue=True),
    )

    add(
        "s37",
        "체력 약한 동행자 + 빡빡한 선호",
        "체력 제약과 밀도 높은 일정 희망이 함께 있을 때 충돌을 드러내야 한다.",
        [
            _participant("p1", notes="체력이 약해서 하루 두세 곳이면 충분해요"),
            _participant("p2", notes="하루에 최대한 많은 곳을 보고 싶어요"),
        ],
        _places(),
        ScenarioExpectations(expects_conflict=True),
    )

    add(
        "s38",
        "두 사람이 같은 필수 장소",
        "동일 희망은 충돌이 아니라 공통 선호로 잡혀야 한다.",
        [
            _participant("p1", must="성산일출봉은 꼭 보고 싶어요"),
            _participant("p2", must="성산일출봉은 꼭 보고 싶어요"),
        ],
        _places(),
        ScenarioExpectations(expects_conflict=False),
    )

    add(
        "s39",
        "정반대 pace",
        "하루 10곳 vs 2곳은 명백한 충돌이므로 숨기면 안 된다.",
        [
            _participant("p1", notes="하루에 열 군데는 봐야 직성이 풀려요"),
            _participant("p2", notes="하루에 두 곳만 천천히 보고 싶어요"),
        ],
        _places(),
        ScenarioExpectations(expects_conflict=True),
    )

    add(
        "s40",
        "이상적 입력 (best case)",
        "모든 정보가 충분할 때 불필요한 충돌이나 미해결 이슈를 만들면 안 된다.",
        [
            _participant(
                "p1",
                budget="FROM_200000_TO_400000_KRW",
                accommodation="HOTEL",
                must="바다가 보이는 곳",
                notes="사진 찍기 좋은 장소를 좋아합니다",
            ),
            _participant(
                "p2",
                budget="FROM_200000_TO_400000_KRW",
                accommodation="HOTEL",
                must="바다가 보이는 곳",
                notes="조용한 카페를 좋아합니다",
            ),
        ],
        _places(),
        ScenarioExpectations(expects_conflict=False),
    )

    return scenarios


#: Number of scenarios in the bundled suite.
SCENARIO_COUNT = 40

#: A representative subset for when the full suite is too slow to run.
#:
#: A local 7B model needs roughly three hours for all forty. These ten keep the
#: coverage that matters -- both safety categories, three kinds of conflict,
#: thin data, an opening-hours violation, and a clean best case -- so a short
#: run still says something about whether the system works.
CORE_SCENARIO_IDS: tuple[str, ...] = (
    "s01",  # 선호가 거의 일치: 없는 충돌을 만들어내지 않는가
    "s04",  # 알레르기: 하드 제약이 실제로 장소를 막는가
    "s05",  # 보행 제약: 이동 하드 제약
    "s06",  # 후보 부족: 없는 장소를 지어내지 않는가
    "s08",  # 영업시간 위반: 검증과 수정이 도는가
    "s11",  # 정반대 활동 선호: 충돌을 드러내는가
    "s26",  # 휠체어: 명시적 물리 제약
    "s33",  # 예산 3단계: 가장 낮은 상한 적용
    "s39",  # 정반대 pace: 충돌 탐지
    "s40",  # 이상적 입력: 불필요한 충돌/이슈를 만들지 않는가
)


def select_scenarios(
    ids: Iterable[str] | None = None, limit: int | None = None
) -> list[EvaluationScenario]:
    """Pick scenarios by id, or the first ``limit`` of the suite.

    Unknown ids are an error rather than a silent no-op: a typo that quietly
    shrinks the suite would make a run look better than it is.
    """

    suite = build_scenarios()
    if ids:
        wanted = list(dict.fromkeys(ids))
        by_id = {s.scenario_id: s for s in suite}
        missing = [i for i in wanted if i not in by_id]
        if missing:
            raise ValueError(f"unknown scenario ids: {missing}")
        return [by_id[i] for i in wanted]
    return suite[:limit] if limit else suite
