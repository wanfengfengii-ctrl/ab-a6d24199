#!/usr/bin/env python3
"""导排 API 冒烟脚本：对真实运行中的服务做端到端业务校验。

通过环境变量 BASE_URL 指定服务地址（容器内默认 http://web:8080）。
任一检查失败即以退出码 1 退出。
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

BASE_URL = os.environ.get("BASE_URL", "http://web:8080").rstrip("/")

failures: list[str] = []


def _request(method: str, path: str, body: object = None) -> tuple[int, dict | list]:
    data = None
    headers = {}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE_URL + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" — {detail}" if detail and not ok else ""))
    if not ok:
        failures.append(name)


def example_network(required_flow: int) -> dict:
    return {
        "required_flow": required_flow,
        "nodes": [
            {"id": "SRC", "kind": "source", "label": "泄压源"},
            {"id": "J1", "kind": "junction"},
            {"id": "J2", "kind": "junction"},
            {"id": "INC", "kind": "sink", "label": "安全焚烧端"},
        ],
        "pipes": [
            {"id": "P1", "source": "SRC", "target": "J1", "capacity": 8, "maintainable": True},
            {"id": "P2", "source": "SRC", "target": "J2", "capacity": 6, "maintainable": True},
            {"id": "P3", "source": "J1", "target": "INC", "capacity": 6, "maintainable": True},
            {"id": "P4", "source": "J2", "target": "INC", "capacity": 6, "maintainable": True},
            {"id": "P5", "source": "J1", "target": "J2", "capacity": 6, "maintainable": False},
        ],
    }


def main() -> int:
    print(f"== 导排 API 冒烟：{BASE_URL} ==")

    # 1. 健康检查
    status, body = _request("GET", "/healthz")
    check("健康检查 /healthz", status == 200 and body.get("status") == "ok",
          f"status={status} body={body}")

    # 2. 通过情形：必须流量 6
    #   正常网络 12（P1 8 中 6 走 P3、2 经 P5 汇入 J2）；
    #   逐管失效（按录入顺序 P1..P4，P5 不可检修）：
    #   P1 失效 6、P2 失效 8、P3 失效 6、P4 失效 6
    status, body = _request("POST", "/api/audit", example_network(6))
    flows = [s["max_flow"] for s in body.get("scenarios", [])]
    removed = [s["pipe_id"] for s in body.get("scenarios", []) if s["case"] == "pipe_removed"]
    check("达标网络返回 passed", status == 200 and body.get("status") == "passed",
          f"status={status} body={body}")
    check("情形数 = 正常 + 4 条可检修管段", len(body.get("scenarios", [])) == 5,
          f"scenarios={flows}")
    check("失效情形按录入顺序 P1..P4", removed == ["P1", "P2", "P3", "P4"], f"removed={removed}")
    check("逐情形最大流为真实容量结果 [12,6,8,6,6]（非路径条数）",
          flows == [12, 6, 8, 6, 6], f"flows={flows}")
    check("所有情形均达标才放行", all(s["satisfies"] for s in body.get("scenarios", [])))

    # 3. 失败情形：必须流量 7，P1 失效后仅剩 6
    status, body = _request("POST", "/api/audit", example_network(7))
    failure = body.get("failure") or {}
    check("存在不达标时返回 failed", status == 200 and body.get("status") == "failed",
          f"body={body}")
    check("按录入顺序返回首条失效管段 P1(#1)",
          failure.get("pipe_id") == "P1" and failure.get("pipe_seq") == 1,
          f"failure={failure}")
    check("失败证据含最大可导排量 6 与缺口 1",
          failure.get("max_flow") == 6 and failure.get("shortfall") == 1,
          f"failure={failure}")
    check("失败证据含源侧割集（含泄压源 SRC）",
          "SRC" in failure.get("source_cut", []), f"source_cut={failure.get('source_cut')}")
    check("失败证据含焚烧端侧节点（含 INC）",
          "INC" in failure.get("sink_side", []), f"sink_side={failure.get('sink_side')}")
    check("割集容量 == 最大流（最大流最小割定理，可复核）",
          failure.get("cut_capacity") == 6 and failure.get("cut_edges") == ["P2"],
          f"cut={failure.get('cut_edges')} cap={failure.get('cut_capacity')}")

    # 4. 无效输入拒绝审计：节点引用不存在
    invalid = example_network(6)
    invalid["pipes"][0]["source"] = "GHOST"
    status, body = _request("POST", "/api/audit", invalid)
    check("节点引用无效时 HTTP 422 拒绝审计",
          status == 422 and body.get("status") == "rejected" and body.get("scenarios") == [],
          f"status={status} body={body}")
    check("拒绝原因可定位", any("起点节点不存在" in e for e in body.get("errors", [])),
          f"errors={body.get('errors')}")

    # 5. 草稿修改后旧结论过期，不得冒充新草稿结果
    status, state = _request("GET", "/api/draft")
    check("最近结论对当前草稿有效（stale=false）",
          status == 200 and state.get("audit", {}).get("stale") is False, f"state={state}")
    edited = example_network(7)
    edited["pipes"][1]["capacity"] = 3  # 修改草稿但未重新审计
    _request("PUT", "/api/draft", edited)
    status, state = _request("GET", "/api/draft")
    check("草稿修改后旧结论标记 stale=true",
          status == 200 and state.get("audit", {}).get("stale") is True, f"state={state}")

    print("=" * 48)
    if failures:
        print(f"冒烟失败 {len(failures)} 项：{failures}")
        return 1
    print("冒烟全部通过。")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # 网络等异常同样判定失败
        print(f"[FAIL] 冒烟脚本异常：{exc!r}")
        sys.exit(1)
