"""HTTP 错误映射：领域异常 / 请求校验异常 -> 统一结构化错误信封。

与判定引擎完全分离：引擎只抛 DomainError，本模块决定 HTTP 语义。

错误信封格式：
    {"error": {"code", "message", "locators": [...], "context": {...}}}
"""
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from ..engine.errors import DomainError


def _loc_id(raw_loc: list) -> str:
    parts = list(raw_loc)
    if parts and parts[0] in ("body", "query", "path"):
        parts = parts[1:]
    return ".".join(str(p) for p in parts) or "request"


def _request_locators(errors: list[dict]) -> list[dict[str, str]]:
    locs: list[dict[str, str]] = []
    for err in errors:
        locs.append(
            {
                "kind": "request",
                "id": _loc_id(err.get("loc", [])),
                "detail": err.get("msg", "invalid request"),
            }
        )
    return locs


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _domain_error(_: Request, exc: DomainError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.http_status,
            content=exc.to_dict(),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(
        _: Request, exc: RequestValidationError
    ) -> JSONResponse:
        errors = exc.errors()
        return JSONResponse(
            status_code=422,
            content={
                "error": {
                    "code": "REQUEST_VALIDATION_FAILED",
                    "message": "request payload failed schema validation",
                    "locators": _request_locators(errors),
                    "context": {
                        "validation_errors": [
                            {
                                "loc": _loc_id(err.get("loc", [])),
                                "type": err.get("type"),
                                "message": err.get("msg"),
                            }
                            for err in errors
                        ]
                    },
                }
            },
        )

    @app.exception_handler(Exception)
    async def _unexpected(_: Request, exc: Exception) -> JSONResponse:
        # 未预期错误不吞细节给业务字段；保持结构化信封一致
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": f"unexpected error: {exc.__class__.__name__}",
                    "locators": [],
                    "context": {},
                }
            },
        )
