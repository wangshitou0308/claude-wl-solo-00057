"""HTTP 请求模型（仅做传输层/形状校验）。

业务语义（型号是否存在、版本是否存在等）由判定引擎基于不可变
目录判定，错误由 HTTP 错误映射层统一转成结构化响应。
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RepairRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    device_model: str = Field(..., min_length=1, description="设备型号")
    hardware_revision: str = Field(..., min_length=1, description="硬件修订号")
    installed_part: str = Field(..., min_length=1, description="现装部件编号")
    fault_code: str = Field(..., min_length=1, description="故障代码")
    catalog_version: str = Field(..., min_length=1, description="目录版本")
    measurements: dict[str, Any] = Field(
        default_factory=dict, description="测量值（温度、固件版本等）"
    )
    slot: Optional[str] = Field(
        default=None, description="安装槽位；缺省取该修订号的主槽位"
    )

    @field_validator(
        "device_model",
        "hardware_revision",
        "installed_part",
        "fault_code",
        "catalog_version",
    )
    @classmethod
    def _non_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("must not be blank")
        return v.strip()

    @field_validator("measurements")
    @classmethod
    def _measurement_keys(cls, v: dict[str, Any]) -> dict[str, Any]:
        for key in v:
            if not isinstance(key, str) or not key.strip():
                raise ValueError("measurement keys must be non-blank strings")
        return v
