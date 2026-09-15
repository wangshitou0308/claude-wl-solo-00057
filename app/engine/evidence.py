"""判定结果与证据模型。

每个结论（规则命中、候选通过/拒绝）都必须携带 evidence；
任何拒绝都需给出 reason 和 locator，保证可审计。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

EvidenceStatus = Literal["pass", "fail", "unknown"]
OverallConclusion = Literal["repairable", "need_data", "forbidden"]


@dataclass(frozen=True)
class Evidence:
    subject: str  # 检查项标识，如 rule_fired / interface_match / voltage_match
    status: EvidenceStatus
    detail: str
    locator: dict[str, str] = field(default_factory=dict)
    expected: Any = None
    actual: Any = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "subject": self.subject,
            "status": self.status,
            "detail": self.detail,
        }
        if self.locator:
            out["locator"] = self.locator
        if self.expected is not None:
            out["expected"] = self.expected
        if self.actual is not None:
            out["actual"] = self.actual
        return out


@dataclass(frozen=True)
class RuleEvaluation:
    rule_id: str
    priority: int
    state: Literal["fired", "needs_data", "not_applicable"]
    conclusion: str | None
    evidence: tuple[Evidence, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "priority": self.priority,
            "state": self.state,
            "conclusion": self.conclusion,
            "evidence": [e.to_dict() for e in self.evidence],
        }


@dataclass(frozen=True)
class CandidateOption:
    candidate_part: str
    path: tuple[str, ...]  # 从现装件出发经过的链节点
    direct: bool
    adapter_part: str | None
    adapter_steps: int
    replaced_part_count: int  # 更换件数量（候选 + 额外件）
    feasible: bool
    evidence: tuple[Evidence, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "candidate_part": self.candidate_part,
            "path": list(self.path),
            "direct": self.direct,
            "adapter_part": self.adapter_part,
            "adapter_steps": self.adapter_steps,
            "replaced_part_count": self.replaced_part_count,
            "feasible": self.feasible,
            "evidence": [e.to_dict() for e in self.evidence],
        }


@dataclass(frozen=True)
class Decision:
    catalog_version: str
    fault_code: str
    conclusion: OverallConclusion
    rule_evaluations: tuple[RuleEvaluation, ...]
    winning_priority: int | None
    options: tuple[CandidateOption, ...]
    evidence_summary: tuple[Evidence, ...]
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "catalog_version": self.catalog_version,
            "fault_code": self.fault_code,
            "conclusion": self.conclusion,
            "reason": self.reason,
            "winning_priority": self.winning_priority,
            "rule_evaluations": [r.to_dict() for r in self.rule_evaluations],
            "options": [o.to_dict() for o in self.options],
            "evidence_summary": [e.to_dict() for e in self.evidence_summary],
        }
