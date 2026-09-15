"""领域错误与结构化定位。

每一个错误都必须携带可定位到 *规则* 或 *替代链* 的 locator 列表，
HTTP 层负责把这些领域异常映射为响应。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

ErrorCode = Literal[
    "CATALOG_VERSION_NOT_FOUND",
    "UNKNOWN_FAULT_CODE",
    "UNKNOWN_DEVICE_MODEL",
    "UNKNOWN_HARDWARE_REVISION",
    "UNKNOWN_PART_NUMBER",
    "UNKNOWN_SLOT",
    "RULE_CONFLICT",
    "REPLACEMENT_CHAIN_CYCLE",
]


@dataclass(frozen=True)
class Locator:
    """定位信息：kind 表明落点（规则/链/候选/测量项/目录）。"""

    kind: Literal[
        "catalog",
        "fault_rule",
        "replacement_chain",
        "chain_edge",
        "candidate",
        "measurement",
        "device",
        "installed_part",
        "request",
    ]
    id: str
    detail: str = ""

    def to_dict(self) -> dict[str, str]:
        out: dict[str, str] = {"kind": self.kind, "id": self.id}
        if self.detail:
            out["detail"] = self.detail
        return out


class DomainError(Exception):
    """所有可被 HTTP 映射的领域错误的基类。"""

    code: ErrorCode = "CATALOG_VERSION_NOT_FOUND"
    http_status: int = 422

    def __init__(
        self,
        message: str,
        *,
        locators: list[Locator] | None = None,
        context: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.locators: list[Locator] = list(locators or [])
        self.context: dict[str, Any] = dict(context or {})

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": {
                "code": self.code,
                "message": self.message,
                "locators": [loc.to_dict() for loc in self.locators],
                "context": self.context,
            }
        }


class CatalogVersionNotFound(DomainError):
    """请求的目录版本不存在（不可变目录之外的版本）。"""

    code = "CATALOG_VERSION_NOT_FOUND"
    http_status = 404


class UnknownFaultCode(DomainError):
    code = "UNKNOWN_FAULT_CODE"
    http_status = 422


class UnknownDeviceModel(DomainError):
    code = "UNKNOWN_DEVICE_MODEL"
    http_status = 422


class UnknownHardwareRevision(DomainError):
    code = "UNKNOWN_HARDWARE_REVISION"
    http_status = 422


class UnknownPartNumber(DomainError):
    code = "UNKNOWN_PART_NUMBER"
    http_status = 422


class UnknownSlot(DomainError):
    code = "UNKNOWN_SLOT"
    http_status = 422


@dataclass(frozen=True)
class ConflictingRule:
    rule_id: str
    conclusion: str
    priority: int
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule_id": self.rule_id,
            "conclusion": self.conclusion,
            "priority": self.priority,
            "detail": self.detail,
        }


class RuleConflict(DomainError):
    """同一最高优先级上被触发的规则给出了互斥结论。"""

    code = "RULE_CONFLICT"
    http_status = 409

    def __init__(
        self,
        message: str,
        *,
        fault_code: str,
        priority: int,
        rules: list[ConflictingRule],
    ) -> None:
        locators = [
            Locator(
                "fault_rule",
                r.rule_id,
                f"priority={priority}, conclusion={r.conclusion}: {r.detail}",
            )
            for r in rules
        ]
        super().__init__(
            message,
            locators=locators,
            context={"fault_code": fault_code, "priority": priority},
        )
        self.conflicting_rules: list[ConflictingRule] = list(rules)


class ReplacementChainCycle(DomainError):
    """沿原厂替代链遍历时发现有向环。"""

    code = "REPLACEMENT_CHAIN_CYCLE"
    http_status = 409

    def __init__(self, message: str, *, cycle: list[str]) -> None:
        # cycle 同时在 context（机读）与 locator（逐边定位）中给出
        edge_locs: list[Locator] = []
        for i in range(len(cycle) - 1):
            edge_locs.append(
                Locator(
                    "chain_edge",
                    f"{cycle[i]}->{cycle[i + 1]}",
                    f"edge {i + 1} of cycle",
                )
            )
        super().__init__(
            message,
            locators=edge_locs,
            context={"cycle": cycle},
        )
        self.cycle: list[str] = list(cycle)
