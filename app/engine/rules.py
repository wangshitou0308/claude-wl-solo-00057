"""故障规则判定。

三值语义（任何未知条件都不得默认为满足/兼容）：

- 所有条件为真           -> fired（带规则自身结论）
- 存在未知、无明确假      -> needs_data（记录缺失测量项）
- 任一条件明确为假        -> not_applicable

规则显式声明 required_measurements：只要该测量项缺失，规则即
处于 needs_data，即使其 conditions 未引用该项。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..catalog.models import FaultRule, RuleCondition
from .evidence import Evidence, RuleEvaluation


@dataclass(frozen=True)
class ConditionResult:
    truth: bool | None  # True / False / None(=unknown)
    evidence: Evidence


def _compare(cond: RuleCondition, actual: Any) -> bool | None:
    op = cond.op
    expected = cond.value

    if actual is None:
        return None

    if op in ("eq", "ne"):
        # 相等性：布尔/字符串/数字直接比较；类型不同视为明确不匹配
        equal = type(actual) is type(expected) and actual == expected
        if type(actual) is not type(expected) and isinstance(actual, (int, float)) \
                and isinstance(expected, (int, float)):
            equal = actual == expected
        return equal if op == "eq" else not equal

    # 大小比较仅对数字与同类型字符串成立，否则未知
    if isinstance(actual, bool) or isinstance(expected, bool):
        return None
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        if op == "gt":
            return actual > expected
        if op == "gte":
            return actual >= expected
        if op == "lt":
            return actual < expected
        if op == "lte":
            return actual <= expected
    return None


def evaluate_condition(
    cond: RuleCondition, measurements: dict[str, Any]
) -> ConditionResult:
    loc = {
        "kind": "measurement",
        "id": cond.measurement,
    }
    if cond.measurement not in measurements:
        return ConditionResult(
            truth=None,
            evidence=Evidence(
                subject=f"condition:{cond.measurement}:{cond.op}",
                status="unknown",
                detail=f"measurement '{cond.measurement}' is missing",
                locator=loc,
                expected=cond.value,
                actual=None,
            ),
        )
    actual = measurements[cond.measurement]
    truth = _compare(cond, actual)
    if truth is None:
        return ConditionResult(
            truth=None,
            evidence=Evidence(
                subject=f"condition:{cond.measurement}:{cond.op}",
                status="unknown",
                detail=(
                    f"measurement '{cond.measurement}' value {actual!r} "
                    f"cannot be evaluated for operator '{cond.op}'"
                ),
                locator=loc,
                expected=cond.value,
                actual=actual,
            ),
        )
    return ConditionResult(
        truth=truth,
        evidence=Evidence(
            subject=f"condition:{cond.measurement}:{cond.op}",
            status="pass" if truth else "fail",
            detail=(
                f"{cond.measurement}={actual!r} {cond.op} {cond.value!r} "
                f"-> {truth}"
            ),
            locator=loc,
            expected=cond.value,
            actual=actual,
        ),
    )


def evaluate_rule(
    rule: FaultRule, measurements: dict[str, Any]
) -> RuleEvaluation:
    evidences: list[Evidence] = []
    has_false = False
    has_unknown = False

    for required in rule.required_measurements:
        if required not in measurements:
            has_unknown = True
            evidences.append(
                Evidence(
                    subject="required_measurement",
                    status="unknown",
                    detail=f"required measurement '{required}' is missing",
                    locator={"kind": "measurement", "id": required},
                )
            )
        else:
            evidences.append(
                Evidence(
                    subject="required_measurement",
                    status="pass",
                    detail=f"required measurement '{required}' is present",
                    locator={"kind": "measurement", "id": required},
                    actual=measurements[required],
                )
            )

    for cond in rule.conditions:
        result = evaluate_condition(cond, measurements)
        evidences.append(result.evidence)
        if result.truth is False:
            has_false = True
        elif result.truth is None:
            has_unknown = True

    if has_false:
        state = "not_applicable"
        conclusion: str | None = None
    elif has_unknown:
        state = "needs_data"
        conclusion = "need_data"
    else:
        state = "fired"
        conclusion = rule.conclusion

    evidences.append(
        Evidence(
            subject="rule_state",
            status=(
                "pass"
                if state == "fired"
                else "unknown"
                if state == "needs_data"
                else "fail"
            ),
            detail=f"rule {rule.rule_id} -> {state}"
            + (f" ({conclusion})" if conclusion else ""),
            locator={"kind": "fault_rule", "id": rule.rule_id},
        )
    )

    return RuleEvaluation(
        rule_id=rule.rule_id,
        priority=rule.priority,
        state=state,  # type: ignore[arg-type]
        conclusion=conclusion,
        evidence=tuple(evidences),
    )
