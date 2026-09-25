"""FastAPI 入口：导排网络录入、草稿修改与审计提交。"""

from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .audit import fingerprint, run_audit
from .storage import store

app = FastAPI(title="化工园区事故导排检修校核", version="1.0.0")

FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"


@app.get("/healthz")
def healthz() -> dict:
    return {"status": "ok"}


@app.get("/api/draft")
def get_draft() -> dict:
    draft = store.get_draft()
    if draft is None:
        return {"draft": None, "fingerprint": None, "audit": None}
    audit = store.get_audit_state(fingerprint(draft))
    return {"draft": draft, "fingerprint": fingerprint(draft), "audit": audit}


@app.put("/api/draft")
async def save_draft(payload: dict) -> dict:
    if not isinstance(payload, dict):
        return JSONResponse({"error": "请求体必须是 JSON 对象"}, status_code=422)
    return store.save_draft(payload)


@app.post("/api/audit")
async def submit_audit(payload: dict) -> JSONResponse:
    """提交审计。

    * 输入无效（方向/容量/节点引用）：HTTP 422 + rejected 结论，拒绝审计；
    * 校核失败：HTTP 200 + failed 结论（正常业务结果，非服务端错误），
      含首条失效管段、源侧割集、焚烧端侧节点与割集容量；
    * 全部达标：HTTP 200 + passed 结论并放行。
    """

    if not isinstance(payload, dict):
        return JSONResponse(
            {"status": "rejected", "errors": ["请求体必须是 JSON 对象"],
             "scenarios": [], "failure": None},
            status_code=422,
        )

    store.save_draft(payload)
    result = run_audit(payload)
    store.save_audit(result)

    status_code = 422 if result["status"] == "rejected" else 200
    return JSONResponse(result, status_code=status_code)


@app.get("/")
def index() -> FileResponse:
    return FileResponse(FRONTEND_DIR / "index.html")


if FRONTEND_DIR.is_dir():
    app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


if __name__ == "__main__":
    import uvicorn

    host = os.environ.get("HOST", "0.0.0.0")
    port = int(os.environ.get("PORT", "8080"))
    uvicorn.run("app.main:app", host=host, port=port)
