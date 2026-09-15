"""不可变目录的领域模型。

所有对象均为 frozen dataclass；Catalog 构造时用 MappingProxyType
冻结对外暴露的映射，确保“按版本不可变加载”后判定引擎无法改写目录。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal, Mapping, Optional

RuleConclusion = Literal["repairable", "need_data", "forbidden"]
ConditionOp = Literal["eq", "ne", "gt", "gte", "lt", "lte"]


@dataclass(frozen=True)
class Part:
    """配件/部件主数据。任何 *未知* 条件不得默认为兼容：

    - interface 为 None：该件不涉及接口（如纯机械支架）；
    - voltage 为 None：该件不涉及电压；
    - firmware_min 为 None：无固件下限；存在则强制校验。
    """

    part_number: str
    description: str = ""
    interface: Optional[str] = None
    from_interface: Optional[str] = None
    voltage: Optional[str] = None
    firmware_min: Optional[str] = None
    is_adapter: bool = False


@dataclass(frozen=True)
class ChainLink:
    """替代链上的一条有向边 from_part -> to_part。

    adapter_pn 为 None 表示直换；否则为必需转接件。
    extra_parts 是随该方案必须一并更换的其它部件（计入更换件数量）。
    """

    from_part: str
    to_part: str
    adapter_pn: Optional[str] = None
    extra_parts: tuple[str, ...] = ()
    note: str = ""


@dataclass(frozen=True)
class DeviceRevision:
    revision: str
    slot: str
    interfaces: frozenset[str]
    voltage: str


@dataclass(frozen=True)
class DeviceModel:
    model: str
    revisions: Mapping[str, DeviceRevision]


@dataclass(frozen=True)
class RuleCondition:
    measurement: str
    op: ConditionOp
    value: object


@dataclass(frozen=True)
class FaultRule:
    rule_id: str
    fault_code: str
    priority: int
    conclusion: RuleConclusion
    conditions: tuple[RuleCondition, ...] = ()
    required_measurements: tuple[str, ...] = ()
    message: str = ""


@dataclass(frozen=True)
class Catalog:
    """某一版本的完整只读目录。"""

    version: str
    parts: Mapping[str, Part]
    chains: tuple[ChainLink, ...]
    devices: Mapping[str, DeviceModel]
    fault_rules: Mapping[str, tuple[FaultRule, ...]]
    _adj: Mapping[str, tuple["ChainLink", ...]] = field(
        default_factory=dict, init=False, repr=False, compare=False
    )

    def part(self, part_number: str) -> Part:
        return self.parts[part_number]

    def has_part(self, part_number: str) -> bool:
        return part_number in self.parts

    def outgoing(self, part_number: str) -> tuple[ChainLink, ...]:
        return self._adj.get(part_number, ())

    def rules_for(self, fault_code: str) -> tuple[FaultRule, ...]:
        return self.fault_rules.get(fault_code, ())

    @staticmethod
    def create(
        version: str,
        parts: Mapping[str, Part],
        chains: tuple[ChainLink, ...],
        devices: Mapping[str, DeviceModel],
        fault_rules: Mapping[str, tuple[FaultRule, ...]],
    ) -> "Catalog":
        cat = Catalog(
            version=version,
            parts=MappingProxyType(dict(parts)),
            chains=chains,
            devices=MappingProxyType(
                {
                    m: DeviceModel(
                        model=m,
                        revisions=MappingProxyType(dict(model.revisions)),
                    )
                    for m, model in devices.items()
                }
            ),
            fault_rules=MappingProxyType(
                {code: tuple(rules) for code, rules in fault_rules.items()}
            ),
        )
        # 内部邻接表，仅用于查询，不对外暴露可变结构
        adj: dict[str, list[ChainLink]] = {}
        for link in chains:
            adj.setdefault(link.from_part, []).append(link)
        object.__setattr__(
            cat,
            "_adj",
            MappingProxyType({k: tuple(v) for k, v in adj.items()}),
        )
        return cat
