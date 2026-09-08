"""Hard dietary / allergen constraints.

Only HARD constraints are enforced here.  "회는 별로예요" is a soft
preference and must not fail a plan; "땅콩 알레르기" must.
"""

from __future__ import annotations

from typing import Iterable

from triptailor_ai.retrieval.service import dietary_tags_from
from triptailor_ai.schemas.preference import PreferenceCategory
from triptailor_ai.schemas.validation import Severity, ValidationCode, ValidationIssue
from triptailor_ai.validation.rules.base import Rule, ValidationContext, issue

#: Categories treated as food stops for the "no data" warning.
_FOOD_CATEGORY_MARKERS = {"restaurant", "food", "cafe", "맛집", "식당", "카페"}


class DietaryRule(Rule):
    rule_id = "dietary"
    description = "하드 식이/알레르기 제약을 위반하는 장소가 없어야 한다"

    def is_applicable(self, context: ValidationContext) -> bool:
        return bool(context.itinerary.all_items()) and bool(self._excluded(context))

    def check(self, context: ValidationContext) -> Iterable[ValidationIssue]:
        excluded = self._excluded(context)
        if not excluded:
            return

        untagged_food: list[str] = []
        for item in context.itinerary.all_items():
            place = context.place_for(item.place_id)
            if place is None:
                continue
            violated = {t.lower() for t in place.dietary_tags} & excluded
            if violated:
                yield issue(
                    ValidationCode.DIETARY_CONSTRAINT_VIOLATION,
                    Severity.ERROR,
                    f"'{place.name}'이(가) 하드 식이 제약({', '.join(sorted(violated))})을 위반합니다.",
                    rule_id=self.rule_id,
                    item_ids=[item.item_id],
                    evidence={
                        "placeId": place.place_id,
                        "violatedTags": sorted(violated),
                        "excludedTags": sorted(excluded),
                    },
                    repair_hint=(
                        f"{', '.join(sorted(violated))} 관련 없는 다른 음식 장소로 교체하세요."
                    ),
                )
            elif not place.dietary_tags and self._is_food_place(place):
                untagged_food.append(item.item_id)

        if untagged_food:
            yield issue(
                ValidationCode.DIETARY_DATA_UNVERIFIED,
                Severity.WARNING,
                f"식이 정보가 없는 음식 관련 장소 {len(untagged_food)}건은 알레르기 검증을 하지 못했습니다.",
                rule_id=self.rule_id,
                item_ids=untagged_food,
                evidence={"excludedTags": sorted(excluded)},
            )

    @staticmethod
    def _excluded(context: ValidationContext) -> set[str]:
        tags: set[str] = set()
        for pref in context.hard_constraints:
            if pref.category is not PreferenceCategory.DIETARY:
                continue
            tags.update(dietary_tags_from(pref.source_text))
        return tags

    @staticmethod
    def _is_food_place(place) -> bool:  # noqa: ANN001 - PlaceCandidate
        haystack = {c.lower() for c in (*place.categories, *place.tags)}
        return bool(haystack & _FOOD_CATEGORY_MARKERS)
