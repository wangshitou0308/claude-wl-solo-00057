"""直换场景：同接口、无转接件，排序优先。"""
from __future__ import annotations

BASE_PAYLOAD = {
    "device_model": "TERM-A7",
    "hardware_revision": "REV-2",
    "installed_part": "SSD-128",
    "fault_code": "F001",
    "catalog_version": "2025.1",
    "measurements": {
        "smart_log": "complete",
        "firmware_version": "2.0.0",
    },
}


def test_direct_swap_is_feasible_and_first(client, engine):
    decision = engine.decide(
        device_model="TERM-A7",
        hardware_revision="REV-2",
        installed_part="SSD-128",
        fault_code="F001",
        catalog_version="2025.1",
        measurements={"smart_log": "complete", "firmware_version": "2.0.0"},
    )
    assert decision.conclusion == "repairable"
    feasible = [o for o in decision.options if o.feasible]
    assert feasible, "expected at least one feasible option"

    first = feasible[0]
    assert first.candidate_part == "SSD-256"
    assert first.direct is True
    assert first.adapter_part is None
    assert first.adapter_steps == 0
    assert first.replaced_part_count == 1
    assert first.path == ("SSD-128", "SSD-256")

    # 每个通过结论都必须有证据，且关键校验全部 pass
    subjects = {e.subject for e in first.evidence if e.status == "pass"}
    assert {
        "part_exists",
        "interface_slot",
        "adapter_scenario",
        "voltage_match",
        "firmware_min",
        "candidate_result",
    }.issubset(subjects)


def test_direct_swap_http(client):
    resp = client.post("/api/v1/repair-decisions", json=BASE_PAYLOAD)
    assert resp.status_code == 200
    body = resp.json()
    # 响应固定回显命中版本
    assert body["catalog_version"] == "2025.1"
    assert body["conclusion"] == "repairable"
    first = next(o for o in body["options"] if o["candidate_part"] == "SSD-256")
    assert first["direct"] is True
    assert first["feasible"] is True
