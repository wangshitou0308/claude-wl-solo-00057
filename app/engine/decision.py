"""判定引擎：规则判定 -> 替代链候选校验 -> 结论聚合与排序。

流程（严格顺序，前一步不通过绝不进入下一步的乐观假设）：

1. 版本目录查找（版本不存在 -> CATALOG_VERSION_NOT_FOUND）
2. 设备型号/修订号/现装部件解析（未知 -> 结构化错误）
3. 故障代码与规则求值；按优先级聚合：
   - 最高活跃优先级上 fired 规则结论互斥 -> RULE_CONFLICT
   - fired=repairable 且同层有 needs_data -> 降级 need_data
   - fired=forbidden 即使同层有 needs_data 也优先禁止
4. repairable 才遍历替代链（有环 -> REPLACEMENT_CHAIN_CYCLE），
   逐个候选做接口/电压/固件/转接件校验；
5. 有可行方案 -> repairable；仅因未知被拒 -> need_data；
   全部硬不兼容 -> forbidden（证据说明由适配性导致）。
"""
from __future__ import annotations

from typing import Any

from ..catalog.models import Catalog
from ..catalog.registry import CatalogRegistry
from .chain import discover_candidates
from .compatibility import evaluate_candidate
from .errors import (
    ConflictingRule,
    Locator,
    RuleConflict,
    UnknownDeviceModel,
    UnknownFaultCode,
    UnknownHardwareRevision,
    UnknownPartNumber,
    UnknownSlot,
)
from .evidence import CandidateOption, Decision, Evidence, RuleEvaluation
from .rules import evaluate_rule


def _summary(subject: str, status: str, detail: str, **kw: Any) -> Evidence:
    return Evidence(
        subject=subject,
        status=status,  # type: ignore[arg-type]
        detail=detail,
        locator=kw.get("locator", {}),
        expected=kw.get("expected"),
        actual=kw.get("actual"),
    )


class RepairDecisionEngine:
    def __init__(self, registry: CatalogRegistry) -> None:
        self._registry = registry

    def decide(
        self,
        *,
        device_model: str,
        hardware_revision: str,
        installed_part: str,
        fault_code: str,
        catalog_version: str,
        measurements: dict[str, Any],
        slot: str | None = None,
    ) -> Decision:
        # 1) 版本（registry 对未知版本抛 CATALOG_VERSION_NOT_FOUND）
        catalog = self._registry.get(catalog_version)

        # 2) 设备 / 部件解析
        model = catalog.devices.get(device_model)
        if model is None:
            raise UnknownDeviceModel(
                f"device model '{device_model}' is not in catalog "
                f"version '{catalog_version}'",
                locators=[Locator("device", device_model)],
                context={"catalog_version": catalog_version},
            )
        rev = model.revisions.get(hardware_revision)
        if rev is None:
            raise UnknownHardwareRevision(
                f"hardware revision '{hardware_revision}' of model "
                f"'{device_model}' is not in catalog",
                locators=[
                    Locator("device", device_model),
                    Locator(
                        "device",
                        f"{device_model}:{hardware_revision}",
                        "unknown revision",
                    ),
                ],
                context={
                    "device_model": device_model,
                    "available_revisions": sorted(model.revisions),
                },
            )
        if slot is not None and slot != rev.slot:
            raise UnknownSlot(
                f"slot '{slot}' is not defined for {device_model} "
                f"revision {hardware_revision}",
                locators=[Locator("device", f"{device_model}:{hardware_revision}")],
                context={"expected_slot": rev.slot, "requested_slot": slot},
            )
        if not catalog.has_part(installed_part):
            raise UnknownPartNumber(
                f"installed part '{installed_part}' is not in catalog",
                locators=[Locator("installed_part", installed_part)],
            )
        installed = catalog.part(installed_part)

        # 3) 故障代码存在性 + 规则求值
        rules = catalog.rules_for(fault_code)
        if not rules:
            raise UnknownFaultCode(
                f"fault code '{fault_code}' has no rules in catalog "
                f"version '{catalog_version}'",
                locators=[Locator("fault_rule", fault_code, "no rules defined")],
                context={"fault_code": fault_code, "catalog_version": catalog_version},
            )

        evaluations = tuple(
            evaluate_rule(rule, measurements) for rule in rules
        )
        active = [e for e in evaluations if e.state != "not_applicable"]

        if not active:
            # 没有任何规则被满足/缺数据：未知，不得默认可修
            return Decision(
                catalog_version=catalog_version,
                fault_code=fault_code,
                conclusion="need_data",
                rule_evaluations=evaluations,
                winning_priority=None,
                options=(),
                evidence_summary=(
                    _summary(
                        "fault_rule",
                        "unknown",
                        f"no rule for fault code '{fault_code}' matched the "
                        f"supplied measurements; repairability cannot be assumed",
                        locator={"kind": "fault_rule", "id": fault_code},
                    ),
                ),
                reason="no applicable fault rule and no missing data declared",
            )

        highest = max(e.priority for e in active)
        top = [e for e in active if e.priority == highest]
        fired = [e for e in top if e.state == "fired"]
        pending = [e for e in top if e.state == "needs_data"]

        summary: list[Evidence] = []

        if fired:
            conclusions = {e.conclusion for e in fired}
            if len(conclusions) > 1:
                raise self._conflict(fault_code, highest, fired, rules)
            rule_conclusion = fired[0].conclusion
            summary.append(
                _summary(
                    "fault_rule",
                    "pass",
                    f"{len(fired)} rule(s) fired at priority {highest} "
                    f"with conclusion '{rule_conclusion}'",
                    locator={"kind": "fault_rule", "id": fired[0].rule_id},
                )
            )
            # 同优先级存在缺数据规则时，维修结论降级；禁止不受影响
            if rule_conclusion == "repairable" and pending:
                return self._need_data(
                    catalog_version,
                    fault_code,
                    evaluations,
                    highest,
                    summary
                    + [
                        _summary(
                            "fault_rule",
                            "unknown",
                            f"{len(pending)} same-priority rule(s) require "
                            f"additional measurements",
                            locator={
                                "kind": "fault_rule",
                                "id": pending[0].rule_id,
                            },
                        )
                    ],
                    "highest-priority rules disagree on data sufficiency",
                )
            if rule_conclusion in ("forbidden", "need_data"):
                return Decision(
                    catalog_version=catalog_version,
                    fault_code=fault_code,
                    conclusion=rule_conclusion,  # type: ignore[arg-type]
                    rule_evaluations=evaluations,
                    winning_priority=highest,
                    options=(),
                    evidence_summary=tuple(summary),
                    reason=(
                        f"fault rule at priority {highest} concludes "
                        f"'{rule_conclusion}'; replacement chain not evaluated"
                    ),
                )
            # rule_conclusion == repairable -> 继续走替代链
        else:
            # 最高活跃层全部缺数据
            return self._need_data(
                catalog_version,
                fault_code,
                evaluations,
                highest,
                summary
                + [
                    _summary(
                        "fault_rule",
                        "unknown",
                        f"{len(pending)} rule(s) at priority {highest} need "
                        f"additional measurements",
                        locator={"kind": "fault_rule", "id": pending[0].rule_id},
                    )
                ],
                "all active rules require additional measurements",
            )

        # 4) 替代链（环在这里被检出并抛 REPLACEMENT_CHAIN_CYCLE）
        if not catalog.outgoing(installed_part):
            summary.append(
                _summary(
                    "replacement_chain",
                    "unknown",
                    f"installed part '{installed_part}' has no replacement "
                    f"chain in catalog version '{catalog_version}'",
                    locator={"kind": "replacement_chain", "id": installed_part},
                )
            )
            return Decision(
                catalog_version=catalog_version,
                fault_code=fault_code,
                conclusion="need_data",
                rule_evaluations=evaluations,
                winning_priority=highest,
                options=(),
                evidence_summary=tuple(summary),
                reason="repairable per rules but no replacement chain exists",
            )

        discovered = discover_candidates(catalog, installed_part)
        summary.append(
            _summary(
                "replacement_chain",
                "pass",
                f"traversed {len(discovered)} reachable candidate(s) from "
                f"'{installed_part}' without cycles",
                locator={"kind": "replacement_chain", "id": installed_part},
            )
        )

        # 5) 候选适配校验
        all_options = [
            evaluate_candidate(catalog, rev, installed, d, measurements)
            for d in discovered
        ]
        feasible = sorted(
            (o for o in all_options if o.feasible),
            key=lambda o: (
                o.replaced_part_count,
                o.adapter_steps,
                o.candidate_part,
            ),
        )
        rejected = sorted(
            (o for o in all_options if not o.feasible),
            key=lambda o: o.candidate_part,
        )
        ordered: tuple[CandidateOption, ...] = tuple(feasible + rejected)

        if feasible:
            summary.append(
                _summary(
                    "compatibility",
                    "pass",
                    f"{len(feasible)} feasible replacement option(s); "
                    f"{len(rejected)} rejected",
                    locator={"kind": "replacement_chain", "id": installed_part},
                )
            )
            return Decision(
                catalog_version=catalog_version,
                fault_code=fault_code,
                conclusion="repairable",
                rule_evaluations=evaluations,
                winning_priority=highest,
                options=ordered,
                evidence_summary=tuple(summary),
                reason=(
                    f"{len(feasible)} feasible option(s) after interface, "
                    f"voltage, firmware and adapter verification"
                ),
            )

        # 无可行方案：有任何候选仅因未知被拒 -> need_data；
        # 全部为明确硬不兼容 -> forbidden。
        # 未知条件不得被乐观地当作“确定不兼容”而落入禁止。
        any_unknown_only = any(
            _option_unknown_only(o) for o in all_options
        )
        summary.append(
            _summary(
                "compatibility",
                "unknown" if any_unknown_only else "fail",
                f"0 of {len(all_options)} candidate(s) feasible",
                locator={"kind": "replacement_chain", "id": installed_part},
            )
        )
        return Decision(
            catalog_version=catalog_version,
            fault_code=fault_code,
            conclusion="need_data" if any_unknown_only else "forbidden",
            rule_evaluations=evaluations,
            winning_priority=highest,
            options=ordered,
            evidence_summary=tuple(summary),
            reason=(
                "at least one candidate is rejected solely due to "
                "unknown/missing data"
                if any_unknown_only
                else "all candidates hard-incompatible with this device revision"
            ),
        )

    # ------------------------------------------------------------------
    @staticmethod
    def _need_data(
        version: str,
        fault_code: str,
        evaluations: tuple[RuleEvaluation, ...],
        priority: int | None,
        summary: list[Evidence],
        reason: str,
    ) -> Decision:
        return Decision(
            catalog_version=version,
            fault_code=fault_code,
            conclusion="need_data",
            rule_evaluations=evaluations,
            winning_priority=priority,
            options=(),
            evidence_summary=tuple(summary),
            reason=reason,
        )

    @staticmethod
    def _conflict(
        fault_code: str,
        priority: int,
        fired: list[RuleEvaluation],
        all_rules: Any,
    ) -> RuleConflict:
        rule_messages = {r.rule_id: r.message for r in all_rules}
        conflicting = [
            ConflictingRule(
                rule_id=e.rule_id,
                conclusion=str(e.conclusion),
                priority=priority,
                detail=rule_messages.get(e.rule_id, ""),
            )
            for e in fired
        ]
        conclusions = sorted({str(e.conclusion) for e in fired})
        return RuleConflict(
            f"fault code '{fault_code}': rules at priority {priority} "
            f"yield conflicting conclusions {conclusions}",
            fault_code=fault_code,
            priority=priority,
            rules=conflicting,
        )


def _option_unknown_only(option: CandidateOption) -> bool:
    """候选是否仅因 unknown 证据被拒（没有任何明确 fail）。"""
    return not any(e.status == "fail" for e in option.evidence)
