"""审计草稿的结构化校验：方向、容量、节点引用无效一律拒绝审计。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Sequence

from .maxflow import Arc


@dataclass
class DraftNode:
    id: str
    kind: str  # "source" | "sink" | "junction"
    label: str = ""


@dataclass
class DraftPipe:
    id: str
    source: str
    target: str
    capacity: int
    maintainable: bool
    seq: int


@dataclass
class ValidationReport:
    ok: bool
    errors: List[str]
    nodes: List[DraftNode]
    pipes: List[DraftPipe]


def _is_blank(value: object) -> bool:
    return value is None or (isinstance(value, str) and value.strip() == "")


def _parse_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in ("true", "1", "yes", "on")
    return bool(value)


def _parse_positive_int(value: object) -> tuple[bool, int]:
    """严格解析正整数：拒绝布尔、小数与非数字字符串。"""
    if isinstance(value, bool):
        return False, 0
    if isinstance(value, int):
        return value > 0, value
    if isinstance(value, float):
        return value.is_integer() and value > 0, int(value)
    if isinstance(value, str) and value.strip().isdigit():
        n = int(value.strip())
        return n > 0, n
    return False, 0


def validate_draft(raw: dict) -> ValidationReport:
    errors: List[str] = []

    if not isinstance(raw, dict):
        return ValidationReport(False, ["请求体必须是 JSON 对象"], [], [])

    required_flow = raw.get("required_flow")

    # ---- 事故时必须持续排出的流量 ----
    if _is_blank(required_flow):
        errors.append("必须填写事故时必须持续排出的流量（required_flow）")
        required_flow_num = 0
    else:
        ok, required_flow_num = _parse_positive_int(required_flow)
        if not ok:
            errors.append("事故时必须持续排出的流量必须是正整数")

    # ---- 节点 ----
    raw_nodes = raw.get("nodes", [])
    if not isinstance(raw_nodes, list):
        errors.append("nodes 必须是数组")
        raw_nodes = []

    nodes: List[DraftNode] = []
    node_ids: List[str] = []
    sources: List[str] = []
    sinks: List[str] = []

    for i, item in enumerate(raw_nodes):
        where = f"第 {i + 1} 个节点"
        if not isinstance(item, dict):
            errors.append(f"{where}：格式无效")
            continue
        node_id = str(item.get("id", "")).strip()
        kind = str(item.get("kind", "")).strip()
        if not node_id:
            errors.append(f"{where}：缺少节点编号")
            continue
        if node_id in node_ids:
            errors.append(f"节点编号重复：{node_id}")
            continue
        if kind not in ("source", "sink", "junction"):
            errors.append(f"节点 {node_id}：类型必须是 source / sink / junction")
            continue
        node_ids.append(node_id)
        nodes.append(DraftNode(id=node_id, kind=kind, label=str(item.get("label", "")).strip()))
        if kind == "source":
            sources.append(node_id)
        elif kind == "sink":
            sinks.append(node_id)

    if len(sources) != 1:
        errors.append(f"必须且只能指定一个泄压源，当前为 {len(sources)} 个")
    if len(sinks) != 1:
        errors.append(f"必须且只能指定一个安全焚烧端，当前为 {len(sinks)} 个")

    # ---- 管段 ----
    raw_pipes = raw.get("pipes", [])
    if not isinstance(raw_pipes, list):
        errors.append("pipes 必须是数组")
        raw_pipes = []

    pipes: List[DraftPipe] = []
    pipe_ids: List[str] = []
    node_set = set(node_ids)

    for i, item in enumerate(raw_pipes):
        seq = i + 1
        where = f"第 {seq} 条管段"
        if not isinstance(item, dict):
            errors.append(f"{where}：格式无效")
            continue
        pipe_id = str(item.get("id", "")).strip()
        u = str(item.get("source", "")).strip()
        v = str(item.get("target", "")).strip()
        cap_raw = item.get("capacity")
        maintainable = _parse_bool(item.get("maintainable", False))

        local_errors: List[str] = []
        if not pipe_id:
            local_errors.append("缺少管段编号")
        elif pipe_id in pipe_ids:
            local_errors.append(f"管段编号重复：{pipe_id}")

        # 方向无效：自环 / 反向引用不存在的节点
        if not u or not v:
            local_errors.append("必须同时填写起点和终点")
        else:
            if u == v:
                local_errors.append(f"起点与终点不能相同（{u}），方向无效")
            if u not in node_set:
                local_errors.append(f"起点节点不存在：{u}")
            if v not in node_set:
                local_errors.append(f"终点节点不存在：{v}")

        # 容量无效：非整数或非正数（管段视作容量上限）
        cap_ok, cap = _parse_positive_int(cap_raw)
        if not cap_ok:
            local_errors.append(f"最大流量必须是正整数，当前值：{cap_raw!r}")

        for msg in local_errors:
            errors.append(f"{where}：{msg}")
        if pipe_id and pipe_id not in pipe_ids:
            pipe_ids.append(pipe_id)
        if not local_errors:
            pipes.append(DraftPipe(id=pipe_id, source=u, target=v, capacity=cap,
                                   maintainable=maintainable, seq=seq))

    if not pipes:
        errors.append("至少需要录入一条管段")
    if not any(p.maintainable for p in pipes):
        # 没有任何可检修管段时“任一可检修管段失效”无从谈起，按无效草稿拒绝
        errors.append("至少需要一条被标记为可检修的管段，否则检修校核无意义")

    return ValidationReport(ok=not errors, errors=errors, nodes=nodes, pipes=pipes)


def to_arcs(pipes: Sequence[DraftPipe]) -> List[Arc]:
    return [
        Arc(seq=p.seq, id=p.id, source=p.source, target=p.target,
            capacity=p.capacity, maintainable=p.maintainable)
        for p in pipes
    ]
