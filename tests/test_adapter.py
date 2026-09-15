"""带转接件场景与适配校验（接口/电压/固件/额外件/排序）。"""
from __future__ import annotations


def test_adapter_option_after_direct_and_carries_evidence(client, engine):
    decision = engine.decide(
        device_model="TERM-A7",
        hardware_revision="REV-2",
        installed_part="SSD-128",
        fault_code="F001",
        catalog_version="2025.1",
        measurements={"smart_log": "complete", "firmware_version": "2.0.0"},
    )
    feasible = [o for o in decision.options if o.feasible]
    pns = [o.candidate_part for o in feasible]

    # 直换在前；转接方案按更换件数量、转接步骤、部件编号排序
    assert pns[0] == "SSD-256"
    assert "SSD-512" in pns
    assert "SSD-1024" in pns
    assert pns.index("SSD-512") < pns.index("SSD-1024")

    nvme = next(o for o in feasible if o.candidate_part == "SSD-512")
    assert nvme.direct is False
    assert nvme.adapter_part == "ADP-SATA-NVME"
    assert nvme.adapter_steps == 1
    assert nvme.replaced_part_count == 1

    bridge = next(
        e for e in nvme.evidence if e.subject == "adapter_bridge"
    )
    assert bridge.status == "pass"
    assert bridge.locator == {"kind": "candidate", "id": "ADP-SATA-NVME"}

    # SSD-1024 沿 SSD-512 链路继续，必须同换支架 -> 更换件数量为 2
    tb = next(o for o in feasible if o.candidate_part == "SSD-1024")
    assert tb.replaced_part_count == 2
    assert tb.adapter_steps == 1


def test_24v_adapter_is_hard_rejected_with_voltage_evidence(client, engine):
    decision = engine.decide(
        device_model="TERM-A7",
        hardware_revision="REV-2",
        installed_part="SSD-128",
        fault_code="F001",
        catalog_version="2025.1",
        measurements={"smart_log": "complete", "firmware_version": "2.0.0"},
    )
    ind = next(
        o for o in decision.options if o.candidate_part == "SSD-1024-IND"
    )
    assert ind.feasible is False
    fails = {e.subject: e for e in ind.evidence if e.status == "fail"}
    assert "adapter_voltage_match" in fails
    assert fails["adapter_voltage_match"].actual == "24V"
    assert fails["adapter_voltage_match"].expected == "3.3V"
    # 存在明确硬失败 -> 整体结论仍可为 repairable（其它方案可行），
    # 但该候选必须带拒绝证据
    assert decision.conclusion == "repairable"


def test_interface_unsupported_by_revision_is_rejected(client, engine):
    # REV-1 槽位只有 SATA-3，NVMe 候选必须拒绝，绝不默认兼容
    decision = engine.decide(
        device_model="TERM-A7",
        hardware_revision="REV-1",
        installed_part="SSD-128",
        fault_code="F001",
        catalog_version="2025.1",
        measurements={"smart_log": "complete", "firmware_version": "2.0.0"},
    )
    by_pn = {o.candidate_part: o for o in decision.options}
    assert by_pn["SSD-256"].feasible is True
    assert by_pn["SSD-512"].feasible is False
    assert by_pn["SSD-1024"].feasible is False
    nvme = by_pn["SSD-512"]
    slot_fail = next(
        e for e in nvme.evidence
        if e.subject == "interface_slot" and e.status == "fail"
    )
    assert slot_fail.expected == ["SATA-3"]
    assert slot_fail.actual == "NVMe-4"


def test_firmware_below_floor_is_hard_rejected(client, engine):
    decision = engine.decide(
        device_model="TERM-A7",
        hardware_revision="REV-2",
        installed_part="SSD-128",
        fault_code="F001",
        catalog_version="2025.1",
        measurements={"smart_log": "complete", "firmware_version": "1.0.0"},
    )
    # 所有候选固件下限都高于 1.0.0，且属于明确不满足 -> forbidden
    assert decision.conclusion == "forbidden"
    for option in decision.options:
        fw_fail = next(
            e for e in option.evidence
            if e.subject == "firmware_min" and e.status == "fail"
        )
        assert fw_fail.actual == "1.0.0"
