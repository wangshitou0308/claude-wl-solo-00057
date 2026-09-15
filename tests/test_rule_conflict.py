"""同优先级规则结论冲突：结构化、可定位到每条规则。"""
from __future__ import annotations


def test_same_priority_conflict_raises_structured_error(client, engine):
    from app.engine.errors import RuleConflict

    try:
        engine.decide(
            device_model="TERM-A7",
            hardware_revision="REV-2",
            installed_part="SSD-128",
            fault_code="F002",
            catalog_version="2025.1",
            measurements={"vibration_mm_s": 5},
        )
    except RuleConflict as exc:
        assert exc.http_status == 409
        assert exc.context["fault_code"] == "F002"
        assert exc.context["priority"] == 20
        rule_ids = {loc.id for loc in exc.locators}
        assert rule_ids == {"R-F002-REPAIR", "R-F002-FORBID"}
        assert all(loc.kind == "fault_rule" for loc in exc.locators)
        conclusions = {r.conclusion for r in exc.conflicting_rules}
        assert conclusions == {"repairable", "forbidden"}
    else:  # pragma: no cover
        raise AssertionError("expected RuleConflict")


def test_conflict_http_envelope(client):
    resp = client.post(
        "/api/v1/repair-decisions",
        json={
            "device_model": "TERM-A7",
            "hardware_revision": "REV-2",
            "installed_part": "SSD-128",
            "fault_code": "F002",
            "catalog_version": "2025.1",
            "measurements": {"vibration_mm_s": 5},
        },
    )
    assert resp.status_code == 409
    body = resp.json()
    assert body["error"]["code"] == "RULE_CONFLICT"
    locator_ids = {l["id"] for l in body["error"]["locators"]}
    assert locator_ids == {"R-F002-REPAIR", "R-F002-FORBID"}
    assert body["error"]["context"]["priority"] == 20


def test_conflict_does_not_fire_when_measurement_missing(client, engine):
    # 缺测量项时两条规则都处于 needs_data（同结论），这是缺数据而非冲突
    decision = engine.decide(
        device_model="TERM-A7",
        hardware_revision="REV-2",
        installed_part="SSD-128",
        fault_code="F002",
        catalog_version="2025.1",
        measurements={},
    )
    assert decision.conclusion == "need_data"
