"""真实业务 API 测试：录入、审计、结论失效与拒绝审计。"""

from __future__ import annotations

import pytest

from app.storage import store


@pytest.fixture(autouse=True)
def _reset_store():
    store._draft = None
    store._audit = None
    yield
    store._draft = None
    store._audit = None


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        yield c


def _payload(required_flow=4):
    return {
        "required_flow": required_flow,
        "nodes": [
            {"id": "S", "kind": "source"},
            {"id": "J", "kind": "junction"},
            {"id": "T", "kind": "sink"},
        ],
        "pipes": [
            {"id": "p1", "source": "S", "target": "J", "capacity": 6, "maintainable": True},
            {"id": "p2", "source": "J", "target": "T", "capacity": 5, "maintainable": True},
            {"id": "p3", "source": "S", "target": "T", "capacity": 3, "maintainable": True},
        ],
    }


def test_healthz(client):
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_full_passing_audit_flow(client):
    resp = client.post("/api/audit", json=_payload(required_flow=3))
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "passed"
    assert len(body["scenarios"]) == 4
    assert all(s["satisfies"] for s in body["scenarios"])
    assert body["scenarios"][0]["max_flow"] == 8


def test_failed_audit_returns_evidence_and_first_pipe(client):
    resp = client.post("/api/audit", json=_payload(required_flow=4))
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "failed"
    failure = body["failure"]
    assert failure["pipe_id"] == "p1"
    assert failure["source_cut"] == ["S"]
    assert "T" in failure["sink_side"]
    assert failure["cut_capacity"] == 3
    assert failure["cut_edges"] == ["p3"]


def test_invalid_audit_rejected_with_422(client):
    payload = _payload()
    payload["pipes"][0]["source"] = "NOPE"
    resp = client.post("/api/audit", json=payload)
    assert resp.status_code == 422
    body = resp.json()
    assert body["status"] == "rejected"
    assert body["scenarios"] == []
    assert any("起点节点不存在" in e for e in body["errors"])


def test_stale_conclusion_after_draft_edit(client):
    # 1. 审计通过
    resp = client.post("/api/audit", json=_payload(required_flow=3))
    assert resp.json()["status"] == "passed"

    state = client.get("/api/draft").json()
    assert state["audit"]["status"] == "passed"
    assert state["audit"]["stale"] is False

    # 2. 用户继续修改草稿（降低 p3 容量）但尚未重新审计
    edited = _payload(required_flow=3)
    edited["pipes"][2]["capacity"] = 0  # 同时制造无效输入
    client.put("/api/draft", json=edited)

    state = client.get("/api/draft").json()
    # 旧结论必须标记为过期，不能作为新草稿的结果
    assert state["audit"] is not None
    assert state["audit"]["stale"] is True
    assert state["audit"]["status"] == "passed"  # 历史结论本身不变

    # 3. 重新审计后得到新结论
    resp = client.post("/api/audit", json=edited)
    assert resp.status_code == 422
    assert resp.json()["status"] == "rejected"
    state = client.get("/api/draft").json()
    assert state["audit"]["stale"] is False
    assert state["audit"]["status"] == "rejected"


def test_draft_can_be_edited_and_reaudited_to_pass(client):
    # 初始草稿需 6：正常网络 8 达标，但 p1 失效仅剩直连 3 < 6
    resp = client.post("/api/audit", json=_payload(required_flow=6))
    body = resp.json()
    assert body["status"] == "failed"
    assert body["failure"]["pipe_id"] == "p1"

    # 修改草稿：J->T 与直连扩容到 6，使任一单管失效仍可导排 6
    fixed = _payload(required_flow=6)
    fixed["pipes"][1]["capacity"] = 6
    fixed["pipes"][2]["capacity"] = 6
    resp = client.post("/api/audit", json=fixed)
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "passed"
    flows = [s["max_flow"] for s in body["scenarios"]]
    # 正常 12；p1 失效剩直连 6；p2 失效剩直连 6；p3 失效剩 S-J-T 6
    assert flows == [12, 6, 6, 6]
