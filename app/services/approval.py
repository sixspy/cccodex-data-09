"""点头（人工复核）流程：采集条目先停在牌子下，点头后才进入账册。"""

from app.db import db_transaction, get_db

APPROVAL_PENDING = "pending"
APPROVAL_APPROVED = "approved"

# 采集未完成（或失败）时，后台一律拒绝点头。
APPROVABLE_JOB_STATUS = "done"


def approve_job(job_id: int, approver_name: str) -> tuple[str, str]:
    """执行点头。

    :param approver_name: 网页上另填的点头人姓名（并非登录账号）。
    :return: ("ok", None) 或 ("error", 文案)。
    """
    name = (approver_name or "").strip()
    db = get_db()
    job = db.execute(
        "SELECT * FROM crawl_jobs WHERE id = ?", (job_id,)
    ).fetchone()
    if job is None:
        return "error", "任务不存在"

    # 后台同样挡下：采集未完成时不允许点头。
    if job["status"] != APPROVABLE_JOB_STATUS:
        return "error", "采集尚未完成，暂不能点头"

    if job["approval_status"] == APPROVAL_APPROVED:
        return "error", "该任务已点头，不能重复点头"

    if not name:
        return "error", "点头人姓名不能留空"

    created_by = (job["created_by"] or "").strip()
    if name == created_by:
        return "error", "点头人不能与建档人相同"

    with db_transaction() as tx:
        tx.execute(
            """
            UPDATE crawl_jobs
               SET approval_status = ?,
                   approved_by = ?,
                   approved_at = datetime('now')
             WHERE id = ?
            """,
            (APPROVAL_APPROVED, name, job_id),
        )
        tx.execute(
            "UPDATE crawl_records SET approved = 1 WHERE job_id = ?",
            (job_id,),
        )

    return "ok", name


def rename_record(job_id: int, record_id: int, new_title: str) -> tuple[str, str | None]:
    """修改题名；已点头的题名不许再改。"""
    title = (new_title or "").strip()
    if not title:
        return "error", "题名不能留空"

    db = get_db()
    job = db.execute(
        "SELECT * FROM crawl_jobs WHERE id = ?", (job_id,)
    ).fetchone()
    if job is None:
        return "error", "任务不存在"
    if job["approval_status"] == APPROVAL_APPROVED:
        return "error", "已点头的题名不能再修改"

    record = db.execute(
        "SELECT * FROM crawl_records WHERE id = ? AND job_id = ?",
        (record_id, job_id),
    ).fetchone()
    if record is None:
        return "error", "条目不存在"
    if record["approved"]:
        return "error", "已点头的题名不能再修改"

    with db_transaction() as tx:
        tx.execute(
            "UPDATE crawl_records SET title = ? WHERE id = ? AND job_id = ?",
            (title, record_id, job_id),
        )

    return "ok", title
