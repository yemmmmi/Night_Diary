"""E2E test: weekly report plan section setup (V3 P3).

Full weekly report generation requires a real LLM call (network + API key),
which the E2E environment does not have. Instead this test drives the real
HTTP stack to create a plan+task, then exercises the plan-data injection path
(``weekly_service._plans_in_week`` + ``_build_weekly_content``) against the
real app database session — verifying the integration does not crash and
injects the 「【本周计划执行】」 block.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.infrastructure.models import PlanRow
from app.services import weekly_service


def test_plan_data_injection_does_not_crash(e2e_client: TestClient) -> None:
    """创建 plan/task 后, 周报数据注入逻辑不应崩溃且正确注入计划段落."""
    # 1. 通过真实 HTTP 栈创建一个带任务的计划.
    create = e2e_client.post(
        "/api/v1/plans",
        json={
            "title": "测试计划",
            "tasks": [{"title": "测试任务"}],
        },
    )
    assert create.status_code == 201, create.text
    plan_id = create.json()["id"]

    # 2. 在真实 app DB 上跑数据注入逻辑, 取出 user_id 以匹配多租户隔离.
    container = e2e_client.app.state.container
    db = container.session()
    try:
        plan = db.query(PlanRow).filter(PlanRow.id == plan_id).first()
        assert plan is not None
        user_id = plan.user_id

        start, end = weekly_service.week_bounds()
        plans_data = weekly_service._plans_in_week(
            db, user_id=user_id, start=start, end=end
        )
        assert len(plans_data["active_plans"]) >= 1
        assert len(plans_data["week_tasks"]) >= 1

        content = weekly_service._build_weekly_content(
            start, end, [], [], plans_data=plans_data
        )
        assert "【本周计划执行】" in content
        assert "测试计划" in content
    finally:
        db.close()
