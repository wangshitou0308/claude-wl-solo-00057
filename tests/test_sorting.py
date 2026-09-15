"""多方案稳定排序：更换件数量 -> 转接步骤 -> 部件编号。"""
from __future__ import annotations


def test_feasible_options_sorted_stably(client, engine):
    decision = engine.decide(
        device_model="TERM-A7",
        hardware_revision="REV-2",
        installed_part="SSD-128",
        fault_code="F001",
        catalog_version="2025.1",
        measurements={"smart_log": "complete", "firmware_version": "2.0.0"},
    )
    feasible = [o for o in decision.options if o.feasible]
    keys = [
        (o.replaced_part_count, o.adapter_steps, o.candidate_part)
        for o in feasible
    ]
    assert keys == sorted(keys)
    # 具体期望顺序：
    # SSD-256(1件,0步) < SSD-512(1件,1步) < SSD-1024(2件,1步)
    assert [o.candidate_part for o in feasible] == [
        "SSD-256",
        "SSD-512",
        "SSD-1024",
    ]


def test_rejected_candidates_still_listed_with_evidence(client, engine):
    decision = engine.decide(
        device_model="TERM-A7",
        hardware_revision="REV-2",
        installed_part="SSD-128",
        fault_code="F001",
        catalog_version="2025.1",
        measurements={"smart_log": "complete", "firmware_version": "2.0.0"},
    )
    rejected = [o for o in decision.options if not o.feasible]
    assert rejected, "rejected options must be present in response"
    for option in rejected:
        result = next(
            e for e in option.evidence if e.subject == "candidate_result"
        )
        assert result.status in ("fail", "unknown")
        assert option.candidate_part in result.detail
