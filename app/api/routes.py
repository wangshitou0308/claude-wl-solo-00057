"""HTTP 路由：请求校验 -> 判定引擎 -> 固定回显命中版本。"""
from __future__ import annotations

from fastapi import APIRouter

from ..engine.decision import RepairDecisionEngine
from .schemas import RepairRequest


def build_router(engine: RepairDecisionEngine) -> APIRouter:
    router = APIRouter()

    @router.post("/api/v1/repair-decisions", tags=["repair"])
    async def decide_repair(request: RepairRequest) -> dict:
        decision = engine.decide(
            device_model=request.device_model,
            hardware_revision=request.hardware_revision,
            installed_part=request.installed_part,
            fault_code=request.fault_code,
            catalog_version=request.catalog_version,
            measurements=request.measurements,
            slot=request.slot,
        )
        return decision.to_dict()

    return router
