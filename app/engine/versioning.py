"""固件版本比较。

支持点分数字版本（"1.2", "1.10.0"）与等长数字段比较；
无法解析时返回 None —— 调用方必须按 *未知* 处理，绝不默认通过。
"""
from __future__ import annotations

from typing import Optional


def parse_version(value: object) -> Optional[tuple[int, ...]]:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    parts = text.split(".")
    out: list[int] = []
    for part in parts:
        if not part.isdigit():
            return None
        out.append(int(part))
    return tuple(out)


def compare_versions(left: tuple[int, ...], right: tuple[int, ...]) -> int:
    """左填零对齐后逐段比较，返回 -1 / 0 / 1。"""
    width = max(len(left), len(right))
    a = left + (0,) * (width - len(left))
    b = right + (0,) * (width - len(right))
    if a < b:
        return -1
    if a > b:
        return 1
    return 0


def firmware_satisfied(actual: object, minimum: str) -> Optional[bool]:
    """实际固件是否满足下限。

    返回 None 表示无法判定（缺测量值或无法解析）——未知不得视为兼容。
    """
    a = parse_version(actual)
    m = parse_version(minimum)
    if a is None or m is None:
        return None
    return compare_versions(a, m) >= 0
