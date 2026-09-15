"""HTTP 适配层：请求模型、路由、错误映射。"""
from .app import DEFAULT_CATALOG_DIR, create_app

__all__ = ["DEFAULT_CATALOG_DIR", "create_app"]
