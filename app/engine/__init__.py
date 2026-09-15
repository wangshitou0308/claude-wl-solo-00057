"""判定引擎包。

注意：本 __init__ 只暴露无 catalog 依赖的基础类型，避免
catalog.registry <-> engine.decision 的导入环。
引擎编排请直接从子模块导入：

    from app.engine.decision import RepairDecisionEngine
"""
from .errors import (
    CatalogVersionNotFound,
    ConflictingRule,
    DomainError,
    Locator,
    ReplacementChainCycle,
    RuleConflict,
    UnknownFaultCode,
)
from .evidence import CandidateOption, Decision, Evidence

__all__ = [
    "CatalogVersionNotFound",
    "CandidateOption",
    "ConflictingRule",
    "Decision",
    "DomainError",
    "Evidence",
    "Locator",
    "ReplacementChainCycle",
    "RuleConflict",
    "UnknownFaultCode",
]
