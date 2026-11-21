import threading

import pytest

from app.db import get_db
from app.services import files, plans, rewrite
from app.services.detach_item import detach_one
from app.services.detach_hang_surface import reconcile_surface, snapshot
from app.services.errors import ServiceError


def _plan_with_items(db):
    p = plans.create_plan("CP-DETACH", "退挂计划", "dw_users", db_path=db)
    plans.attach_loose_files(p["id"], db_path=db)
    return p


def test_detach_dual_write_shrinks_plan(db):
    p = _plan_with_items(db)
    items = plans.plan_detail(p["id"], db_path=db)["items"]
    target = items[0]
    bytes_before = sum(f["size_bytes"] for f in items)
    out = detach_one(p["id"], target["id"], db_path=db)
    # 碎件态立刻回写为碎文件
    assert out["file"]["status"] == "碎文件"
    gone = [f for f in files.list_files("dw_users", db_path=db) if f["id"] == target["id"]]
    assert gone[0]["status"] == "碎文件"
    # 双写：plan_items 行已删，计划卡片字节缩水
    detail = plans.plan_detail(p["id"], db_path=db)
    assert all(f["id"] != target["id"] for f in detail["items"])
    card = [x for x in plans.list_plans(db_path=db) if x["id"] == p["id"]][0]
    assert card["plan_bytes"] == bytes_before - target["size_bytes"]
    assert card["item_count"] == len(items) - 1


def test_detached_item_not_in_merge_candidates(db):
    p = _plan_with_items(db)
    items = plans.plan_detail(p["id"], db_path=db)["items"]
    target = items[0]
    detach_one(p["id"], target["id"], db_path=db)
    plans.publish_plan(p["id"], db_path=db)
    job = rewrite.start_rewrite(p["id"], db_path=db)
    assert job["merged_bytes"] == sum(f["size_bytes"] for f in items[1:])
    left = [f for f in files.list_files("dw_users", db_path=db) if f["id"] == target["id"]]
    assert left[0]["status"] == "碎文件"


def test_drift_blocks_merge(db):
    p = _plan_with_items(db)
    target = plans.plan_detail(p["id"], db_path=db)["items"][0]
    detach_one(p["id"], target["id"], db_path=db)
    # 人为制造漂移：退挂项未回写碎件态
    with get_db(db) as conn:
        conn.execute(
            "UPDATE lake_files SET status='已入计划' WHERE id=?", (target["id"],)
        )
    plans.publish_plan(p["id"], db_path=db)
    with pytest.raises(ServiceError) as exc:
        rewrite.start_rewrite(p["id"], db_path=db)
    assert "未对齐" in exc.value.message


def test_second_detach_rejected_in_chinese(db):
    p = _plan_with_items(db)
    target = plans.plan_detail(p["id"], db_path=db)["items"][0]
    detach_one(p["id"], target["id"], db_path=db)
    with pytest.raises(ServiceError) as exc:
        detach_one(p["id"], target["id"], db_path=db)
    assert "退挂" in exc.value.message


def test_concurrent_detach_single_commit(db):
    p = _plan_with_items(db)
    target = plans.plan_detail(p["id"], db_path=db)["items"][0]
    barrier = threading.Barrier(2)
    results = []

    def worker():
        barrier.wait()
        try:
            detach_one(p["id"], target["id"], db_path=db)
            results.append("ok")
        except ServiceError:
            results.append("rejected")

    threads = [threading.Thread(target=worker) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # 恰好一方落盘，另一方中文失败，互不覆盖
    assert sorted(results) == ["ok", "rejected"]
    row = [f for f in files.list_files("dw_users", db_path=db) if f["id"] == target["id"]][0]
    assert row["status"] == "碎文件"


def test_surface_truth_and_real_repair(db):
    p = _plan_with_items(db)
    target = plans.plan_detail(p["id"], db_path=db)["items"][0]
    detach_one(p["id"], target["id"], db_path=db)
    snap = snapshot(db)
    assert snap["truth"] == "退挂已回写"
    assert snap["panel_chip"] == snap["truth"]
    with get_db(db) as conn:
        conn.execute(
            "UPDATE lake_files SET status='已入计划' WHERE id=?", (target["id"],)
        )
    assert snapshot(db)["truth"] == "态未回碎"
    out = reconcile_surface(db)
    assert out["repaired"] == 1
    assert snapshot(db)["truth"] == "退挂已回写"
