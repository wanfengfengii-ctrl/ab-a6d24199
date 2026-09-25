"""草稿与最近一次审计结论的进程内存储。

审计结论带草稿指纹：草稿被修改后，旧结论只作为历史保留并标记为过期，
绝不会被当作新草稿的结果返回给前端。
"""

from __future__ import annotations

import threading
from typing import Dict, Optional


class Store:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._draft: Optional[dict] = None
        self._audit: Optional[dict] = None

    def save_draft(self, draft: dict) -> dict:
        with self._lock:
            self._draft = draft
            return {"draft": self._draft, "saved": True}

    def get_draft(self) -> Optional[dict]:
        with self._lock:
            return None if self._draft is None else dict(self._draft)

    def save_audit(self, audit: dict) -> None:
        with self._lock:
            self._audit = dict(audit)

    def get_audit_state(self, current_fingerprint: Optional[str]) -> Optional[dict]:
        """返回最近审计结论，并标注是否与当前草稿一致。"""
        with self._lock:
            if self._audit is None:
                return None
            audit = dict(self._audit)
        audit["stale"] = (
            current_fingerprint is None
            or audit.get("fingerprint") != current_fingerprint
        )
        return audit


store = Store()
