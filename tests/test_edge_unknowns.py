"""目录引用缺失转接件、固件版本不可解析等未知条件的边界。"""
from __future__ import annotations

import json

from app.catalog import CatalogRegistry
from app.engine.decision import RepairDecisionEngine


_MINIMAL = {
    "version": "t-1",
    "parts": [
        {
            "part_number": "P1",
            "interface": "IF-A",
            "voltage": "5V",
            "firmware_min": "1.0.0",
        },
        {
            "part_number": "P2",
            "interface": "IF-B",
            "voltage": "5V",
            "firmware_min": "1.0.0",
        },
    ],
    "chains": [
        {
            "from_part": "P1",
            "to_part": "P2",
            "adapter_pn": "ADP-MISSING"
        }
    ],
    "devices": [
        {
            "model": "D1",
            "revisions": [
                {
                    "revision": "R1",
                    "slot": "main",
                    "interfaces": ["IF-A", "IF-B"],
                    "voltage": "5V",
                }
            ],
        }
    ],
    "fault_rules": [
        {
            "rule_id": "R1",
            "fault_code": "X1",
            "priority": 10,
            "conclusion": "repairable",
            "conditions": [],
            "required_measurements": [],
            "message": "always",
        }
    ],
}


def _engine_for(tmp_path, raw) -> RepairDecisionEngine:
    (tmp_path / "catalog-t-1.json").write_text(
        json.dumps(raw), encoding="utf-8"
    )
    return RepairDecisionEngine(CatalogRegistry(tmp_path).load_all())


def test_missing_adapter_in_catalog_rejects_candidate(tmp_path):
    engine = _engine_for(tmp_path, _MINIMAL)
    d = engine.decide(
        device_model="D1",
        hardware_revision="R1",
        installed_part="P1",
        fault_code="X1",
        catalog_version="t-1",
        measurements={"firmware_version": "2.0.0"},
    )
    option = d.options[0]
    assert option.feasible is False
    fail = next(
        e for e in option.evidence
        if e.subject == "adapter_exists" and e.status == "fail"
    )
    assert "ADP-MISSING" in fail.detail
    # 存在明确硬失败（目录引用断裂）-> forbidden
    assert d.conclusion == "forbidden"


def test_unparseable_firmware_is_unknown_not_compatible(tmp_path):
    raw = json.loads(json.dumps(_MINIMAL))
    # 直换、同接口，让固件成为唯一关卡
    raw["chains"] = [{"from_part": "P1", "to_part": "P2"}]
    raw["parts"][1]["interface"] = "IF-A"
    engine = _engine_for(tmp_path, raw)
    d = engine.decide(
        device_model="D1",
        hardware_revision="R1",
        installed_part="P1",
        fault_code="X1",
        catalog_version="t-1",
        measurements={"firmware_version": "banana"},
    )
    assert d.conclusion == "need_data"
    fw = next(e for e in d.options[0].evidence if e.subject == "firmware_min")
    assert fw.status == "unknown"


def test_version_comparison_zero_padding():
    from app.engine.versioning import compare_versions, parse_version

    assert compare_versions(parse_version("1.10"), parse_version("1.9")) == 1
    assert compare_versions(parse_version("2.0"), parse_version("2.0.0")) == 0
