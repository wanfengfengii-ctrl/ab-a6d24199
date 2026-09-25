"""最大流 / 最小割计算引擎。

使用 Dinic 算法。审计中：
* 正常网络独立求一次最大流；
* 每个可检修管段被临时移除后的残余网络各自独立求最大流。

每条管段均被视作有向容量上限，绝不以路径条数代替流量结论。
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Dict, List, Mapping, Optional, Sequence, Tuple

# 容量统一为整数，单位与页面录入的事故持续排出流量一致（如 m³/h）
Capacity = int


@dataclass(frozen=True)
class Arc:
    """一条有向管段。"""

    seq: int  # 录入顺序（从 1 开始），用于失败时定位首条管段
    id: str
    source: str
    target: str
    capacity: Capacity
    maintainable: bool


@dataclass
class FlowResult:
    """一次独立最大流计算的结果。"""

    max_flow: Capacity
    # 最小割中源侧集合 S（包含超源 super_source）
    source_cut: Tuple[str, ...]
    # 最小割中焚烧端侧节点集合 T（包含焚烧端）
    sink_side: Tuple[str, ...]
    # 跨越割 (S -> T) 的管段 id 列表（按录入顺序），即可复核的割集管段
    cut_edges: Tuple[str, ...]
    cut_capacity: Capacity


class _Edge:
    __slots__ = ("to", "rev", "cap")

    def __init__(self, to: int, rev: int, cap: Capacity) -> None:
        self.to = to
        self.rev = rev
        self.cap = cap


class Dinic:
    """整数容量有向图上的 Dinic 最大流。"""

    def __init__(self, n: int) -> None:
        self._n = n
        self._graph: List[List[_Edge]] = [[] for _ in range(n)]

    def add_edge(self, u: int, v: int, cap: Capacity) -> Tuple[_Edge, _Edge]:
        forward = _Edge(v, len(self._graph[v]), cap)
        backward = _Edge(u, len(self._graph[u]), 0)
        self._graph[u].append(forward)
        self._graph[v].append(backward)
        return forward, backward

    def _bfs_level(self, s: int, t: int) -> Optional[List[int]]:
        level = [-1] * self._n
        level[s] = 0
        queue = deque([s])
        graph = self._graph
        while queue:
            u = queue.popleft()
            for edge in graph[u]:
                if edge.cap > 0 and level[edge.to] < 0:
                    level[edge.to] = level[u] + 1
                    queue.append(edge.to)
        return level if level[t] >= 0 else None

    def _dfs_flow(self, u: int, t: int, pushed: Capacity, level: List[int], it: List[int]) -> Capacity:
        if u == t:
            return pushed
        graph = self._graph
        while it[u] < len(graph[u]):
            edge = graph[u][it[u]]
            if edge.cap > 0 and level[edge.to] == level[u] + 1:
                d = self._dfs_flow(edge.to, t, min(pushed, edge.cap), level, it)
                if d > 0:
                    edge.cap -= d
                    graph[edge.to][edge.rev].cap += d
                    return d
            it[u] += 1
        return 0

    def max_flow(self, s: int, t: int) -> Capacity:
        flow: Capacity = 0
        inf = _INF
        while True:
            level = self._bfs_level(s, t)
            if level is None:
                break
            it = [0] * self._n
            while True:
                pushed = self._dfs_flow(s, t, inf, level, it)
                if pushed == 0:
                    break
                flow += pushed
        return flow

    def reachable_from(self, s: int) -> List[bool]:
        """在最终残余网络上求从 s 沿残余容量 > 0 的边可达的节点。"""
        seen = [False] * self._n
        seen[s] = True
        queue = deque([s])
        graph = self._graph
        while queue:
            u = queue.popleft()
            for edge in graph[u]:
                if edge.cap > 0 and not seen[edge.to]:
                    seen[edge.to] = True
                    queue.append(edge.to)
        return seen


_INF: Capacity = 10**30


def build_and_solve(
    arcs: Sequence[Arc],
    nodes: Sequence[str],
    source: str,
    sink: str,
    removed_arc_id: Optional[str] = None,
) -> FlowResult:
    """在给定网络上独立构建图并求最大流与最小割。

    ``removed_arc_id`` 非空时，该管段视为临时失效，不加入图。
    """

    index: Dict[str, int] = {name: i for i, name in enumerate(nodes)}
    dinic = Dinic(len(nodes))

    active: List[Arc] = []
    for arc in arcs:
        if arc.id == removed_arc_id:
            continue
        dinic.add_edge(index[arc.source], index[arc.target], arc.capacity)
        active.append(arc)

    s_idx, t_idx = index[source], index[sink]
    total = dinic.max_flow(s_idx, t_idx)
    reachable = dinic.reachable_from(s_idx)

    source_side = tuple(name for i, name in enumerate(nodes) if reachable[i])
    sink_side = tuple(name for i, name in enumerate(nodes) if not reachable[i])

    source_side_set = set(source_side)
    cut_edge_ids: List[str] = []
    cut_capacity: Capacity = 0
    for arc in sorted(active, key=lambda a: a.seq):
        if arc.source in source_side_set and arc.target not in source_side_set:
            cut_edge_ids.append(arc.id)
            cut_capacity += arc.capacity

    return FlowResult(
        max_flow=total,
        source_cut=source_side,
        sink_side=sink_side,
        cut_edges=tuple(cut_edge_ids),
        cut_capacity=cut_capacity,
    )


def solve_all_cases(
    arcs: Sequence[Arc],
    nodes: Sequence[str],
    source: str,
    sink: str,
) -> List[Tuple[Optional[str], FlowResult]]:
    """对正常网络及每个可检修管段移除后的残余网络分别独立求最大流。

    返回顺序：正常网络（removed=None）在前，其后按管段录入顺序排列
    各可检修管段失效情形。
    """

    cases: List[Tuple[Optional[str], FlowResult]] = []
    cases.append((None, build_and_solve(arcs, nodes, source, sink)))
    for arc in sorted(arcs, key=lambda a: a.seq):
        if arc.maintainable:
            cases.append(
                (arc.id, build_and_solve(arcs, nodes, source, sink, removed_arc_id=arc.id))
            )
    return cases
