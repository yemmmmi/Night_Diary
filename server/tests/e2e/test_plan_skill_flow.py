"""E2E tests for the plan skill full vertical slice (V3 P2).

Tests the end-to-end plan workflow through the real HTTP stack (real
JWT auth, real settings, real database) without mocking the service
layer. They complement the dependency-override based unit route tests
in ``tests/unit/api/test_plan_routes.py`` by exercising the full
vertical slice including bootstrap and authentication.

Covered flows:
- Plan CRUD full cycle (create -> read -> update -> delete)
- Today tasks aggregation (due today OR pending without due_date)
- Agent-sourced audit trail (source / created_from_conversation_id)
- Cascade delete (deleting a plan removes its tasks)
- Task completion timestamp (completed_at set/cleared on status flips)
"""

from __future__ import annotations

from datetime import date

from fastapi.testclient import TestClient


def test_plan_crud_full_cycle(e2e_client: TestClient) -> None:
    """Plan full CRUD cycle - create then read then update then delete."""
    # Create
    create_resp = e2e_client.post(
        "/api/v1/plans",
        json={
            "title": "测试计划",
            "motivation": "e2e 测试",
            "tasks": [{"title": "task1"}, {"title": "task2"}],
        },
    )
    assert create_resp.status_code == 201, create_resp.text
    plan_id = create_resp.json()["id"]
    assert create_resp.json()["source"] == "manual"  # 默认值

    # Read
    get_resp = e2e_client.get(f"/api/v1/plans/{plan_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["title"] == "测试计划"
    assert len(get_resp.json()["tasks"]) == 2

    # Update
    patch_resp = e2e_client.patch(
        f"/api/v1/plans/{plan_id}",
        json={"status": "archived"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["status"] == "archived"

    # Delete
    del_resp = e2e_client.delete(f"/api/v1/plans/{plan_id}")
    assert del_resp.status_code == 204

    # 确认已删
    get_after = e2e_client.get(f"/api/v1/plans/{plan_id}")
    assert get_after.status_code == 404


def test_today_tasks_aggregation(e2e_client: TestClient) -> None:
    """今日待办聚合 - 今日到期 + 无截止日的 pending."""
    today = date.today().isoformat()

    e2e_client.post(
        "/api/v1/tasks",
        json={"title": "今日到期", "due_date": today},
    )
    e2e_client.post(
        "/api/v1/tasks",
        json={"title": "无截止"},
    )
    # 已完成的任务不应出现在 today
    done_resp = e2e_client.post(
        "/api/v1/tasks",
        json={"title": "已完成的任务"},
    )
    e2e_client.patch(
        f"/api/v1/tasks/{done_resp.json()['id']}",
        json={"status": "done"},
    )

    resp = e2e_client.get("/api/v1/tasks/today")
    assert resp.status_code == 200
    titles = [t["title"] for t in resp.json()]
    assert "今日到期" in titles
    assert "无截止" in titles
    assert "已完成的任务" not in titles  # done 不算今日待办


def test_agent_sourced_plan_audited(e2e_client: TestClient) -> None:
    """source=agent 的计划应正确记录审计字段."""
    resp = e2e_client.post(
        "/api/v1/plans",
        json={
            "title": "AI 建议的计划",
            "source": "agent",
            "created_from_conversation_id": "conv-abc-123",
            "tasks": [{"title": "建议 task", "source": "agent"}],
        },
    )
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert data["source"] == "agent"
    assert data["tasks"][0]["source"] == "agent"


def test_cascade_delete_removes_tasks(e2e_client: TestClient) -> None:
    """删 plan 应级联删其下所有 tasks."""
    create = e2e_client.post(
        "/api/v1/plans",
        json={
            "title": "级联测试",
            "tasks": [{"title": "t1"}, {"title": "t2"}, {"title": "t3"}],
        },
    )
    plan_id = create.json()["id"]

    # 确认 tasks 存在
    tasks = e2e_client.get(f"/api/v1/tasks?plan_id={plan_id}")
    assert len(tasks.json()) == 3

    # 删 plan
    e2e_client.delete(f"/api/v1/plans/{plan_id}")

    # tasks 应也没了
    tasks_after = e2e_client.get(f"/api/v1/tasks?plan_id={plan_id}")
    assert len(tasks_after.json()) == 0


def test_task_completion_sets_completed_at(e2e_client: TestClient) -> None:
    """标记 task 完成应设置 completed_at 时间戳."""
    create = e2e_client.post(
        "/api/v1/tasks",
        json={"title": "待完成"},
    )
    task_id = create.json()["id"]
    assert create.json()["completed_at"] is None

    patch = e2e_client.patch(
        f"/api/v1/tasks/{task_id}",
        json={"status": "done"},
    )
    assert patch.status_code == 200
    assert patch.json()["status"] == "done"
    assert patch.json()["completed_at"] is not None


def test_task_can_be_undone(e2e_client: TestClient) -> None:
    """完成的 task 可以重新标记为 pending, completed_at 清空."""
    create = e2e_client.post(
        "/api/v1/tasks",
        json={"title": "可切换"},
    )
    task_id = create.json()["id"]

    # 完成
    e2e_client.patch(f"/api/v1/tasks/{task_id}", json={"status": "done"})

    # 撤销
    undone = e2e_client.patch(
        f"/api/v1/tasks/{task_id}",
        json={"status": "pending"},
    )
    assert undone.json()["status"] == "pending"
    assert undone.json()["completed_at"] is None
