"""Dinic 最大流 / 最小割引擎测试。"""

from __future__ import annotations

from app.maxflow import Arc, build_and_solve, solve_all_cases


def _arc(seq: int, id_: str, u: str, v: str, cap: int, maint: bool = True) -> Arc:
    return Arc(seq=seq, id=id_, source=u, target=v, capacity=cap, maintainable=maint)


def test_simple_series_network():
    # S -5-> A -3-> T  最大流受限于 3
    arcs = [_arc(1, "p1", "S", "A", 5), _arc(2, "p2", "A", "T", 3)]
    nodes = ["S", "A", "T"]
    r = build_and_solve(arcs, nodes, "S", "T")
    assert r.max_flow == 3
    assert r.cut_capacity == 3
    assert r.cut_edges == ("p2",)
    assert "T" in r.sink_side
    assert "S" in r.source_cut


def test_parallel_paths_capacity_not_path_count():
    # 两条路径但容量不同：不能用路径条数（=2）代替流量（=5+2=7）
    arcs = [
        _arc(1, "p1", "S", "A", 5),
        _arc(2, "p2", "S", "B", 2),
        _arc(3, "p3", "A", "T", 5),
        _arc(4, "p4", "B", "T", 2),
    ]
    nodes = ["S", "A", "B", "T"]
    r = build_and_solve(arcs, nodes, "S", "T")
    assert r.max_flow == 7
    assert r.cut_capacity == 7


def test_directed_arcs_no_backflow():
    # 方向必须被尊重：T -> S 的反向管段不能帮助 S 到 T 送流
    arcs = [
        _arc(1, "p1", "S", "A", 10),
        _arc(2, "p2", "A", "T", 4),
        _arc(3, "p3", "T", "S", 100),
    ]
    nodes = ["S", "A", "T"]
    r = build_and_solve(arcs, nodes, "S", "T")
    assert r.max_flow == 4


def test_disconnected_after_removal_gives_zero():
    arcs = [_arc(1, "p1", "S", "T", 9)]
    nodes = ["S", "T"]
    r = build_and_solve(arcs, nodes, "S", "T", removed_arc_id="p1")
    assert r.max_flow == 0
    assert r.cut_capacity == 0
    assert set(r.source_cut) == {"S"}
    assert set(r.sink_side) == {"T"}


def test_min_cut_on_diamond_with_cross_edge():
    # 经典最小割：割源侧出边容量 3+1=4 优于其他割
    arcs = [
        _arc(1, "p1", "S", "A", 3),
        _arc(2, "p2", "S", "B", 1),
        _arc(3, "p3", "A", "B", 100),
        _arc(4, "p4", "A", "T", 2),
        _arc(5, "p5", "B", "T", 3),
    ]
    nodes = ["S", "A", "B", "T"]
    r = build_and_solve(arcs, nodes, "S", "T")
    assert r.max_flow == 4
    assert r.cut_capacity == r.max_flow  # 最大流最小割定理


def test_solve_all_cases_independent_and_ordered():
    arcs = [
        _arc(1, "p1", "S", "A", 5),
        _arc(2, "p2", "A", "T", 5),
        _arc(3, "p3", "S", "T", 2, maint=False),  # 不可检修：不产生失效情形
    ]
    nodes = ["S", "A", "T"]
    cases = solve_all_cases(arcs, nodes, "S", "T")
    # 正常 + 两条可检修管段，共 3 个情形；每个情形独立建图
    assert [removed for removed, _ in cases] == [None, "p1", "p2"]
    assert cases[0][1].max_flow == 7
    assert cases[1][1].max_flow == 2  # p1 失效，仅剩直连 2
    assert cases[2][1].max_flow == 2  # p2 失效，仅剩直连 2


def test_residual_reroute_keeps_capacity():
    # 单管失效后流量应能绕行：p4(B->T) 失效时，B 来流可经 p5 到 A 再入 T
    arcs = [
        _arc(1, "p1", "S", "A", 4),
        _arc(2, "p2", "S", "B", 4),
        _arc(3, "p3", "A", "T", 8),
        _arc(4, "p4", "B", "T", 4),
        _arc(5, "p5", "B", "A", 8),
    ]
    nodes = ["S", "A", "B", "T"]
    normal = build_and_solve(arcs, nodes, "S", "T")
    assert normal.max_flow == 8
    r = build_and_solve(arcs, nodes, "S", "T", removed_arc_id="p4")
    assert r.max_flow == 8  # S->B->A->T 与 S->A->T 汇合，A->T 容量 8

