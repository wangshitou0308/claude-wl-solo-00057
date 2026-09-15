"""版本化、不可变的配件目录。"""
from .loader import CatalogLoadError, load_catalog
from .models import (
    Catalog,
    ChainLink,
    DeviceModel,
    DeviceRevision,
    FaultRule,
    Part,
    RuleCondition,
)
from .registry import CatalogRegistry

__all__ = [
    "Catalog",
    "CatalogLoadError",
    "CatalogRegistry",
    "ChainLink",
    "DeviceModel",
    "DeviceRevision",
    "FaultRule",
    "Part",
    "RuleCondition",
    "load_catalog",
]
