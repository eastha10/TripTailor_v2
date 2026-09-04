"""Every scheduled place must come from the retrieved candidate set.

This is the single most important rule in the system: it is what stops the
planner from scheduling a place the model merely remembers.
"""

from __future__ import annotations

from collections import Counter
from typing import Iterable

from triptailor_ai.schemas.validation import Severity, ValidationCode, ValidationIssue
from triptailor_ai.validation.rules.base import Rule, ValidationContext, issue


class PlaceGroundingRule(Rule):
    rule_id = "place_grounding"
    description = "모든 placeId가 검색된 후보 장소 목록에 존재해야 한다"

    def check(self, context: ValidationContext) -> Iterable[ValidationIssue]:
        for item in context.itinerary.all_items():
            if context.place_for(item.place_id) is not None:
                continue
            yield issue(
                ValidationCode.PLACE_NOT_GROUNDED,
                Severity.ERROR,
                f"'{item.place_name}'(placeId={item.place_id})는 후보 장소 목록에 없습니다.",
                rule_id=self.rule_id,
                item_ids=[item.item_id],
                evidence={
                    "placeId": item.place_id,
                    "placeName": item.place_name,
                    "candidateCount": len(context.candidates),
                },
                repair_hint=(
                    "후보 장소 목록(CANDIDATE_PLACES)에 있는 placeId로 교체하거나 "
                    "해당 일정을 제거하세요."
                ),
            )

        yield from self._duplicates(context)

        # A name/id mismatch is not fatal, but it misleads the UI.
        for item in context.itinerary.all_items():
            place = context.place_for(item.place_id)
            if place is not None and place.name != item.place_name:
                yield issue(
                    ValidationCode.PLACE_NOT_GROUNDED,
                    Severity.WARNING,
                    f"placeName('{item.place_name}')이 후보 데이터의 이름('{place.name}')과 다릅니다.",
                    rule_id=self.rule_id,
                    item_ids=[item.item_id],
                    evidence={"placeId": item.place_id, "expectedName": place.name},
                    repair_hint=f"placeName을 '{place.name}'으로 맞추세요.",
                )

    def _duplicates(self, context: ValidationContext) -> Iterable[ValidationIssue]:
        """The same place scheduled more than once.

        A local 7B model filled every lunch slot with the same cafe three days
        running. The planner prompt forbids it, but prompt compliance is not a
        guarantee -- so it is checked here instead.

        Escalated to ERROR only when unused candidates exist to substitute in;
        with a thin candidate pool, repeating a place may be the best the data
        allows and failing the plan would spin the repair loop for nothing.
        """

        items = context.itinerary.all_items()
        counts = Counter(item.place_id for item in items)
        repeated = {place_id for place_id, n in counts.items() if n > 1}
        if not repeated:
            return

        unused = [
            place_id
            for place_id, place in context.candidates.items()
            if counts[place_id] == 0 and not place.is_accommodation
        ]
        severity = Severity.ERROR if unused else Severity.WARNING

        for place_id in sorted(repeated):
            offenders = [i for i in items if i.place_id == place_id]
            name = offenders[0].place_name
            days = sorted({i.day for i in offenders})
            yield issue(
                ValidationCode.DUPLICATE_PLACE,
                severity,
                f"'{name}'이(가) {counts[place_id]}번 중복 배치되었습니다 "
                f"(day {', '.join(str(d) for d in days)}).",
                rule_id=self.rule_id,
                item_ids=[i.item_id for i in offenders],
                evidence={
                    "placeId": place_id,
                    "occurrences": counts[place_id],
                    "days": days,
                    "unusedCandidateCount": len(unused),
                },
                repair_hint=(
                    "첫 방문만 남기고 나머지는 아직 사용하지 않은 후보 장소로 교체하세요."
                    if unused
                    else "후보가 부족해 교체할 장소가 없습니다. 후보를 늘려야 합니다."
                ),
            )
