"""候选配件与设备槽位的适配校验。

严格原则：任何未知条件（目录缺字段、缺转接件、缺固件测量值、
版本无法解析）一律记为 unknown 证据并拒绝候选，绝不默认兼容。

每个候选按固定顺序检查，全部 pass 才 feasible：
  1. 候选件存在于本版目录
  2. 候选接口被设备修订号槽位支持
  3. 直换/转接场景判定与链边声明一致
  4. 必需转接件存在
  5. 转接件接口桥接（现装接口 -> 候选接口）
  6. 电压匹配（候选件，及转接件）
  7. 固件下限满足
  8. 额外更换件存在
"""
from __future__ import annotations

from typing import Any

from ..catalog.models import Catalog, ChainLink, DeviceRevision, Part
from .evidence import CandidateOption, Evidence
from .versioning import firmware_satisfied
from .chain import DiscoveredCandidate


def _ev(
    subject: str,
    status: str,
    detail: str,
    *,
    locator: dict[str, str] | None = None,
    expected: Any = None,
    actual: Any = None,
) -> Evidence:
    return Evidence(
        subject=subject,
        status=status,  # type: ignore[arg-type]
        detail=detail,
        locator=locator or {},
        expected=expected,
        actual=actual,
    )


def evaluate_candidate(
    catalog: Catalog,
    device_rev: DeviceRevision,
    installed: Part,
    discovered: DiscoveredCandidate,
    measurements: dict[str, Any],
) -> CandidateOption:
    candidate_pn = discovered.candidate_part
    last_link: ChainLink = discovered.links[-1]
    cand_loc = {"kind": "candidate", "id": candidate_pn}
    evidence: list[Evidence] = []
    rejected_reasons: list[str] = []
    has_unknown = False

    def fail(subject: str, detail: str, **kw: Any) -> None:
        evidence.append(_ev(subject, "fail", detail, **kw))
        rejected_reasons.append(detail)

    def unknown(subject: str, detail: str, **kw: Any) -> None:
        evidence.append(_ev(subject, "unknown", detail, **kw))
        rejected_reasons.append(detail)
        nonlocal has_unknown
        has_unknown = True

    def passed(subject: str, detail: str, **kw: Any) -> None:
        evidence.append(_ev(subject, "pass", detail, **kw))

    # ---- 1. 候选件存在 ---------------------------------------------------
    if not catalog.has_part(candidate_pn):
        fail(
            "part_exists",
            f"candidate part '{candidate_pn}' is not present in catalog",
            locator=cand_loc,
        )
        return _build_option(discovered, last_link, False, evidence,
                             rejected_reasons, has_unknown, None, None)
    candidate = catalog.part(candidate_pn)
    passed(
        "part_exists",
        f"candidate part '{candidate_pn}' exists in catalog",
        locator=cand_loc,
    )

    # ---- 2. 接口被槽位支持 ----------------------------------------------
    if candidate.interface is None:
        # 不涉及接口的件（机械件等）：无需槽位接口，但转接件也不应存在
        slot_interface_ok = True
        passed(
            "interface_slot",
            f"candidate '{candidate_pn}' declares no interface requirement",
            locator=cand_loc,
        )
    else:
        slot_interface_ok = candidate.interface in device_rev.interfaces
        if slot_interface_ok:
            passed(
                "interface_slot",
                f"interface '{candidate.interface}' is supported by slot "
                f"'{device_rev.slot}' on revision '{device_rev.revision}'",
                locator=cand_loc,
                expected=sorted(device_rev.interfaces),
                actual=candidate.interface,
            )
        else:
            fail(
                "interface_slot",
                f"interface '{candidate.interface}' is NOT supported by slot "
                f"'{device_rev.slot}' on revision '{device_rev.revision}'",
                locator=cand_loc,
                expected=sorted(device_rev.interfaces),
                actual=candidate.interface,
            )

    # ---- 3. 直换 vs 转接的场景判定 --------------------------------------
    installed_if = installed.interface
    requires_adapter = last_link.adapter_pn is not None
    same_interface = (
        installed_if is not None
        and candidate.interface is not None
        and installed_if == candidate.interface
    )

    if candidate.interface is None or installed_if is None:
        # 至少一方不涉及接口：链边声明什么就是什么
        scenario_consistent = True
    else:
        scenario_consistent = requires_adapter != same_interface

    adapter: Part | None = None
    if not scenario_consistent:
        if same_interface and requires_adapter:
            fail(
                "adapter_scenario",
                f"edge declares adapter '{last_link.adapter_pn}' but candidate "
                f"uses the same interface '{installed_if}' as installed part",
                locator={
                    "kind": "chain_edge",
                    "id": f"{last_link.from_part}->{last_link.to_part}",
                },
            )
        else:
            fail(
                "adapter_scenario",
                f"interface changes '{installed_if}' -> '{candidate.interface}' "
                f"but edge declares no required adapter",
                locator={
                    "kind": "chain_edge",
                    "id": f"{last_link.from_part}->{last_link.to_part}",
                },
            )
    else:
        passed(
            "adapter_scenario",
            "direct swap, no adapter required"
            if not requires_adapter
            else f"adapter required per edge: '{last_link.adapter_pn}'",
            locator={
                "kind": "chain_edge",
                "id": f"{last_link.from_part}->{last_link.to_part}",
            },
        )

    # ---- 4. 必需转接件存在 ----------------------------------------------
    if requires_adapter and scenario_consistent:
        adapter_pn = last_link.adapter_pn
        assert adapter_pn is not None
        if not catalog.has_part(adapter_pn):
            fail(
                "adapter_exists",
                f"required adapter '{adapter_pn}' is not present in catalog",
                locator={"kind": "candidate", "id": adapter_pn},
            )
        else:
            adapter = catalog.part(adapter_pn)
            passed(
                "adapter_exists",
                f"required adapter '{adapter_pn}' exists in catalog",
                locator={"kind": "candidate", "id": adapter_pn},
            )

            # ---- 5. 转接件接口桥接 --------------------------------------
            # 目录在转接件上用 from_interface / to_interface 之外的简单
            # 字段表示：interface=候选侧接口，adapter_from=现装侧接口。
            from_if = adapter.from_interface
            if from_if is None:
                unknown(
                    "adapter_bridge",
                    f"adapter '{adapter_pn}' has no known source interface; "
                    f"cannot verify it bridges '{installed_if}' -> "
                    f"'{candidate.interface}'",
                    locator={"kind": "candidate", "id": adapter_pn},
                )
            elif from_if != installed_if:
                fail(
                    "adapter_bridge",
                    f"adapter '{adapter_pn}' source interface is '{from_if}', "
                    f"but installed part provides '{installed_if}'",
                    locator={"kind": "candidate", "id": adapter_pn},
                    expected=installed_if,
                    actual=from_if,
                )
            elif adapter.interface != candidate.interface:
                fail(
                    "adapter_bridge",
                    f"adapter '{adapter_pn}' target interface is "
                    f"'{adapter.interface}', but candidate requires "
                    f"'{candidate.interface}'",
                    locator={"kind": "candidate", "id": adapter_pn},
                    expected=candidate.interface,
                    actual=adapter.interface,
                )
            else:
                passed(
                    "adapter_bridge",
                    f"adapter '{adapter_pn}' bridges '{installed_if}' -> "
                    f"'{candidate.interface}'",
                    locator={"kind": "candidate", "id": adapter_pn},
                )

    # ---- 6. 电压匹配 ----------------------------------------------------
    slot_voltage = device_rev.voltage
    if candidate.voltage is None:
        unknown(
            "voltage_match",
            f"candidate '{candidate_pn}' declares no voltage; compatibility "
            f"cannot be assumed",
            locator=cand_loc,
            expected=slot_voltage,
            actual=None,
        )
    elif candidate.voltage != slot_voltage:
        fail(
            "voltage_match",
            f"candidate '{candidate_pn}' voltage '{candidate.voltage}' != "
            f"slot voltage '{slot_voltage}'",
            locator=cand_loc,
            expected=slot_voltage,
            actual=candidate.voltage,
        )
    else:
        passed(
            "voltage_match",
            f"candidate voltage '{candidate.voltage}' matches slot",
            locator=cand_loc,
            expected=slot_voltage,
            actual=candidate.voltage,
        )

    if adapter is not None:
        if adapter.voltage is None:
            unknown(
                "adapter_voltage_match",
                f"adapter '{adapter.part_number}' declares no voltage; "
                f"compatibility cannot be assumed",
                locator={"kind": "candidate", "id": adapter.part_number},
                expected=slot_voltage,
                actual=None,
            )
        elif adapter.voltage != slot_voltage:
            fail(
                "adapter_voltage_match",
                f"adapter '{adapter.part_number}' voltage '{adapter.voltage}' "
                f"!= slot voltage '{slot_voltage}'",
                locator={"kind": "candidate", "id": adapter.part_number},
                expected=slot_voltage,
                actual=adapter.voltage,
            )
        else:
            passed(
                "adapter_voltage_match",
                f"adapter voltage '{adapter.voltage}' matches slot",
                locator={"kind": "candidate", "id": adapter.part_number},
                expected=slot_voltage,
                actual=adapter.voltage,
            )

    # ---- 7. 固件下限 ----------------------------------------------------
    if candidate.firmware_min is None:
        unknown(
            "firmware_min",
            f"candidate '{candidate_pn}' declares no firmware floor; "
            f"cannot assume compatibility",
            locator=cand_loc,
            actual=None,
        )
    else:
        actual_fw = measurements.get("firmware_version")
        result = firmware_satisfied(actual_fw, candidate.firmware_min)
        if result is None:
            unknown(
                "firmware_min",
                f"firmware_version measurement is missing/unparseable; "
                f"cannot verify floor '{candidate.firmware_min}'",
                locator=cand_loc,
                expected=f">={candidate.firmware_min}",
                actual=actual_fw,
            )
        elif result:
            passed(
                "firmware_min",
                f"firmware {actual_fw} satisfies floor "
                f"'>={candidate.firmware_min}'",
                locator=cand_loc,
                expected=f">={candidate.firmware_min}",
                actual=actual_fw,
            )
        else:
            fail(
                "firmware_min",
                f"firmware {actual_fw} is below required floor "
                f"'>={candidate.firmware_min}'",
                locator=cand_loc,
                expected=f">={candidate.firmware_min}",
                actual=actual_fw,
            )

    # ---- 8. 额外更换件 --------------------------------------------------
    extra_parts = tuple(last_link.extra_parts)
    for extra_pn in extra_parts:
        if not catalog.has_part(extra_pn):
            fail(
                "extra_part_exists",
                f"required extra part '{extra_pn}' is not present in catalog",
                locator={"kind": "candidate", "id": extra_pn},
            )
        else:
            passed(
                "extra_part_exists",
                f"required extra part '{extra_pn}' exists",
                locator={"kind": "candidate", "id": extra_pn},
            )

    feasible = not rejected_reasons
    return _build_option(
        discovered,
        last_link,
        feasible,
        evidence,
        rejected_reasons,
        has_unknown,
        adapter.part_number if adapter is not None else None,
        extra_parts,
    )


def _build_option(
    discovered: DiscoveredCandidate,
    last_link: ChainLink,
    feasible: bool,
    evidence: list[Evidence],
    rejected_reasons: list[str],
    has_unknown: bool,
    adapter_pn: str | None,
    extra_parts: tuple[str, ...] | None,
) -> CandidateOption:
    extra = tuple(extra_parts or last_link.extra_parts)
    replaced_count = 1 + len(extra)
    if not feasible:
        status = "unknown" if has_unknown and not _has_hard_fail(evidence) else "fail"
        evidence.append(
            _ev(
                "candidate_result",
                status,
                f"candidate '{discovered.candidate_part}' rejected: "
                + "; ".join(rejected_reasons),
                locator={"kind": "candidate", "id": discovered.candidate_part},
            )
        )
    else:
        evidence.append(
            _ev(
                "candidate_result",
                "pass",
                f"candidate '{discovered.candidate_part}' is feasible",
                locator={"kind": "candidate", "id": discovered.candidate_part},
            )
        )
    return CandidateOption(
        candidate_part=discovered.candidate_part,
        path=discovered.path,
        direct=last_link.adapter_pn is None,
        adapter_part=adapter_pn,
        adapter_steps=1 if last_link.adapter_pn is not None else 0,
        replaced_part_count=replaced_count,
        feasible=feasible,
        evidence=tuple(evidence),
    )


def _has_hard_fail(evidence: list[Evidence]) -> bool:
    return any(e.status == "fail" for e in evidence)
