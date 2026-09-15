"""替代链有环：带完整环路径与逐边定位。"""
from __future__ import annotations

import pytest

from app.engine.errors import ReplacementChainCycle


def test_cycle_is_detected_with_path(client, engine):
    with pytest.raises(ReplacementChainCycle) as exc_info:
        engine.decide(
            device_model="TERM-A7",
            hardware_revision="REV-2",
            installed_part="CYC-A",
            fault_code="F001",
            catalog_version="2025.1",
            measurements={
                "smart_log": "complete",
                "firmware_version": "2.0.0",
            },
        )
    exc = exc_info.value
    assert exc.http_status == 409
    assert exc.cycle == ["CYC-A", "CYC-B", "CYC-C", "CYC-A"]
    # 逐边 locator 可定位回链
    edge_ids = [loc.id for loc in exc.locators]
    assert edge_ids == [
        "CYC-A->CYC-B",
        "CYC-B->CYC-C",
        "CYC-C->CYC-A",
    ]
    assert all(loc.kind == "chain_edge" for loc in exc.locators)


def test_cycle_http_envelope(client):
    resp = client.post(
        "/api/v1/repair-decisions",
        json={
            "device_model": "TERM-A7",
            "hardware_revision": "REV-2",
            "installed_part": "CYC-A",
            "fault_code": "F001",
            "catalog_version": "2025.1",
            "measurements": {
                "smart_log": "complete",
                "firmware_version": "2.0.0",
            },
        },
    )
    assert resp.status_code == 409
    body = resp.json()
    assert body["error"]["code"] == "REPLACEMENT_CHAIN_CYCLE"
    assert body["error"]["context"]["cycle"] == [
        "CYC-A", "CYC-B", "CYC-C", "CYC-A"
    ]
    assert len(body["error"]["locators"]) == 3
