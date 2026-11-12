from flask import Blueprint, flash, redirect, render_template, request, url_for

from app.db import get_db
from app.routes.auth import login_required
from app.services.approval import (
    APPROVAL_APPROVED,
    approve_job,
    rename_record,
)
from app.services.mock_catalog import CATALOGS
from app.services.runner import run_job

bp = Blueprint("jobs", __name__)


@bp.route("/")
@login_required
def list_jobs():
    db = get_db()
    jobs = db.execute(
        "SELECT * FROM crawl_jobs ORDER BY id DESC"
    ).fetchall()
    # 账册只统计已点头的条目；牌子下未点头的不计。
    ledger_counts = {
        row["job_id"]: row["c"]
        for row in db.execute(
            "SELECT job_id, COUNT(*) AS c FROM crawl_records "
            "WHERE approved = 1 GROUP BY job_id"
        )
    }
    pending_counts = {
        row["job_id"]: row["c"]
        for row in db.execute(
            "SELECT job_id, COUNT(*) AS c FROM crawl_records "
            "WHERE approved = 0 GROUP BY job_id"
        )
    }
    return render_template(
        "jobs_list.html",
        jobs=jobs,
        ledger_counts=ledger_counts,
        pending_counts=pending_counts,
        seeds=sorted(CATALOGS.keys()),
    )


@bp.post("/jobs")
@login_required
def create_job():
    name = request.form.get("name", "").strip()
    seed = request.form.get("seed_path", "").strip()
    created_by = request.form.get("created_by", "").strip()
    if not name or not seed:
        flash("请填写任务名与种子路径", "error")
        return redirect(url_for("jobs.list_jobs"))
    if not created_by:
        flash("请填写建档人姓名", "error")
        return redirect(url_for("jobs.list_jobs"))
    if seed not in CATALOGS:
        flash("种子路径必须是已注册的 mock 目录", "error")
        return redirect(url_for("jobs.list_jobs"))
    db = get_db()
    db.execute(
        "INSERT INTO crawl_jobs (name, seed_path, status, created_by) "
        "VALUES (?, ?, 'draft', ?)",
        (name, seed, created_by),
    )
    db.commit()
    flash("任务已创建", "ok")
    return redirect(url_for("jobs.list_jobs"))


@bp.post("/jobs/<int:job_id>/run")
@login_required
def run_job_view(job_id: int):
    try:
        summary = run_job(job_id)
        flash(
            f"运行完成：写入 {summary['inserted']} 条，去重跳过 {summary['skipped_dup']} 条",
            "ok",
        )
    except ValueError as e:
        flash(str(e), "error")
    except Exception as e:
        flash(f"运行失败: {e}", "error")
    return redirect(url_for("jobs.detail", job_id=job_id))


@bp.post("/jobs/<int:job_id>/approve")
@login_required
def approve(job_id: int):
    status, result = approve_job(job_id, request.form.get("approver_name", ""))
    if status == "ok":
        flash(f"已点头，点头人：{result}", "ok")
    else:
        flash(result, "error")
    return redirect(url_for("jobs.detail", job_id=job_id))


@bp.post("/jobs/<int:job_id>/records/<int:record_id>/title")
@login_required
def rename(job_id: int, record_id: int):
    status, result = rename_record(job_id, record_id, request.form.get("title", ""))
    if status == "ok":
        flash(f"题名已改为「{result}」", "ok")
    else:
        flash(result, "error")
    return redirect(url_for("jobs.detail", job_id=job_id))


@bp.get("/jobs/<int:job_id>")
@login_required
def detail(job_id: int):
    db = get_db()
    job = db.execute("SELECT * FROM crawl_jobs WHERE id = ?", (job_id,)).fetchone()
    if job is None:
        flash("任务不存在", "error")
        return redirect(url_for("jobs.list_jobs"))
    pending_records = db.execute(
        "SELECT * FROM crawl_records WHERE job_id = ? AND approved = 0 ORDER BY id",
        (job_id,),
    ).fetchall()
    ledger_records = db.execute(
        "SELECT * FROM crawl_records WHERE job_id = ? AND approved = 1 ORDER BY id",
        (job_id,),
    ).fetchall()
    return render_template(
        "job_detail.html",
        job=job,
        pending_records=pending_records,
        ledger_records=ledger_records,
        approval_approved=APPROVAL_APPROVED,
    )
