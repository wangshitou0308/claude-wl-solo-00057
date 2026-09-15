"""HTTP 错误映射：未知实体、形状校验、结构化信封。"""
from __future__ import annotations


def test_unknown_fault_code(client):
    resp = client.post(
        "/api/v1/repair-decisions",
        json={
            "device_model": "TERM-A7",
            "hardware_revision": "REV-2",
            "installed_part": "SSD-128",
            "fault_code": "F999",
            "catalog_version": "2025.1",
            "measurements": {},
        },
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"]["code"] == "UNKNOWN_FAULT_CODE"
    assert body["error"]["locators"][0]["kind"] == "fault_rule"
    assert body["error"]["locators"][0]["id"] == "F999"


def test_unknown_device_model(client):
    payload = {
        "device_model": "NO-SUCH",
        "hardware_revision": "REV-2",
        "installed_part": "SSD-128",
        "fault_code": "F001",
        "catalog_version": "2025.1",
        "measurements": {},
    }
    resp = client.post("/api/v1/repair-decisions", json=payload)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "UNKNOWN_DEVICE_MODEL"


def test_unknown_hardware_revision_lists_available(client):
    payload = {
        "device_model": "TERM-A7",
        "hardware_revision": "REV-9",
        "installed_part": "SSD-128",
        "fault_code": "F001",
        "catalog_version": "2025.1",
        "measurements": {},
    }
    resp = client.post("/api/v1/repair-decisions", json=payload)
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"]["code"] == "UNKNOWN_HARDWARE_REVISION"
    assert body["error"]["context"]["available_revisions"] == [
        "REV-1",
        "REV-2",
    ]


def test_unknown_installed_part(client):
    payload = {
        "device_model": "TERM-A7",
        "hardware_revision": "REV-2",
        "installed_part": "SSD-X",
        "fault_code": "F001",
        "catalog_version": "2025.1",
        "measurements": {},
    }
    resp = client.post("/api/v1/repair-decisions", json=payload)
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "UNKNOWN_PART_NUMBER"


def test_request_shape_validation_uses_same_envelope(client):
    resp = client.post(
        "/api/v1/repair-decisions",
        json={
            "hardware_revision": "REV-2",
            # 缺 device_model 等必填项
            "catalog_version": "2025.1",
        },
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"]["code"] == "REQUEST_VALIDATION_FAILED"
    missing = {l["id"] for l in body["error"]["locators"]}
    assert {"device_model", "installed_part", "fault_code"} & missing


def test_extra_fields_rejected(client):
    resp = client.post(
        "/api/v1/repair-decisions",
        json={
            "device_model": "TERM-A7",
            "hardware_revision": "REV-2",
            "installed_part": "SSD-128",
            "fault_code": "F001",
            "catalog_version": "2025.1",
            "measurements": {},
            "bogus": 1,
        },
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "REQUEST_VALIDATION_FAILED"


def test_health_lists_versions(client):
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json()["catalog_versions"] == ["2025.1", "2025.2"]
