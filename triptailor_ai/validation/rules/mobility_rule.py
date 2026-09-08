"""Hard mobility constraints against place accessibility data."""

from __future__ import annotations

from typing import Iterable

from triptailor_ai.retrieval.service import MOBILITY_EXCLUSION_TAGS
from triptailor_ai.schemas.preference import PreferenceCategory
from triptailor_ai.schemas.validation import Severity, ValidationCode, ValidationIssue
from triptailor_ai.validation.rules.base import Rule, ValidationContext, issue


class MobilityRule(Rule):
    rule_id = "mobility"
    description = "보행/이동 하드 제약이 있으면 부담이 큰 장소를 배치하지 않는다"

    def is_applicable(self, context: ValidationContext) -> bool:
        return bool(context.itinerary.all_items()) and self._has_hard_mobility(context)

    def check(self, context: ValidationContext) -> Iterable[ValidationIssue]:
        if not self._has_hard_mobility(context):
            return

        banned = {tag.lower() for tag in MOBILITY_EXCLUSION_TAGS}
        no_data: list[str] = []

        for item in context.itinerary.all_items():
            place = context.place_for(item.place_id)
            if place is None:
                continue
            if not place.accessibility:
                no_data.append(item.item_id)
                continue
            violated = {t.lower() for t in place.accessibility} & banned
            if violated:
                yield issue(
                    ValidationCode.MOBILITY_CONSTRAINT_VIOLATION,
                    Severity.ERROR,
                    f"'{place.name}'은(는) 보행 부담이 큰 장소({', '.join(sorted(violated))})라 "
                    "이동 제약이 있는 동행자에게 적합하지 않습니다.",
                    rule_id=self.rule_id,
                    item_ids=[item.item_id],
                    evidence={
                        "placeId": place.place_id,
                        "violatedTags": sorted(violated),
                        "accessibility": place.accessibility,
                    },
                    repair_hint="접근성이 좋은(도보 부담이 적은) 다른 후보로 교체하세요.",
                )

        if no_data:
            yield issue(
                ValidationCode.MOBILITY_DATA_UNVERIFIED,
                Severity.WARNING,
                f"접근성 데이터가 없어 {len(no_data)}개 일정의 이동 부담을 확인하지 못했습니다.",
                rule_id=self.rule_id,
                item_ids=no_data,
                evidence={"unverifiedItemCount": len(no_data)},
            )

    @staticmethod
    def _has_hard_mobility(context: ValidationContext) -> bool:
        return any(
            pref.category is PreferenceCategory.MOBILITY
            for pref in context.hard_constraints
        )
