"""Unit tests for plan/task REST API routes (V3 P2).

Uses the ``authed_client`` fixture (dependency-override based auto-auth)
like the other route tests. The raw ``api_client`` is used for the 401
case so we exercise the real missing-token path.
"""

from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient


def _create_plan(
    client: TestClient, title: str = "晚间例程", **extra: object
) -> dict:
    payload: dict = {"title": title}
    payload.update(extra)
    response = client.post("/api/v1/plans", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_create_plan_with_tasks(authed_client: TestClient) -> None:
    """POST /plans 创建 plan 并原子嵌入 tasks。"""
    data = _create_plan(
        authed_client,
        title="晚间例程",
        motivation="改善睡眠",
        source_refs=[{"type": "diary", "id": 1}],
        tasks=[
            {"title": "睡前不看手机"},
            {"title": "泡茶", "due_date": "2026-08-10"},
        ],
        source="agent",
        created_from_conversation_id="conv-1",
    )
    assert data["title"] == "晚间例程"
    assert data["motivation"] == "改善睡眠"
    assert data["source"] == "agent"
    assert data["status"] == "active"
    # source_refs echo back with optional fields defaulting to None.
    assert data["source_refs"] == [
        {"type": "diary", "id": 1, "date": None, "snippet": None}
    ]
    assert len(data["tasks"]) == 2
    titles = {t["title"] for t in data["tasks"]}
    assert titles == {"睡前不看手机", "泡茶"}
    # Embedded tasks inherit the originating plan via plan_id.
    assert all(t["plan_id"] == data["id"] for t in data["tasks"])


def test_list_plans(authed_client: TestClient) -> None:
    """GET /plans 列出当前用户的计划。"""
    _create_plan(authed_client, title="计划A")
    _create_plan(authed_client, title="计划B")
    response = authed_client.get("/api/v1/plans")
    assert response.status_code == 200
    plans = response.json()
    titles = {p["title"] for p in plans}
    assert {"计划A", "计划B"}.issubset(titles)


def test_list_plans_status_filter(authed_client: TestClient) -> None:
    """GET /plans?status=archived 按 status 过滤。"""
    plan = _create_plan(authed_client, title="归档项")
    authed_client.patch(f"/api/v1/plans/{plan['id']}", json={"status": "archived"})
    _create_plan(authed_client, title="活跃项")

    archived = authed_client.get("/api/v1/plans?status=archived").json()
    assert {p["title"] for p in archived} == {"归档项"}
    active = authed_client.get("/api/v1/plans?status=active").json()
    assert {p["title"] for p in active} == {"活跃项"}


def test_get_plan_detail(authed_client: TestClient) -> None:
    """GET /plans/{id} 返回单个计划详情。响应包含嵌套 tasks。"""
    created = _create_plan(
        authed_client, title="详情计划", tasks=[{"title": "子任务1"}]
    )
    response = authed_client.get(f"/api/v1/plans/{created['id']}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == created["id"]
    assert data["title"] == "详情计划"
    assert len(data["tasks"]) == 1
    assert data["tasks"][0]["title"] == "子任务1"


def test_update_plan(authed_client: TestClient) -> None:
    """PATCH /plans/{id} 更新计划字段。"""
    created = _create_plan(authed_client, title="旧标题")
    response = authed_client.patch(
        f"/api/v1/plans/{created['id']}",
        json={"title": "新标题", "motivation": "新动力", "status": "completed"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "新标题"
    assert data["motivation"] == "新动力"
    assert data["status"] == "completed"


def test_delete_plan(authed_client: TestClient) -> None:
    """DELETE /plans/{id} 删除计划。随后 GET 返回 404。"""
    created = _create_plan(authed_client, title="待删除")
    delete_response = authed_client.delete(f"/api/v1/plans/{created['id']}")
    assert delete_response.status_code == 204
    get_response = authed_client.get(f"/api/v1/plans/{created['id']}")
    assert get_response.status_code == 404


def test_create_standalone_task(authed_client: TestClient) -> None:
    """POST /tasks 创建独立 task。该任务不隶属任何 plan。"""
    response = authed_client.post(
        "/api/v1/tasks",
        json={"title": "买菜", "due_date": "2026-08-10", "note": "记得带袋子"},
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "买菜"
    assert data["due_date"] == "2026-08-10"
    assert data["status"] == "pending"
    assert data["plan_id"] is None
    assert data["source"] == "manual"


def test_list_tasks_filter_by_plan(authed_client: TestClient) -> None:
    """GET /tasks?plan_id=... 只返回该 plan 下的任务。"""
    plan = _create_plan(authed_client, title="容器", tasks=[{"title": "归属任务"}])
    authed_client.post("/api/v1/tasks", json={"title": "游离任务"})
    response = authed_client.get(f"/api/v1/tasks?plan_id={plan['id']}")
    assert response.status_code == 200
    titles = [t["title"] for t in response.json()]
    assert titles == ["归属任务"]


def test_get_today_tasks(authed_client: TestClient) -> None:
    """GET /tasks/today 返回今日到期或无截止日的 pending 任务。"""
    today = date.today().isoformat()
    authed_client.post("/api/v1/tasks", json={"title": "今日到期", "due_date": today})
    authed_client.post("/api/v1/tasks", json={"title": "无截止日的 pending"})
    # 明天到期 -> 不应出现
    authed_client.post(
        "/api/v1/tasks", json={"title": "未来任务", "due_date": "2099-12-31"}
    )
    response = authed_client.get("/api/v1/tasks/today")
    assert response.status_code == 200
    titles = [t["title"] for t in response.json()]
    assert "今日到期" in titles
    assert "无截止日的 pending" in titles
    assert "未来任务" not in titles


def test_complete_task_sets_completed_at(authed_client: TestClient) -> None:
    """PATCH /tasks/{id} {status: done} 应置位 completed_at。"""
    create = authed_client.post("/api/v1/tasks", json={"title": "待完成"})
    task_id = create.json()["id"]
    response = authed_client.patch(
        f"/api/v1/tasks/{task_id}", json={"status": "done"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "done"
    assert data["completed_at"] is not None

    # Revert to pending clears completed_at.
    revert = authed_client.patch(
        f"/api/v1/tasks/{task_id}", json={"status": "pending"}
    )
    assert revert.status_code == 200
    assert revert.json()["completed_at"] is None


def test_update_task_fields(authed_client: TestClient) -> None:
    """PATCH /tasks/{id} 更新 title/note/due_date 字段。不带 status。"""
    create = authed_client.post("/api/v1/tasks", json={"title": "原标题"})
    task_id = create.json()["id"]
    response = authed_client.patch(
        f"/api/v1/tasks/{task_id}",
        json={"title": "新标题", "note": "新增备注", "due_date": "2026-09-01"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["title"] == "新标题"
    assert data["note"] == "新增备注"
    assert data["due_date"] == "2026-09-01"
    assert data["status"] == "pending"


def test_delete_task(authed_client: TestClient) -> None:
    """DELETE /tasks/{id} 删除独立任务。"""
    create = authed_client.post("/api/v1/tasks", json={"title": "待删除"})
    task_id = create.json()["id"]
    delete_response = authed_client.delete(f"/api/v1/tasks/{task_id}")
    assert delete_response.status_code == 204


def test_get_plan_404_for_nonexistent(authed_client: TestClient) -> None:
    """获取不存在的 plan 应 404。"""
    response = authed_client.get("/api/v1/plans/nonexistent-id")
    assert response.status_code == 404


def test_patch_task_404_for_nonexistent(authed_client: TestClient) -> None:
    """更新不存在的 task 应 404。"""
    response = authed_client.patch(
        "/api/v1/tasks/nonexistent-id", json={"status": "done"}
    )
    assert response.status_code == 404


def test_unauthenticated_rejected(api_client: TestClient) -> None:
    """未携带认证令牌访问受保护端点应 401。"""
    response = api_client.get("/api/v1/plans")
    assert response.status_code == 401


def test_user_isolation(api_client: TestClient) -> None:
    """一个用户创建的 plan 对另一用户不可见。验证 user_id 隔离。

    通过两个真实注册账号验证 list/get 不会越权。不使用 authed_client。
    authed_client 用 dependency override 固定 user_id=1 因此无法与真实注册混用。
    """

    def _register_login(email: str) -> dict[str, str]:
        api_client.post(
            "/api/v1/auth/register",
            json={"email": email, "password": "password123", "nickname": email},
        )
        resp = api_client.post(
            "/api/v1/auth/login", data={"username": email, "password": "password123"}
        )
        assert resp.status_code == 200, resp.text
        return {"Authorization": f"Bearer {resp.json()['access_token']}"}

    alice_headers = _register_login("alice@test.com")
    bob_headers = _register_login("bob@test.com")

    # Alice 创建一个私有 plan。
    created = api_client.post(
        "/api/v1/plans",
        json={"title": "私有计划"},
        headers=alice_headers,
    )
    assert created.status_code == 201
    plan_id = created.json()["id"]

    # Bob 看不到 Alice 的 plan。
    listing = api_client.get("/api/v1/plans", headers=bob_headers)
    assert listing.status_code == 200
    assert all(p["id"] != plan_id for p in listing.json())

    # Bob 直接请求 Alice 的 plan id -> 404 (越权视为不存在)。
    direct = api_client.get(f"/api/v1/plans/{plan_id}", headers=bob_headers)
    assert direct.status_code == 404


def test_list_tasks_filters_by_due_date_range(authed_client: TestClient) -> None:
    authed_client.post("/api/v1/tasks", json={"title": "周内任务", "due_date": "2026-08-26"})
    authed_client.post("/api/v1/tasks", json={"title": "下周任务", "due_date": "2026-09-02"})
    authed_client.post("/api/v1/tasks", json={"title": "无期限任务"})

    listing = authed_client.get(
        "/api/v1/tasks",
        params={"date_from": "2026-08-25", "date_to": "2026-08-31"},
    )
    assert listing.status_code == 200
    titles = [t["title"] for t in listing.json()]
    assert titles == ["周内任务"]

    open_ended = authed_client.get("/api/v1/tasks", params={"date_to": "2026-08-25"})
    assert open_ended.status_code == 200
    assert [t["title"] for t in open_ended.json()] == []


# ── PR4: metric columns (recurrence/target/actual) ────────────────────


def test_create_plan_with_recurrence_and_target(authed_client: TestClient) -> None:
    """POST /plans 携带周期与目标值字段应透出。"""
    data = _create_plan(
        authed_client,
        title="早睡挑战",
        recurrence="weekly:2,4",
        target_value=4,
        target_unit="h",
        target_period="weekly",
    )
    assert data["recurrence"] == "weekly:2,4"
    assert data["target_value"] == 4
    assert data["target_unit"] == "h"
    assert data["target_period"] == "weekly"


def test_create_plan_defaults_metric_fields_to_none(authed_client: TestClient) -> None:
    """不携带度量字段时响应应为 None 而非缺失。"""
    data = _create_plan(authed_client, title="极简计划")
    assert data["recurrence"] is None
    assert data["target_value"] is None
    assert data["target_unit"] is None
    assert data["target_period"] is None


def test_create_plan_rejects_bad_recurrence(authed_client: TestClient) -> None:
    """非法周期标记应 422。"""
    response = authed_client.post(
        "/api/v1/plans", json={"title": "x", "recurrence": "monthly"}
    )
    assert response.status_code == 422


def test_update_plan_recurrence(authed_client: TestClient) -> None:
    """PATCH /plans/{id} 可更新周期。"""
    plan = _create_plan(authed_client, title="跑步")
    response = authed_client.patch(
        f"/api/v1/plans/{plan['id']}", json={"recurrence": "daily"}
    )
    assert response.status_code == 200
    assert response.json()["recurrence"] == "daily"


def test_complete_task_records_actual_value(authed_client: TestClient) -> None:
    """完成任务时记录实际值，响应透出 actual_value。"""
    plan = _create_plan(authed_client, title="阅读")
    create = authed_client.post(
        "/api/v1/tasks", json={"title": "读书半小时", "plan_id": plan["id"]}
    )
    task_id = create.json()["id"]

    response = authed_client.patch(
        f"/api/v1/tasks/{task_id}", json={"status": "done", "actual_value": 2.5}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "done"
    assert body["completed_at"] is not None
    assert body["actual_value"] == 2.5

    # 计划详情内嵌任务同样带 actual_value。
    detail = authed_client.get(f"/api/v1/plans/{plan['id']}")
    assert detail.json()["tasks"][0]["actual_value"] == 2.5


def test_complete_task_without_actual_value(authed_client: TestClient) -> None:
    """无实际值完成时 actual_value 保持 None（按 1 次计数由前端兜底）。"""
    create = authed_client.post("/api/v1/tasks", json={"title": "散步"})
    task_id = create.json()["id"]
    response = authed_client.patch(
        f"/api/v1/tasks/{task_id}", json={"status": "done"}
    )
    assert response.json()["actual_value"] is None


def test_task_response_includes_actual_value_default(authed_client: TestClient) -> None:
    """普通任务响应带 actual_value=None 字段。"""
    create = authed_client.post("/api/v1/tasks", json={"title": "默认值检查"})
    assert create.json()["actual_value"] is None
