"""原厂替代链遍历与候选发现。

遍历采用迭代 DFS + 三色标记：

- white(0) 未访问 / gray(1) 在当前递归路径上 / black(2) 已完成；
- 遇到 gray 后继即发现有向环，立刻抛出带完整环路径的
  REPLACEMENT_CHAIN_CYCLE（定位到逐边链路）；
- 遇到 black 后继是跨边，直接跳过，候选不重复展开。

每个可达部件只产出一个候选，保留首次发现的（最短、按边顺序稳定的）路径。
"""
from __future__ import annotations

from dataclasses import dataclass

from ..catalog.models import Catalog, ChainLink
from .errors import ReplacementChainCycle


@dataclass(frozen=True)
class DiscoveredCandidate:
    candidate_part: str
    path: tuple[str, ...]          # 含起点（现装件）与终点（候选件）
    links: tuple[ChainLink, ...]  # path 上逐段对应的边


def discover_candidates(
    catalog: Catalog, start_part: str
) -> tuple[DiscoveredCandidate, ...]:
    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {start_part: GRAY}
    discovered: list[DiscoveredCandidate] = []

    # 栈帧：(当前节点, 已展开到的出边下标, 当前节点路径, 当前路径上的边)
    stack: list[tuple[str, int, tuple[str, ...], tuple[ChainLink, ...]]] = [
        (start_part, 0, (start_part,), ())
    ]

    while stack:
        node, idx, path, links = stack[-1]
        outgoing = catalog.outgoing(node)

        if idx >= len(outgoing):
            color[node] = BLACK
            stack.pop()
            continue

        link = outgoing[idx]
        stack[-1] = (node, idx + 1, path, links)
        nxt = link.to_part
        nxt_color = color.get(nxt, WHITE)

        if nxt_color == GRAY:
            # 找到回到当前路径上某节点的环
            cycle_start = path.index(nxt)
            cycle = path[cycle_start:] + (nxt,)
            raise ReplacementChainCycle(
                f"cycle detected in replacement chain for installed "
                f"part '{start_part}': {' -> '.join(cycle)}",
                cycle=list(cycle),
            )

        if nxt_color == BLACK:
            # 跨边：该候选已由更早的路径产出
            continue

        new_path = path + (nxt,)
        new_links = links + (link,)
        discovered.append(
            DiscoveredCandidate(
                candidate_part=nxt,
                path=new_path,
                links=new_links,
            )
        )
        color[nxt] = GRAY
        stack.append((nxt, 0, new_path, new_links))

    return tuple(discovered)
