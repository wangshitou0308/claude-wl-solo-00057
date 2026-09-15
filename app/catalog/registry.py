"""按版本组织的不可变目录注册表。

从目录加载所有 catalog-*.json，每个版本只解析一次；注册表对外
只返回冻结后的 Catalog 副本。新增目录文件（新版本）不会影响
任何已加载版本的对象及其判定结论。
"""
from __future__ import annotations

from pathlib import Path
from threading import Lock

from .loader import CatalogLoadError, load_catalog
from .models import Catalog
from ..engine.errors import CatalogVersionNotFound, Locator


class CatalogRegistry:
    def __init__(self, catalog_dir: str | Path) -> None:
        self._dir = Path(catalog_dir)
        self._catalogs: dict[str, Catalog] = {}
        self._lock = Lock()

    def load_all(self) -> "CatalogRegistry":
        if not self._dir.is_dir():
            raise CatalogLoadError(f"catalog directory not found: {self._dir}")
        for path in sorted(self._dir.glob("catalog-*.json")):
            catalog = load_catalog(path)
            with self._lock:
                if catalog.version in self._catalogs:
                    raise CatalogLoadError(
                        f"duplicate catalog version {catalog.version} "
                        f"({path.name})"
                    )
                self._catalogs[catalog.version] = catalog
        return self

    @property
    def versions(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._catalogs))

    def get(self, version: str) -> Catalog:
        with self._lock:
            catalog = self._catalogs.get(version)
        if catalog is None:
            raise CatalogVersionNotFound(
                f"catalog version '{version}' does not exist",
                locators=[
                    Locator(
                        "catalog",
                        version,
                        "no immutable catalog registered for this version",
                    )
                ],
                context={
                    "requested_version": version,
                    "available_versions": self.versions,
                },
            )
        return catalog
