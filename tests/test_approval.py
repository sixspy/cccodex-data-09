"""点头流程验收：六条脚本，每条只验一件事。

每条都用独立的 app / client，互不依赖，可单独执行：

    pytest tests/test_approval.py -k <条目关键词>
"""

from app.db import get_db
from app.services.runner import run_job

ALPHA = "/mock/catalog/alpha"
CREATOR = "张三"


def _login(client):
    return client.post(
        "/login",
        data={"username": "admin", "password": "123456"},
        follow_redirects=True,
    )


def _create_job(client, app, created_by=CREATOR, seed=ALPHA):
    client.post(
        "/jobs",
        data={"name": "验收任务", "seed_path": seed, "created_by": created_by},
        follow_redirects=True,
    )
    with app.app_context():
        return get_db().execute("SELECT id FROM crawl_jobs LIMIT 1").fetchone()["id"]


def _run(app, job_id):
    with app.app_context():
        return run_job(job_id)


def _detail_html(client, job_id):
    return client.get(f"/jobs/{job_id}").get_data(as_text=True)


def _ledger_section(html):
    """截取详情页「账册」区块，用于断言条目是否真的入了账册。"""
    marker = "<h2>账册</h2>"
    assert marker in html
    return html.split(marker, 1)[1].split("</section>", 1)[0]


def _flash_text(html):
    return html.split('<ul class="flash">', 1)[-1]


def _approval_state(app, job_id):
    with app.app_context():
        return get_db().execute(
            "SELECT approval_status, approved_by FROM crawl_jobs WHERE id = ?",
            (job_id,),
        ).fetchone()


def test_1_未点头时账册里没有条目(app, client):
    _login(client)
    job_id = _create_job(client, app)
    _run(app, job_id)

    html = _detail_html(client, job_id)
    ledger = _ledger_section(html)

    assert "账册中暂无条目" in ledger
    assert "市政管线测绘记录表" not in ledger
    assert "排水井巡查台账" not in ledger
    # 条目确实停在牌子下，只是没进账册。
    with app.app_context():
        pending = get_db().execute(
            "SELECT COUNT(*) AS c FROM crawl_records WHERE job_id = ? AND approved = 0",
            (job_id,),
        ).fetchone()["c"]
    assert pending == 2


def test_2_点头人姓名留空过不了(app, client):
    _login(client)
    job_id = _create_job(client, app)
    _run(app, job_id)

    html = client.post(
        f"/jobs/{job_id}/approve",
        data={"approver_name": "   "},
        follow_redirects=True,
    ).get_data(as_text=True)

    assert "点头人姓名不能留空" in _flash_text(html)
    assert _approval_state(app, job_id)["approval_status"] == "pending"
    with app.app_context():
        approved = get_db().execute(
            "SELECT COUNT(*) AS c FROM crawl_records WHERE job_id = ? AND approved = 1",
            (job_id,),
        ).fetchone()["c"]
    assert approved == 0


def test_3_建档人自己点头过不了(app, client):
    _login(client)
    job_id = _create_job(client, app, created_by=CREATOR)
    _run(app, job_id)

    html = client.post(
        f"/jobs/{job_id}/approve",
        data={"approver_name": CREATOR},
        follow_redirects=True,
    ).get_data(as_text=True)

    assert "点头人不能与建档人相同" in _flash_text(html)
    assert _approval_state(app, job_id)["approval_status"] == "pending"


def test_4_点头之后牌子下面是空的(app, client):
    _login(client)
    job_id = _create_job(client, app)
    _run(app, job_id)

    html = client.post(
        f"/jobs/{job_id}/approve",
        data={"approver_name": "李四"},
        follow_redirects=True,
    ).get_data(as_text=True)

    assert "牌子下已清空，条目已进入账册" in html
    assert "点头人：<strong>李四</strong>" in html
    ledger = _ledger_section(html)
    assert "市政管线测绘记录表" in ledger
    assert "排水井巡查台账" in ledger
    with app.app_context():
        pending = get_db().execute(
            "SELECT COUNT(*) AS c FROM crawl_records WHERE job_id = ? AND approved = 0",
            (job_id,),
        ).fetchone()["c"]
    assert pending == 0


def test_5_已点头的题名改不动(app, client):
    _login(client)
    job_id = _create_job(client, app)
    _run(app, job_id)
    client.post(
        f"/jobs/{job_id}/approve",
        data={"approver_name": "李四"},
        follow_redirects=True,
    )
    with app.app_context():
        record = get_db().execute(
            "SELECT id, title FROM crawl_records WHERE job_id = ? ORDER BY id LIMIT 1",
            (job_id,),
        ).fetchone()
        record_id, old_title = record["id"], record["title"]

    html = client.post(
        f"/jobs/{job_id}/records/{record_id}/title",
        data={"title": "偷改的题名"},
        follow_redirects=True,
    ).get_data(as_text=True)

    assert "已点头的题名不能再修改" in _flash_text(html)
    with app.app_context():
        now_title = get_db().execute(
            "SELECT title FROM crawl_records WHERE id = ?", (record_id,)
        ).fetchone()["title"]
    assert now_title == old_title


def test_6_采集未完成时点头入口收起且后台挡下(app, client):
    _login(client)
    job_id = _create_job(client, app)  # 仅创建，不运行

    html = _detail_html(client, job_id)
    assert f"/jobs/{job_id}/approve" not in html
    assert "采集未完成，点头入口已收起" in html

    html = client.post(
        f"/jobs/{job_id}/approve",
        data={"approver_name": "李四"},
        follow_redirects=True,
    ).get_data(as_text=True)
    assert "采集尚未完成，暂不能点头" in _flash_text(html)
    assert _approval_state(app, job_id)["approval_status"] == "pending"
