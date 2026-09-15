"""目录版本：不存在报错、固定回显、新版本加入后旧结论保持不变。"""
from __future__ import annotations

from app.catalog import CatalogRegistry
from app.engine.decision import RepairDecisionEngine


def test_missing_catalog_version_is_404_with_locator(client):
    resp = client.post(
        "/api/v1/repair-decisions",
        json={
            "device_model": "TERM-A7",
            "hardware_revision": "REV-2",
            "installed_part": "SSD-128",
            "fault_code": "F001",
            "catalog_version": "1999.9",
            "measurements": {},
        },
    )
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"]["code"] == "CATALOG_VERSION_NOT_FOUND"
    assert body["error"]["locators"][0]["id"] == "1999.9"
    assert "2025.1" in body["error"]["context"]["available_versions"]


def _decide(engine: RepairDecisionEngine, version: str, fault: str = "F001"):
    return engine.decide(
        device_model="TERM-A7",
        hardware_revision="REV-2",
        installed_part="SSD-128",
        fault_code=fault,
        catalog_version=version,
        measurements={"smart_log": "complete", "firmware_version": "2.0.0"},
    )


def test_response_echoes_pinned_version(client):
    resp = client.post(
        "/api/v1/repair-decisions",
        json={
            "device_model": "TERM-A7",
            "hardware_revision": "REV-2",
            "installed_part": "SSD-128",
            "fault_code": "F001",
            "catalog_version": "2025.1",
            "measurements": {
                "smart_log": "complete",
                "firmware_version": "2.0.0",
            },
        },
    )
    assert resp.json()["catalog_version"] == "2025.1"


def test_old_version_conclusion_unchanged_after_new_catalog_added(
    tmp_path,
):
    """先只加载 v1 得到结论 A；加入 v2 文件后重新加载注册表，
    对同一 v1 请求的结论必须字节级保持一致（候选集合也不变）。"""
    import shutil
    from pathlib import Path

    catalog_src = Path(__file__).resolve().parents[1] / "catalogs"

    def registry_with(include_v2: bool) -> RepairDecisionEngine:
        shutil.copy(catalog_src / "catalog-2025.1.json", tmp_path)
        if include_v2:
            shutil.copy(catalog_src / "catalog-2025.2.json", tmp_path)
        reg = CatalogRegistry(tmp_path).load_all()
        return RepairDecisionEngine(reg)

    import json

    before = _decide(registry_with(False), "2025.1").to_dict()
    after_engine = registry_with(True)
    assert "2025.2" in after_engine._registry.versions
    after = _decide(after_engine, "2025.1").to_dict()

    assert json.dumps(before, sort_keys=True, ensure_ascii=False) == json.dumps(
        after, sort_keys=True, ensure_ascii=False
    )
    # v1 不得看到 v2 才引入的配件；v2 可见
    assert "SSD-2048" not in {o["candidate_part"] for o in before["options"]}
    v2_decision = _decide(after_engine, "2025.2")
    assert "SSD-2048" in {o.candidate_part for o in v2_decision.options}


def test_catalog_objects_are_immutable(engine):
    catalog = engine._registry.get("2025.1")
    import pytest

    with pytest.raises(TypeError):
        catalog.parts["SSD-128"] = catalog.parts["SSD-256"]  # type: ignore[index]
