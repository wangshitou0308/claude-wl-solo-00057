"""数据不足场景：规则层缺数据 与 候选层缺固件测量。"""
from __future__ import annotations


def test_missing_required_measurement_returns_need_data(client, engine):
    decision = engine.decide(
        device_model="TERM-A7",
        hardware_revision="REV-2",
        installed_part="SSD-128",
        fault_code="F001",
        catalog_version="2025.1",
        measurements={"firmware_version": "2.0.0"},  # 缺 smart_log
    )
    assert decision.conclusion == "need_data"
    # 规则未通过 -> 替代链不得提前评估
    assert decision.options == ()
    unknowns = [
        e for e in decision.evidence_summary if e.status == "unknown"
    ]
    assert unknowns


def test_pending_diagnostic_returns_need_data(client):
    resp = client.post(
        "/api/v1/repair-decisions",
        json={
            "device_model": "TERM-A7",
            "hardware_revision": "REV-2",
            "installed_part": "SSD-128",
            "fault_code": "F001",
            "catalog_version": "2025.1",
            "measurements": {
                "smart_log": "pending",
                "firmware_version": "2.0.0",
            },
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["catalog_version"] == "2025.1"
    assert body["conclusion"] == "need_data"
    fired_need_data = next(
        r for r in body["rule_evaluations"]
        if r["rule_id"] == "R-F001-NEEDDATA"
    )
    assert fired_need_data["state"] == "fired"
    assert fired_need_data["conclusion"] == "need_data"


def test_missing_firmware_measurement_unknown_not_compatible(client, engine):
    # 规则判可修，但没有 firmware_version：候选固件校验全部 unknown，
    # 任何候选都不得默认兼容 -> need_data（而非放行）
    decision = engine.decide(
        device_model="TERM-A7",
        hardware_revision="REV-2",
        installed_part="SSD-128",
        fault_code="F001",
        catalog_version="2025.1",
        measurements={"smart_log": "complete"},
    )
    assert decision.conclusion == "need_data"
    assert decision.options, "candidates must be evaluated with evidence"
    assert all(not o.feasible for o in decision.options)
    for option in decision.options:
        fw = next(
            e for e in option.evidence if e.subject == "firmware_min"
        )
        assert fw.status == "unknown"
        assert "missing" in fw.detail or "unparseable" in fw.detail


def test_no_rule_matches_measurements_is_need_data(client, engine):
    # smart_log 给出一个使两条 F001 规则都不适用的值；
    # 没有活跃规则时也不得默认可修
    decision = engine.decide(
        device_model="TERM-A7",
        hardware_revision="REV-2",
        installed_part="SSD-128",
        fault_code="F001",
        catalog_version="2025.1",
        measurements={
            "smart_log": "corrupted",
            "firmware_version": "2.0.0",
        },
    )
    assert decision.conclusion == "need_data"


def test_forbidden_rule_short_circuits_chain(client, engine):
    decision = engine.decide(
        device_model="TERM-A7",
        hardware_revision="REV-2",
        installed_part="SSD-128",
        fault_code="F003",
        catalog_version="2025.1",
        measurements={"temperature_c": 90},
    )
    assert decision.conclusion == "forbidden"
    assert decision.winning_priority == 30
    assert decision.options == ()  # 禁止维修：不评估替代链
