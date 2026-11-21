"""计划拆项：退挂即双写，计划项与碎件态在同一事务落库。"""
from __future__ import annotations

from app.db import get_db
from app.services.errors import ServiceError


def detach_one(plan_id: int, file_id: int, db_path: str | None = None) -> dict:
    """退挂双写：删 plan_items 并把碎件态回写为碎文件，单次落盘。

    两名仓管并发触发同一退挂时，DELETE 认领原子生效：只有真正删到
    挂载行的一方完成回写，另一方拿不到行、回滚并收到中文失败，
    不会双写退挂态、不会互相覆盖。
    """
    with get_db(db_path) as conn:
        plan = conn.execute(
            "SELECT * FROM compact_plans WHERE id=?", (plan_id,)
        ).fetchone()
        if not plan:
            raise ServiceError("计划不存在", 404)
        if plan["status"] not in ("草稿", "已发布"):
            raise ServiceError("当前计划状态不可退挂", 409)
        cur = conn.execute(
            "DELETE FROM plan_items WHERE plan_id=? AND file_id=?",
            (plan_id, file_id),
        )
        if cur.rowcount == 0:
            raise ServiceError("挂载项不存在或已退挂", 404)
        row = conn.execute(
            "SELECT * FROM lake_files WHERE id=?", (file_id,)
        ).fetchone()
        if not row:
            raise ServiceError("碎件不存在", 404)
        if row["status"] != "已入计划":
            raise ServiceError("仅已入计划的碎件可退挂回写", 409)
        conn.execute(
            "UPDATE lake_files SET status='碎文件' WHERE id=? AND status='已入计划'",
            (file_id,),
        )
        out = conn.execute(
            "SELECT * FROM lake_files WHERE id=?", (file_id,)
        ).fetchone()
        return {
            "plan_id": plan_id,
            "file_id": file_id,
            "chip": "已退挂",
            "file": dict(out),
        }
