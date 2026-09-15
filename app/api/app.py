"""FastAPI 应用装配（依赖注入目录注册表与判定引擎）。"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from ..catalog import CatalogRegistry
from ..engine.decision import RepairDecisionEngine
from .error_handlers import register_error_handlers
from .routes import build_router

DEFAULT_CATALOG_DIR = Path(__file__).resolve().parents[2] / "catalogs"


def create_app(catalog_dir: str | Path | None = None) -> FastAPI:
    registry = CatalogRegistry(catalog_dir or DEFAULT_CATALOG_DIR).load_all()
    engine = RepairDecisionEngine(registry)

    app = FastAPI(
        title="维修判定与替换件适配 API",
        version="1.0.0",
        description=(
            "按版本不可变目录完成故障可维修判定与替代件适配校验，"
            "任何未知条件均不默认兼容。"
        ),
    )
    app.state.registry = registry
    app.state.engine = engine
    register_error_handlers(app)
    app.include_router(build_router(engine))

    @app.get("/health", tags=["meta"])
    async def health() -> dict:
        return {"status": "ok", "catalog_versions": registry.versions}

    return app
