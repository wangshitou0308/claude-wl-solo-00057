"""JSON 目录 -> 不可变 Catalog 的加载器。

加载时做结构校验；版本一旦成功加载即冻结，运行期不会被重新解析或修改。
注意：替代链 *环* 不在加载期拒绝（目录本身可能故意含环以驱动错误语义），
而由判定引擎在遍历时返回带链路定位的 REPLACEMENT_CHAIN_CYCLE。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import (
    Catalog,
    ChainLink,
    DeviceModel,
    DeviceRevision,
    FaultRule,
    Part,
    RuleCondition,
)

_VALID_CONCLUSIONS = {"repairable", "need_data", "forbidden"}
_VALID_OPS = {"eq", "ne", "gt", "gte", "lt", "lte"}


class CatalogLoadError(ValueError):
    """目录文件结构非法（部署期错误，不映射为普通业务响应）。"""


def _require(obj: dict[str, Any], key: str, *, where: str) -> Any:
    if key not in obj:
        raise CatalogLoadError(f"{where}: missing required field '{key}'")
    return obj[key]


def load_catalog(path: str | Path) -> Catalog:
    path = Path(path)
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise CatalogLoadError(f"catalog file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise CatalogLoadError(f"catalog {path.name}: invalid JSON ({exc})") from exc

    version = str(_require(raw, "version", where=path.name))

    # ---- 部件 ----------------------------------------------------------
    parts: dict[str, Part] = {}
    for item in raw.get("parts", []):
        pn = str(_require(item, "part_number", where=f"{path.name}#parts"))
        if pn in parts:
            raise CatalogLoadError(f"{path.name}: duplicate part_number {pn}")
        parts[pn] = Part(
            part_number=pn,
            description=str(item.get("description", "")),
            interface=item.get("interface"),
            from_interface=item.get("from_interface"),
            voltage=item.get("voltage"),
            firmware_min=item.get("firmware_min"),
            is_adapter=bool(item.get("is_adapter", False)),
        )

    # ---- 替代链 --------------------------------------------------------
    chain_list: list[ChainLink] = []
    seen_edges: set[tuple[str, str]] = set()
    for item in raw.get("chains", []):
        where = f"{path.name}#chains"
        fp = str(_require(item, "from_part", where=where))
        tp = str(_require(item, "to_part", where=where))
        edge = (fp, tp)
        if edge in seen_edges:
            raise CatalogLoadError(f"{path.name}: duplicate chain edge {fp}->{tp}")
        seen_edges.add(edge)
        chain_list.append(
            ChainLink(
                from_part=fp,
                to_part=tp,
                adapter_pn=item.get("adapter_pn"),
                extra_parts=tuple(item.get("extra_parts", [])),
                note=str(item.get("note", "")),
            )
        )

    # ---- 设备型号 / 修订号 ---------------------------------------------
    devices: dict[str, DeviceModel] = {}
    for item in raw.get("devices", []):
        model = str(_require(item, "model", where=f"{path.name}#devices"))
        revs: dict[str, DeviceRevision] = {}
        for rev in _require(item, "revisions", where=f"{path.name}#devices/{model}"):
            rev_id = str(_require(rev, "revision", where=f"{path.name}#devices/{model}"))
            interfaces = frozenset(
                str(i) for i in _require(
                    rev, "interfaces", where=f"{path.name}#devices/{model}/{rev_id}"
                )
            )
            revs[rev_id] = DeviceRevision(
                revision=rev_id,
                slot=str(rev.get("slot", "main")),
                interfaces=interfaces,
                voltage=str(
                    _require(
                        rev,
                        "voltage",
                        where=f"{path.name}#devices/{model}/{rev_id}",
                    )
                ),
            )
        devices[model] = DeviceModel(model=model, revisions=revs)

    # ---- 故障规则 ------------------------------------------------------
    fault_rules: dict[str, list[FaultRule]] = {}
    for item in raw.get("fault_rules", []):
        rid = str(_require(item, "rule_id", where=f"{path.name}#fault_rules"))
        code = str(_require(item, "fault_code", where=f"rule {rid}"))
        priority = int(_require(item, "priority", where=f"rule {rid}"))
        conclusion = str(_require(item, "conclusion", where=f"rule {rid}"))
        if conclusion not in _VALID_CONCLUSIONS:
            raise CatalogLoadError(
                f"rule {rid}: invalid conclusion '{conclusion}'"
            )
        conditions = []
        for cond in item.get("conditions", []):
            op = str(_require(cond, "op", where=f"rule {rid}#conditions"))
            if op not in _VALID_OPS:
                raise CatalogLoadError(f"rule {rid}: invalid op '{op}'")
            conditions.append(
                RuleCondition(
                    measurement=str(
                        _require(cond, "measurement", where=f"rule {rid}#conditions")
                    ),
                    op=op,  # type: ignore[arg-type]
                    value=_require(cond, "value", where=f"rule {rid}#conditions"),
                )
            )
        required = tuple(str(m) for m in item.get("required_measurements", []))
        fault_rules.setdefault(code, []).append(
            FaultRule(
                rule_id=rid,
                fault_code=code,
                priority=priority,
                conclusion=conclusion,  # type: ignore[arg-type]
                conditions=tuple(conditions),
                required_measurements=required,
                message=str(item.get("message", "")),
            )
        )

    catalog = Catalog.create(
        version=version,
        parts=parts,
        chains=tuple(chain_list),
        devices=devices,
        fault_rules={code: tuple(rs) for code, rs in fault_rules.items()},
    )
    return catalog
