"""Per-person cost against the group's most restrictive budget band."""

from __future__ import annotations

from typing import Iterable

from triptailor_ai.schemas.validation import Severity, ValidationCode, ValidationIssue
from triptailor_ai.validation.rules.base import Rule, ValidationContext, issue


class BudgetRule(Rule):
    rule_id = "budget"
    description = "1인 예상 비용이 그룹 예산 상한을 넘지 않아야 한다"

    def check(self, context: ValidationContext) -> Iterable[ValidationIssue]:
        items = context.itinerary.all_items()
        missing = [i.item_id for i in items if i.estimated_cost_per_person is None]
        total = sum(i.estimated_cost_per_person or 0 for i in items)
        cap = context.group_budget.per_person_cap_krw

        if cap is None:
            yield issue(
                ValidationCode.BUDGET_UNVERIFIED,
                Severity.WARNING,
                "참여자 예산 밴드 정보가 없어 예산 검증을 수행하지 못했습니다.",
                rule_id=self.rule_id,
                evidence={"estimatedCostPerPerson": total},
            )
            return

        if missing:
            yield issue(
                ValidationCode.BUDGET_UNVERIFIED,
                Severity.WARNING,
                f"{len(missing)}개 일정에 비용 정보가 없어 실제 비용은 더 높을 수 있습니다.",
                rule_id=self.rule_id,
                item_ids=missing,
                evidence={
                    "itemsWithoutCost": len(missing),
                    "knownCostPerPerson": total,
                    "budgetCapPerPerson": cap,
                },
            )

        if total > cap:
            yield issue(
                ValidationCode.BUDGET_EXCEEDED,
                Severity.ERROR,
                f"1인 예상 비용 {total:,}원이 그룹 예산 상한 {cap:,}원을 초과합니다.",
                rule_id=self.rule_id,
                item_ids=[i.item_id for i in items if (i.estimated_cost_per_person or 0) > 0],
                evidence={
                    "estimatedCostPerPerson": total,
                    "budgetCapPerPerson": cap,
                    "overageKrw": total - cap,
                    "limitingParticipantIds": context.group_budget.limiting_participant_ids,
                },
                repair_hint=(
                    f"{total - cap:,}원 이상 줄이도록 비용이 큰 일정을 저렴한 후보로 교체하거나 "
                    "제거하세요."
                ),
            )
