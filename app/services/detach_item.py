"""计划拆项：删 plan_items，碎件态可仍停在已入计划。"""
from __future__ import annotations

from app.db import get_db
from app.services.errors import ServiceError


def detach_one(plan_id: int, file_id: int, db_path: str | None = None) -> dict:
    with get_db(db_path) as conn:
        row = conn.execute(
            "SELECT * FROM plan_items WHERE plan_id=? AND file_id=?",
            (plan_id, file_id),
        ).fetchone()
        if not row:
            raise ServiceError("挂载项不存在", 404)
        conn.execute(
            "DELETE FROM plan_items WHERE plan_id=? AND file_id=?",
            (plan_id, file_id),
        )
        # silent: do not reset lake_files.status
        conn.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
            (f"detach_chip_{plan_id}_{file_id}", "已退挂"),
        )
        return {"plan_id": plan_id, "file_id": file_id, "chip": "已退挂"}


def force_loose_display(file_id: int, db_path: str | None = None) -> None:
    """Half-fix: display only."""
    with get_db(db_path) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
            (f"file_chip_{file_id}", "碎文件"),
        )
