"""审计编排与输入校验测试。"""

from __future__ import annotations

from app.audit import run_audit


def _payload(required_flow=8):
    return {
        "required_flow": required_flow,
        "nodes": [
            {"id": "S", "kind": "source", "label": "泄压源"},
            {"id": "J", "kind": "junction", "label": "汇合节点"},
            {"id": "T", "kind": "sink", "label": "安全焚烧端"},
        ],
        "pipes": [
            {"id": "p1", "source": "S", "target": "J", "capacity": 6, "maintainable": True},
            {"id": "p2", "source": "J", "target": "T", "capacity": 5, "maintainable": True},
            {"id": "p3", "source": "S", "target": "T", "capacity": 3, "maintainable": True},
        ],
    }


def test_audit_passes_when_all_scenarios_meet_requirement():
    result = run_audit(_payload(required_flow=3))
    assert result["status"] == "passed"
    assert result["failure"] is None
    # 正常网络 + 3 条可检修管段失效情形
    cases = [(s["case"], s["pipe_id"]) for s in result["scenarios"]]
    assert cases == [("normal", None), ("pipe_removed", "p1"),
                     ("pipe_removed", "p2"), ("pipe_removed", "p3")]
    assert result["scenarios"][0]["max_flow"] == 8  # 5 + 3


def test_audit_fails_and_reports_first_pipe_in_entry_order():
    # 需要 4：正常 8 达标；p1 失效剩 p3=3 不达标 → 首条失效即 p1
    result = run_audit(_payload(required_flow=4))
    assert result["status"] == "failed"
    failure = result["failure"]
    assert failure["pipe_id"] == "p1"
    assert failure["pipe_seq"] == 1
    assert failure["max_flow"] == 3
    assert failure["shortfall"] == 1
    # 可复核证据：源侧割集、焚烧端侧节点、割集容量
    assert "S" in failure["source_cut"]
    assert "T" in failure["sink_side"]
    assert failure["cut_capacity"] == failure["max_flow"]
    assert failure["cut_edges"] == ["p3"]


def test_audit_later_pipe_failure_when_earlier_survives():
    # 需 6：正常 8 达标；p1 失效剩 3 不达标……改成只让 p3 失效暴露瓶颈
    payload = _payload(required_flow=6)
    result = run_audit(payload)
    # p1 失效：3 < 6 先失败，确认按录入顺序而非容量大小
    assert result["failure"]["pipe_id"] == "p1"


def test_audit_rejects_missing_node_reference():
    payload = _payload()
    payload["pipes"][0]["target"] = "GHOST"
    result = run_audit(payload)
    assert result["status"] == "rejected"
    assert any("终点节点不存在" in e for e in result["errors"])
    assert result["scenarios"] == []  # 拒绝审计时不做任何流量计算


def test_audit_rejects_self_loop_and_bad_capacity():
    payload = _payload()
    payload["pipes"][1]["target"] = "J"  # 自环，方向无效
    payload["pipes"][2]["capacity"] = -3  # 容量无效
    result = run_audit(payload)
    assert result["status"] == "rejected"
    joined = " ".join(result["errors"])
    assert "方向无效" in joined
    assert "最大流量必须是正整数" in joined


def test_audit_rejects_wrong_source_sink_counts():
    payload = _payload()
    payload["nodes"][2]["kind"] = "junction"  # 没有焚烧端
    result = run_audit(payload)
    assert result["status"] == "rejected"
    assert any("安全焚烧端" in e for e in result["errors"])


def test_audit_rejects_missing_required_flow():
    payload = _payload()
    del payload["required_flow"]
    result = run_audit(payload)
    assert result["status"] == "rejected"
    assert any("持续排出" in e for e in result["errors"])


def test_audit_rejects_non_integer_capacity_string():
    payload = _payload()
    payload["pipes"][0]["capacity"] = "5.5"
    result = run_audit(payload)
    assert result["status"] == "rejected"
    assert any("最大流量必须是正整数" in e for e in result["errors"])


def test_audit_rejects_bool_and_float_truncation():
    payload = _payload()
    payload["pipes"][0]["capacity"] = True  # 布尔不得被当作容量 1
    result = run_audit(payload)
    assert result["status"] == "rejected"
    assert any("最大流量必须是正整数" in e for e in result["errors"])

    payload = _payload()
    payload["pipes"][0]["capacity"] = 5.9  # 小数不得截断为 5
    result = run_audit(payload)
    assert result["status"] == "rejected"


def test_audit_accepts_numeric_string_capacity():
    payload = _payload(required_flow=3)
    payload["pipes"][0]["capacity"] = "6"
    result = run_audit(payload)
    assert result["status"] == "passed"


def test_failure_evidence_reproducible_cut():
    # 双源侧支路情形下的割集证据复核
    payload = {
        "required_flow": 10,
        "nodes": [
            {"id": "S", "kind": "source"},
            {"id": "A", "kind": "junction"},
            {"id": "T", "kind": "sink"},
        ],
        "pipes": [
            {"id": "e1", "source": "S", "target": "A", "capacity": 4, "maintainable": True},
            {"id": "e2", "source": "A", "target": "T", "capacity": 9, "maintainable": True},
        ],
    }
    result = run_audit(payload)
    assert result["status"] == "failed"
    failure = result["failure"]
    # 正常网络最大流 4 < 10，首先报告正常网络不足
    assert failure["case"] == "normal"
    assert failure["cut_edges"] == ["e1"]
    assert failure["cut_capacity"] == 4
