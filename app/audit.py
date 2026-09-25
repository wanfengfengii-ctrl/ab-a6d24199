"""审计编排：校验草稿、逐情形独立求最大流、生成通过/失败证据。"""

from __future__ import annotations

import hashlib
import json
from typing import List, Optional

from .maxflow import Arc, FlowResult, solve_all_cases
from .validation import DraftNode, DraftPipe, to_arcs, validate_draft


def fingerprint(payload: dict) -> str:
    """草稿内容指纹：内容一变，旧审计结论即判定为过期。"""
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode("utf-8")).hexdigest()[:16]


def _scenario_dict(case: str, pipe: Optional[DraftPipe], result: FlowResult,
                   required_flow: int) -> dict:
    return {
        "case": case,  # "normal" 正常网络 / "pipe_removed" 单管段临时失效
        "pipe_id": None if pipe is None else pipe.id,
        "pipe_seq": None if pipe is None else pipe.seq,
        "max_flow": result.max_flow,
        "required_flow": required_flow,
        "satisfies": result.max_flow >= required_flow,
        "shortfall": max(0, required_flow - result.max_flow),
        "source_cut": list(result.source_cut),
        "sink_side": list(result.sink_side),
        "cut_edges": list(result.cut_edges),
        "cut_capacity": result.cut_capacity,
    }


def run_audit(payload: dict) -> dict:
    """执行一次完整审计。

    返回结构：
    * rejected：方向/容量/节点引用等输入无效，不进行任何流量计算；
    * passed：  正常网络与所有单管段失效情形均满足必须持续排出流量；
    * failed：  存在不达标情形，给出按录入顺序的首条失效管段及割集证据。
    """

    report = validate_draft(payload)
    if not report.ok:
        return {
            "status": "rejected",
            "errors": report.errors,
            "scenarios": [],
            "failure": None,
            "fingerprint": fingerprint(payload),
        }

    required_flow = int(payload["required_flow"])
    source = next(n.id for n in report.nodes if n.kind == "source")
    sink = next(n.id for n in report.nodes if n.kind == "sink")
    node_order = [n.id for n in report.nodes]
    arcs = to_arcs(report.pipes)
    pipe_by_id = {p.id: p for p in report.pipes}

    cases = solve_all_cases(arcs, node_order, source, sink)

    scenarios: List[dict] = []
    first_failure: Optional[dict] = None
    for removed_id, result in cases:
        if removed_id is None:
            scenario = _scenario_dict("normal", None, result, required_flow)
        else:
            scenario = _scenario_dict("pipe_removed", pipe_by_id[removed_id],
                                      result, required_flow)
        scenarios.append(scenario)
        # 评估顺序：正常网络在前，其后按管段录入顺序；故首个不达标情形
        # 即为“按管段录入顺序的首条失效管段”（正常网络不达标时 pipe 为空）。
        if first_failure is None and not scenario["satisfies"]:
            first_failure = dict(scenario)

    status = "passed" if first_failure is None else "failed"
    return {
        "status": status,
        "errors": [],
        "required_flow": required_flow,
        "source": source,
        "sink": sink,
        "scenarios": scenarios,
        "failure": first_failure,
        "fingerprint": fingerprint(payload),
    }
