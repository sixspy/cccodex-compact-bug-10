"""退挂悬挂：展示面与写库面同源，真相来自湖表实测漂移。"""
from __future__ import annotations

from app.db import get_db

_SLUG = "detach_hang"
_OK = "退挂已回写"
_BAD = "态未回碎"


def _drift_count(conn) -> int:
    """退挂项与碎件态的漂移数：已退挂未回写，或挂载中状态漂移。"""
    loose = conn.execute(
        "SELECT COUNT(*) AS c FROM lake_files f WHERE f.status='已入计划' "
        "AND NOT EXISTS (SELECT 1 FROM plan_items i WHERE i.file_id=f.id)"
    ).fetchone()["c"]
    mounted = conn.execute(
        "SELECT COUNT(*) AS c FROM plan_items i JOIN lake_files f ON f.id=i.file_id "
        "WHERE f.status NOT IN ('已入计划','已合并')"
    ).fetchone()["c"]
    return int(loose) + int(mounted)


def truth_flag(db_path: str | None = None) -> str:
    with get_db(db_path) as conn:
        return _OK if _drift_count(conn) == 0 else _BAD


def panel_chip(db_path: str | None = None) -> str:
    # 同源：展示面直接取写库面真相，不再单独维护假绿。
    return truth_flag(db_path)


def seed_skew(db_path: str | None = None) -> None:
    """初始化计数器；不再向展示面写假绿。"""
    with get_db(db_path) as conn:
        conn.execute(
            "INSERT OR IGNORE INTO meta(key, value) VALUES (?, ?)",
            (f"{_SLUG}_counter", "0"),
        )


def bump_counter(db_path: str | None = None) -> int:
    with get_db(db_path) as conn:
        row = conn.execute(
            "SELECT value FROM meta WHERE key=?",
            (f"{_SLUG}_counter",),
        ).fetchone()
        n = int(row["value"]) + 1 if row else 1
        conn.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
            (f"{_SLUG}_counter", str(n)),
        )
        return n


def snapshot(db_path: str | None = None) -> dict:
    """只读快照：不改库，展示面与写库面同一份真相。"""
    with get_db(db_path) as conn:
        drift = _drift_count(conn)
        row = conn.execute(
            "SELECT value FROM meta WHERE key=?",
            (f"{_SLUG}_counter",),
        ).fetchone()
    truth = _OK if drift == 0 else _BAD
    return {
        "title": "退挂悬挂",
        "panel_chip": truth,
        "truth": truth,
        "counter": int(row["value"]) if row else 0,
        "aligned": True,
    }


def list_events(db_path: str | None = None) -> list[dict]:
    with get_db(db_path) as conn:
        rows = conn.execute(
            "SELECT value FROM meta WHERE key LIKE ? ORDER BY key",
            (f"{_SLUG}_evt_%",),
        ).fetchall()
        return [{"note": r["value"]} for r in rows]


def record_event(note: str, db_path: str | None = None) -> dict:
    with get_db(db_path) as conn:
        row = conn.execute(
            "SELECT value FROM meta WHERE key=?",
            (f"{_SLUG}_counter",),
        ).fetchone()
        n = int(row["value"]) + 1 if row else 1
        conn.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
            (f"{_SLUG}_counter", str(n)),
        )
        conn.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
            (f"{_SLUG}_evt_{n}", note or _BAD),
        )
    return snapshot(db_path)


def reconcile_surface(db_path: str | None = None) -> dict:
    """真对齐：把已退挂未回写的碎件回写为碎文件，单次落盘。"""
    with get_db(db_path) as conn:
        rows = conn.execute(
            "SELECT f.id FROM lake_files f WHERE f.status='已入计划' "
            "AND NOT EXISTS (SELECT 1 FROM plan_items i WHERE i.file_id=f.id)"
        ).fetchall()
        for r in rows:
            conn.execute(
                "UPDATE lake_files SET status='碎文件' WHERE id=?", (r["id"],)
            )
        repaired = len(rows)
    snap = snapshot(db_path)
    return {
        "panel_chip": snap["panel_chip"],
        "truth": snap["truth"],
        "repaired": repaired,
        "half_fixed": False,
    }
