"""The one rule that always runs.

Every other rule inspects the items in a plan, so all of them opt out when
there are none -- which used to leave an empty itinerary with zero checked
rules and an ``isValid: true`` verdict. Presenting "nothing" as "a validated
plan" is the worst failure this system can have, so this rule has no
``is_applicable`` guard.
"""

from __future__ import annotations

from typing import Iterable

from triptailor_ai.schemas.validation import Severity, ValidationCode, ValidationIssue
from triptailor_ai.validation.rules.base import Rule, ValidationContext, issue


class CompletenessRule(Rule):
    rule_id = "completeness"
    description = "일정이 비어 있지 않고 최소한의 검증이 실제로 수행되었는지 확인한다"

    def is_applicable(self, context: ValidationContext) -> bool:
        # Always. That is the entire point of this rule.
        return True

    def check(self, context: ValidationContext) -> Iterable[ValidationIssue]:
        items = context.itinerary.all_items()
        if items:
            return

        day_count = context.request.travel_period.day_count
        yield issue(
            ValidationCode.EMPTY_ITINERARY,
            Severity.ERROR,
            f"일정이 비어 있습니다. {day_count}일 여행에 배치된 장소가 하나도 없습니다.",
            rule_id=self.rule_id,
            evidence={
                "dayCount": day_count,
                "candidateCount": len(context.candidates),
                "itemCount": 0,
            },
            repair_hint=(
                "후보 장소 목록에서 각 날짜에 최소 1개 이상의 일정을 배치하세요. "
                "후보가 부족하면 일정을 만들 수 없다고 보고하세요."
            ),
        )

        if not context.candidates:
            yield issue(
                ValidationCode.NOTHING_VALIDATED,
                Severity.ERROR,
                "후보 장소가 없어 어떤 제약도 검증할 수 없었습니다.",
                rule_id=self.rule_id,
                evidence={"candidateCount": 0},
                repair_hint="장소 검색 결과를 확인하세요. 검증 없이 일정을 승인해서는 안 됩니다.",
            )
