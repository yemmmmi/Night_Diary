# 日记/周记/回顾合并重构 + 计划板块入列 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将「日记/周记/回顾」三个板块合并为统一时间轴（日/周/月三级缩放），计划板块升为一级导航并渲染 `source_refs` 溯源，记忆库吸收卡片浏览，全局执行"减法纪律"。

**Architecture:** 前端以新 `TimelineScene`（路由 `/`，`?view=day|week|month&date=YYYY-MM-DD`）为骨架，子视图组件放 `src/features/timeline/`，视图/日期状态收敛到新的 `timeline` Pinia store 并与 URL query 双向同步；旧页面（HomeScene/WeeklyScene/ReviewScene）的可用逻辑分批迁移后删除。后端仅做铺垫：日记/任务/心情趋势接口增加日期范围参数，周报增加结构化计划执行字段（新 JSON 列 + alembic 迁移）。

**Tech Stack:** Vue 3 + TypeScript + Pinia + Vue Router + Tailwind + vitest（前端）；FastAPI + SQLAlchemy + Alembic + pytest（后端）。

**设计规格（本计划的唯一依据）:** `docs/superpowers/specs/2026-08-25-merge-diary-weekly-review-design.md`

---

## 0. 全局约定

### 0.1 命令速查

| 操作 | 命令 | 工作目录 |
|------|------|----------|
| 前端单测 | `npx vitest run src/__tests__/<file>.spec.ts` | `d:\work\night_diary_v2` |
| 前端全量测试 | `npm test` | `d:\work\night_diary_v2` |
| 前端类型检查 | `npm run type-check` | `d:\work\night_diary_v2` |
| 前端 Lint | `npm run lint` | `d:\work\night_diary_v2` |
| 后端单测 | `.\.venv\Scripts\python.exe -m pytest tests/unit/... -v` | `d:\work\night_diary_v2\server` |
| 后端全量测试 | `.\.venv\Scripts\python.exe -m pytest` | `d:\work\night_diary_v2\server` |
| 数据库迁移 | `.\.venv\Scripts\python.exe -m alembic upgrade head` | `d:\work\night_diary_v2\server` |

### 0.2 分支与 PR 策略

每个 PR 一个分支（`feature/merge-diary-weekly-review-pr1` … `feature/merge-diary-weekly-review-pr6`），按顺序合并。每个 PR 独立可测可合并，**必须在前一个 PR 合并后开工**（后端参数是前端时间轴的数据依赖）。PR 描述按项目模板包含：标题、功能描述、实现思路、测试方式。commit 使用 Conventional Commits（`feat:` / `test:` / `refactor:` / `chore:`）。

### 0.3 切分顺序与无回归窗口的保证

本计划的 PR 切分与设计规格第 12 节完全一致：PR-1 后端铺垫 → PR-2 时间轴骨架 → PR-3 周视图 → PR-4 月视图+详情面板 → PR-5 计划场景 → PR-6 记忆库吸收卡片+回顾页清理。优先级对应关系：P0 = PR-1/PR-2，P1 = PR-3/PR-4，P2 = PR-5/PR-6。

无功能真空期的保证来自 **PR 内部的任务排序——先建新去处，后删旧页面**：PR-2 删 HomeScene 前 WeekView 已落地；PR-3 删 WeeklyScene 前周信卡片已完整；PR-6 删 ReviewScene 前 CardsSection 已迁移（Task 6.1/6.2 先于 Task 6.3）。回顾页四类功能在删除时各有去处：月历→MonthView（PR-4）、时间线→时间轴日/周/月视图（PR-2/4）、卡片→CardsSection（PR-6）、详情面板→DetailPanel（PR-4）。

### 0.4 现状关键事实（写代码前必读）

- 路由 `/` → `HomeScene.vue`（周看板，`weekOffset` 翻周）；`/weekly` → `WeeklyScene.vue`；`/review`、`/review/:diaryId` → `ReviewScene.vue`（mode: calendar/timeline/cards）；`/plan` → `src/features/plan/PlanScene.vue`（孤儿路由，不在导航）。
- 导航写死在 `src/shared/components/NavTabs.vue` 的 `tabs` 数组（6 项）；`src/App.vue` 用 `tabRouteNames` / `tabViewNames` 控制 keep-alive。
- `DiaryScene.vue`（`/write/:id`）当前不含任何任务元素——保持为零。
- 周报生成流程：`weekly_service.create_weekly_report()` 已调用 `_plans_in_week()` 得到 `plans_data`，仅用于拼 prompt 文本；`WeeklyReportRow` 无结构化列。
- `listDiaryEntries` / `listTasks` / `getMoodTrends` 后端均无日期范围参数。
- 前端测试约定：`src/__tests__/*.spec.ts`，happy-dom + globals，用 `vi.mock('@/shared/api/xxx')` 模块级 mock + `helpers/mockAxiosClient`（仅 API 层测试需要）。
- 后端测试约定：API 测试用 `authed_client` fixture（依赖覆盖 `get_current_user`）；服务层测试用 `db_session` + `StubLLMClient` + `_FakeContainer`（见 `tests/unit/services/test_weekly_service.py`）。
- 最新 alembic 迁移：`008_daily_modes`（revision id `"008_daily_modes"`）。
- `2026-08-24` 是周一（测试fixture 用这个日期族：2026-08-24 周一 ~ 2026-08-30 周日）。

---

## PR-1 后端铺垫（P0）

> 内容：entries 日期范围参数、tasks 日期范围参数、mood-trends 日期范围参数、weekly 结构化计划字段 + alembic 迁移。全部后端，前端零改动。

### Task 1.1: diary entries 接口支持 date_from / date_to

**Files:**
- Modify: `server/app/api/v1/diary.py:15-23`
- Modify: `server/app/services/diary_service.py:93-108`
- Test: `server/tests/unit/api/test_diary_routes.py`

- [ ] **Step 1: 写失败测试**

在 `server/tests/unit/api/test_diary_routes.py` 末尾追加（该文件已有 `authed_client` 的使用先例，无需新增 import）：

```python
def test_list_entries_filters_by_date_range(authed_client: TestClient) -> None:
    authed_client.post("/api/v1/diary/entries", json={"content": "周一的日记", "date": "2026-08-24"})
    authed_client.post("/api/v1/diary/entries", json={"content": "周二的日记", "date": "2026-08-25"})
    authed_client.post("/api/v1/diary/entries", json={"content": "九月的一天", "date": "2026-09-01"})
    authed_client.post("/api/v1/diary/entries", json={"content": "无日期日记"})

    both = authed_client.get(
        "/api/v1/diary/entries",
        params={"date_from": "2026-08-24", "date_to": "2026-08-25"},
    )
    assert both.status_code == 200
    dates = sorted(e["date"] for e in both.json())
    assert dates == ["2026-08-24", "2026-08-25"]

    from_only = authed_client.get(
        "/api/v1/diary/entries", params={"date_from": "2026-08-26"}
    )
    assert from_only.status_code == 200
    assert [e["date"] for e in from_only.json()] == ["2026-09-01"]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/api/test_diary_routes.py::test_list_entries_filters_by_date_range -v`
Expected: FAIL —— 未知的 `date_from` 参数被 FastAPI 忽略，返回全部 4 条记录，断言 `dates == [...]` 失败。

- [ ] **Step 3: 实现路由层**

`server/app/api/v1/diary.py` 的 `list_entries` 改为（文件顶部 import 增加 `datetime`，即 `import datetime`）：

```python
@router.get("/entries", response_model=list[DiaryResponse])
def list_entries(
    db: DbDep,
    user: CurrentUserDep,
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    date_from: datetime.date | None = Query(default=None),
    date_to: datetime.date | None = Query(default=None),
) -> list[DiaryResponse]:
    rows = diary_service.list_entries(
        db,
        user_id=str(user.id),
        skip=skip,
        limit=limit,
        date_from=date_from,
        date_to=date_to,
    )
    return [diary_to_response(row) for row in rows]
```

- [ ] **Step 4: 实现服务层**

`server/app/services/diary_service.py` 的 `list_entries`（93-108 行）改为：

```python
def list_entries(
    db: Session,
    *,
    user_id: str,
    skip: int = 0,
    limit: int = 20,
    date_from: datetime.date | None = None,
    date_to: datetime.date | None = None,
) -> list[DiaryEntryRow]:
    query = db.query(DiaryEntryRow).filter(DiaryEntryRow.user_id == user_id)
    if date_from is not None:
        query = query.filter(DiaryEntryRow.date >= date_from)
    if date_to is not None:
        query = query.filter(DiaryEntryRow.date <= date_to)
    return (
        query.order_by(desc(DiaryEntryRow.created_at))
        .offset(skip)
        .limit(limit)
        .all()
    )
```

注意：该文件已 import `datetime` 的可能性需确认——查看文件顶部，若只有 `from datetime import datetime` 则改为 `import datetime`（`create_entry` 的 `entry_date` 参数用的是 `date` 对象，由路由层 body.date 传入，不受影响）。

- [ ] **Step 5: 运行测试确认通过**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/api/test_diary_routes.py -v`
Expected: 全部 PASS（含既有 2 个测试）。

- [ ] **Step 6: 提交**

```bash
git add server/app/api/v1/diary.py server/app/services/diary_service.py server/tests/unit/api/test_diary_routes.py
git commit -m "feat(api): add date_from/date_to range filter to diary entries"
```

### Task 1.2: tasks 接口支持 date_from / date_to（按 due_date 过滤）

**Files:**
- Modify: `server/app/api/v1/plan.py:138-148`（`list_tasks` 路由）
- Modify: `server/app/services/plan_service.py:126-139`（`list_tasks` 服务）
- Test: `server/tests/unit/api/test_plan_routes.py`

- [ ] **Step 1: 写失败测试**

在 `server/tests/unit/api/test_plan_routes.py` 末尾追加：

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/api/test_plan_routes.py::test_list_tasks_filters_by_due_date_range -v`
Expected: FAIL —— 日期参数被忽略，返回全部 3 条任务。

- [ ] **Step 3: 实现路由层**

`server/app/api/v1/plan.py` 的 `list_tasks` 改为（文件顶部增加 `import datetime`）：

```python
@tasks_router.get("", response_model=list[TaskResponse])
def list_tasks(
    db: DbDep,
    user: CurrentUserDep,
    plan_id: str | None = Query(default=None),
    task_status: str | None = Query(default=None, alias="status"),
    date_from: datetime.date | None = Query(default=None),
    date_to: datetime.date | None = Query(default=None),
) -> list[TaskResponse]:
    tasks = plan_service.list_tasks(
        db,
        user_id=str(user.id),
        plan_id=plan_id,
        status=task_status,
        date_from=date_from,
        date_to=date_to,
    )
    return [_task_to_response(t) for t in tasks]
```

- [ ] **Step 4: 实现服务层**

`server/app/services/plan_service.py` 的 `list_tasks`（126-139 行）改为：

```python
def list_tasks(
    db: Session,
    *,
    user_id: str,
    plan_id: str | None = None,
    status: str | None = None,
    date_from: datetime.date | None = None,
    date_to: datetime.date | None = None,
) -> list[TaskRow]:
    stmt = select(TaskRow).where(TaskRow.user_id == user_id)
    if plan_id:
        stmt = stmt.where(TaskRow.plan_id == plan_id)
    if status:
        stmt = stmt.where(TaskRow.status == status)
    if date_from is not None:
        stmt = stmt.where(TaskRow.due_date >= date_from)
    if date_to is not None:
        stmt = stmt.where(TaskRow.due_date <= date_to)
    stmt = stmt.order_by(TaskRow.created_at.desc())
    return list(db.scalars(stmt))
```

（语义：按 `due_date` 落在 `[date_from, date_to]` 过滤；`due_date` 为 NULL 的任务在任一过滤生效时被排除。文件顶部 datetime import 方式与现状保持一致，若现为 `from datetime import datetime` 则加 `date`。）

- [ ] **Step 5: 运行测试确认通过**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/api/test_plan_routes.py -v`
Expected: 全部 PASS。

- [ ] **Step 6: 提交**

```bash
git add server/app/api/v1/plan.py server/app/services/plan_service.py server/tests/unit/api/test_plan_routes.py
git commit -m "feat(api): add due-date range filter to tasks list endpoint"
```

### Task 1.3: mood-trends 接口支持 date_from / date_to

**Files:**
- Modify: `server/app/api/v1/card.py:189-195`（`mood_trends` 路由）
- Modify: `server/app/services/card_service.py:503-538`（`get_mood_trends` 服务）
- Test: `server/tests/unit/api/test_card_stats_routes.py`（新建）、`server/tests/unit/services/test_card_stats_mood.py`（新建）

- [ ] **Step 1: 写失败的路由层测试**

新建 `server/tests/unit/api/test_card_stats_routes.py`：

```python
"""Card stats routes: mood-trends query parameter wiring."""

from fastapi.testclient import TestClient


def test_mood_trends_rejects_one_sided_date_range(authed_client: TestClient) -> None:
    response = authed_client.get(
        "/api/v1/cards/stats/mood-trends", params={"date_from": "2026-08-01"}
    )
    assert response.status_code == 422


def test_mood_trends_accepts_full_date_range(authed_client: TestClient) -> None:
    response = authed_client.get(
        "/api/v1/cards/stats/mood-trends",
        params={"date_from": "2020-01-01", "date_to": "2020-01-07"},
    )
    assert response.status_code == 200
    assert response.json() == []
```

- [ ] **Step 2: 运行测试确认失败**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/api/test_card_stats_routes.py -v`
Expected: 第一个测试 FAIL（当前未知参数被忽略，返回 200 而非 422）；第二个 PASS。

- [ ] **Step 3: 实现路由层**

`server/app/api/v1/card.py` 的 `mood_trends` 改为（顶部 fastapi import 增加 `HTTPException`，并增加 `import datetime`）：

```python
@router.get("/stats/mood-trends", response_model=list[dict[str, Any]])
def mood_trends(
    db: DbDep,
    user: CurrentUserDep,
    days: int = Query(30, ge=7, le=365),
    date_from: datetime.date | None = Query(default=None),
    date_to: datetime.date | None = Query(default=None),
) -> list[dict[str, Any]]:
    """按天聚合心情均值。date_from/date_to 需成对出现；成对时优先于 days。"""
    if (date_from is None) != (date_to is None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="date_from and date_to must be provided together",
        )
    return card_service.get_mood_trends(
        db,
        user_id=str(user.id),
        days=days,
        date_from=date_from,
        date_to=date_to,
    )
```

- [ ] **Step 4: 写服务层测试并实现**

新建 `server/tests/unit/services/test_card_stats_mood.py`：

```python
"""card_service.get_mood_trends 的日期窗口语义."""

from datetime import UTC, date, datetime, timedelta

from app.services import card_service


def test_get_mood_trends_days_window(db_session) -> None:
    card_service.create_card(
        db_session, user_id="default", emotion="平静", event_summary="散步", mood_score=0.6
    )
    points = card_service.get_mood_trends(db_session, user_id="default", days=7)
    assert len(points) == 1
    assert points[0]["card_count"] == 1
    assert abs(points[0]["avg_mood"] - 0.6) < 1e-6


def test_get_mood_trends_explicit_range_overrides_days(db_session) -> None:
    card_service.create_card(
        db_session, user_id="default", emotion="开心", event_summary="聚餐", mood_score=0.9
    )
    today = datetime.now(UTC).date()
    in_range = card_service.get_mood_trends(
        db_session,
        user_id="default",
        days=7,
        date_from=today - timedelta(days=6),
        date_to=today,
    )
    assert len(in_range) == 1

    out_of_range = card_service.get_mood_trends(
        db_session,
        user_id="default",
        days=7,
        date_from=date(2020, 1, 1),
        date_to=date(2020, 1, 7),
    )
    assert out_of_range == []
```

然后改 `server/app/services/card_service.py` 的 `get_mood_trends`（503-538 行）。函数内现有的局部 `from sqlalchemy import func, text` 保留 `func`、删除 `text`；确保模块可用的 datetime 导入（顶部已有 `from datetime import datetime` 的话，补成 `from datetime import UTC, date, datetime, time, timedelta`，以文件现状为准）：

```python
def get_mood_trends(
    db: Session,
    *,
    user_id: str,
    days: int = 30,
    date_from: date | None = None,
    date_to: date | None = None,
) -> list[dict[str, Any]]:
    """Get daily average mood scores for trend chart.

    Returns a list of {date, avg_mood, card_count} sorted by date ascending.
    When ``date_from``/``date_to`` are both given, the window is fixed to that
    inclusive range (overrides ``days``); otherwise the window is the last
    ``days`` days ending today.
    """
    from sqlalchemy import func

    if date_from is not None and date_to is not None:
        start, end = date_from, date_to
    else:
        end = datetime.now(UTC).date()
        start = end - timedelta(days=days - 1)

    start_dt = datetime.combine(start, time.min)
    end_dt = datetime.combine(end, time.max)

    rows = (
        db.query(
            func.date(MemoryCardRow.created_at).label("day"),
            func.avg(MemoryCardRow.mood_score).label("avg_mood"),
            func.count(MemoryCardRow.card_id).label("card_count"),
        )
        .filter(MemoryCardRow.user_id == user_id)
        .filter(MemoryCardRow.created_at >= start_dt)
        .filter(MemoryCardRow.created_at <= end_dt)
        .group_by(func.date(MemoryCardRow.created_at))
        .order_by(func.date(MemoryCardRow.created_at).asc())
        .all()
    )
    return [
        {
            "date": str(row.day),
            "avg_mood": round(float(row.avg_mood), 3),
            "card_count": row.card_count,
        }
        for row in rows
    ]
```

（行为变化说明：`days` 模式新增了 `end_dt` 上界——原实现只有下界。对未来时间戳的卡片不再计入，实际数据中不存在，风险为零。）

- [ ] **Step 5: 运行测试确认通过**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/api/test_card_stats_routes.py tests/unit/services/test_card_stats_mood.py -v`
Expected: 全部 PASS。

- [ ] **Step 6: 提交**

```bash
git add server/app/api/v1/card.py server/app/services/card_service.py server/tests/unit/api/test_card_stats_routes.py server/tests/unit/services/test_card_stats_mood.py
git commit -m "feat(api): support explicit date range on mood-trends endpoint"
```

### Task 1.4: weekly 响应新增结构化计划执行字段

**Files:**
- Modify: `server/app/api/schemas.py:220-232`（`WeeklyReportResponse` + 新 schema）
- Modify: `server/app/infrastructure/models/weekly_report.py:19-34`（新增两列）
- Modify: `server/app/api/mappers.py:99-101`（`weekly_to_response`）
- Modify: `server/app/services/weekly_service.py`（`create_weekly_report` 填充 JSON 列）
- Test: `server/tests/unit/services/test_weekly_service.py`

- [ ] **Step 1: 写失败测试**

在 `server/tests/unit/services/test_weekly_service.py` 末尾追加（文件已 import `json` 的话复用，否则顶部加 `import json`；`weekly_to_response` 从 `app.api.mappers` 导入）：

```python
def test_create_weekly_report_persists_plan_struct(db_session) -> None:
    """生成周报时把计划执行快照写入结构化 JSON 列，并能被 mapper 还原."""
    plan = plan_service.create_plan(
        db_session,
        user_id="default",
        title="早睡挑战",
        source_refs=[{"type": "diary", "id": 1, "date": "2026-08-24", "snippet": "最近总是熬夜"}],
    )
    plan_service.create_task(db_session, user_id="default", plan_id=plan.id, title="11点前睡")
    plan_service.create_task(db_session, user_id="default", plan_id=None, title="周末散步")
    _seed_week(db_session)

    row = weekly_service.create_weekly_report(
        db_session, user_id="default", planner=_planner()
    )

    execs = json.loads(row.plan_executions_json)
    assert len(execs) == 1
    assert execs[0]["plan_id"] == plan.id
    assert execs[0]["title"] == "早睡挑战"
    assert execs[0]["total"] == 1
    assert execs[0]["done"] == 0
    assert execs[0]["source_refs"][0]["type"] == "diary"

    tasks = json.loads(row.week_tasks_json)
    assert [t["title"] for t in tasks] == ["周末散步"]
    assert tasks[0]["status"] == "pending"
    assert tasks[0]["source"] == "manual"

    response = weekly_to_response(row)
    assert response.plan_executions[0].title == "早睡挑战"
    assert response.plan_executions[0].source_refs[0].date == "2026-08-24"
    assert response.week_tasks[0].task_id == tasks[0]["task_id"]


def test_weekly_to_response_defaults_for_legacy_rows(db_session) -> None:
    """旧周报行（JSON 列为 NULL）映射后结构化字段为空数组而非报错."""
    from datetime import UTC, datetime

    from app.infrastructure.models.weekly_report import WeeklyReportRow

    row = WeeklyReportRow(
        user_id="default",
        period_start=date(2026, 8, 17),
        period_end=date(2026, 8, 23),
        content="旧周报",
        diary_count=1,
        card_count=0,
        created_at=datetime.now(UTC),
    )
    db_session.add(row)
    db_session.commit()
    db_session.refresh(row)

    response = weekly_to_response(row)
    assert response.plan_executions == []
    assert response.week_tasks == []
```

（若文件顶部已有 `from datetime import date` 则复用；`_seed_week` 与 `_planner` 是该文件已有 fixture/工具。）

- [ ] **Step 2: 运行测试确认失败**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/services/test_weekly_service.py::test_create_weekly_report_persists_plan_struct -v`
Expected: FAIL —— `WeeklyReportRow` 没有 `plan_executions_json` 属性（AttributeError）。

- [ ] **Step 3: 新增 schema**

`server/app/api/schemas.py` 在 `WeeklyReportResponse`（220 行附近）之前插入，并给 `WeeklyReportResponse` 追加两个可选字段：

```python
class PlanExecutionSummary(BaseModel):
    """Snapshot of one plan's execution within a weekly report period."""

    plan_id: str
    title: str
    done: int
    total: int
    source_refs: list[SourceRef] = Field(default_factory=list)


class WeekTaskItem(BaseModel):
    """Snapshot of one standalone task with in-week activity."""

    task_id: str
    title: str
    status: str  # pending | done | skipped
    source: str  # manual | agent
    due_date: datetime.date | None = None


class WeeklyReportResponse(BaseModel):
    id: int
    period_start: datetime.date
    period_end: datetime.date
    content: str
    diary_count: int
    card_count: int
    avg_mood: float | None
    token_cost: int | None
    execution_tier: str | None
    created_at: datetime.datetime
    plan_executions: list[PlanExecutionSummary] = Field(default_factory=list)
    week_tasks: list[WeekTaskItem] = Field(default_factory=list)

    model_config = {"from_attributes": True}
```

注意：`SourceRef` 定义在 schemas.py 353 行（`WeeklyReportResponse` 之后），Python 运行时类体注解延迟求值（`from __future__ import annotations` 已在文件顶部，需确认；若无则把 `SourceRef` 定义上移到本类之前，或依赖 Pydantic 的字符串前向引用——实测以 `from __future__ import annotations` 存在与否决定，简单起见可将 `PlanExecutionSummary`/`WeekTaskItem` 直接放在 `SourceRef`（353 行）之后、`WeeklyReportResponse` 保持原位只加字段）。

- [ ] **Step 4: 新增模型列**

`server/app/infrastructure/models/weekly_report.py` 的 `WeeklyReportRow` 追加（顶部 sa 类型 import 里补 `Text` 若缺失）：

```python
    plan_executions_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    week_tasks_json: Mapped[str | None] = mapped_column(Text, nullable=True)
```

- [ ] **Step 5: 生成时填充**

`server/app/services/weekly_service.py`：顶部加 `import json`。在 `_plans_in_week`（118 行）之后新增两个纯函数：

```python
def _plan_executions_snapshot(plans_data: PlansInWeek) -> list[dict]:
    """Structured plan execution summary for the weekly response."""
    items: list[dict] = []
    for plan in plans_data.get("active_plans", []):
        done = sum(1 for t in plan.tasks if t.status == "done")
        items.append(
            {
                "plan_id": plan.id,
                "title": plan.title,
                "done": done,
                "total": len(plan.tasks),
                "source_refs": json.loads(plan.source_refs_json or "[]"),
            }
        )
    return items


def _week_tasks_snapshot(plans_data: PlansInWeek) -> list[dict]:
    """Standalone (plan_id=None) task snapshots; plan tasks are aggregated above."""
    items: list[dict] = []
    for task in plans_data.get("week_tasks", []):
        if task.plan_id is None:
            items.append(
                {
                    "task_id": task.id,
                    "title": task.title,
                    "status": task.status,
                    "source": task.source,
                    "due_date": task.due_date.isoformat() if task.due_date else None,
                }
            )
    return items
```

`create_weekly_report`（254 行起）中的 `WeeklyReportRow(...)` 构造（280-291 行）追加两个实参：

```python
    row = WeeklyReportRow(
        user_id=user_id,
        period_start=start,
        period_end=end,
        content=result.reply,
        diary_count=len(diaries),
        card_count=len(cards),
        avg_mood=_avg_mood(cards),
        token_cost=result.token_cost,
        execution_tier=result.execution_tier,
        created_at=datetime.now(UTC),
        plan_executions_json=json.dumps(
            _plan_executions_snapshot(plans_data), ensure_ascii=False
        ),
        week_tasks_json=json.dumps(
            _week_tasks_snapshot(plans_data), ensure_ascii=False
        ),
    )
```

（`regenerate_weekly_report` 走删除后重建，自动获得同样行为。）

- [ ] **Step 6: 修改 mapper**

`server/app/api/mappers.py:99-101` 的 `weekly_to_response` 改为（该文件已 `import json`）：

```python
def weekly_to_response(row: WeeklyReportRow) -> WeeklyReportResponse:
    return WeeklyReportResponse(
        id=row.id,
        period_start=row.period_start,
        period_end=row.period_end,
        content=row.content,
        diary_count=row.diary_count,
        card_count=row.card_count,
        avg_mood=row.avg_mood,
        token_cost=row.token_cost,
        execution_tier=row.execution_tier,
        created_at=row.created_at,
        plan_executions=json.loads(row.plan_executions_json or "[]"),
        week_tasks=json.loads(row.week_tasks_json or "[]"),
    )
```

- [ ] **Step 7: 运行测试确认通过**

Run: `.\.venv\Scripts\python.exe -m pytest tests/unit/services/test_weekly_service.py tests/e2e/test_weekly_plan_section.py -v`
Expected: 全部 PASS（既有测试不受影响——`_build_weekly_content` 未改动）。

- [ ] **Step 8: 提交**

```bash
git add server/app/api/schemas.py server/app/infrastructure/models/weekly_report.py server/app/api/mappers.py server/app/services/weekly_service.py server/tests/unit/services/test_weekly_service.py
git commit -m "feat(api): persist structured plan-execution snapshot in weekly reports"
```

### Task 1.5: alembic 迁移 009

**Files:**
- Create: `server/alembic/versions/009_weekly_plan_struct.py`

- [ ] **Step 1: 新建迁移文件**

```python
"""Add structured plan-execution columns to weekly_reports.

Revision ID: 009_weekly_plan_struct
Revises: 008_daily_modes
"""

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "009_weekly_plan_struct"
down_revision = "008_daily_modes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("weekly_reports") as batch_op:
        batch_op.add_column(sa.Column("plan_executions_json", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("week_tasks_json", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("weekly_reports") as batch_op:
        batch_op.drop_column("week_tasks_json")
        batch_op.drop_column("plan_executions_json")
```

- [ ] **Step 2: 在本地库执行迁移并验证**

Run（cwd `d:\work\night_diary_v2\server`）: `.\.venv\Scripts\python.exe -m alembic upgrade head`
Expected: 输出 `Running upgrade 008_daily_modes -> 009_weekly_plan_struct`，无报错。

验证（PowerShell）：

```powershell
.\.venv\Scripts\python.exe -c "import sqlite3; c = sqlite3.connect('night_diary.db'); print([r[1] for r in c.execute('PRAGMA table_info(weekly_reports)')])"
```

Expected: 列表包含 `plan_executions_json` 与 `week_tasks_json`。

- [ ] **Step 3: 提交**

```bash
git add server/alembic/versions/009_weekly_plan_struct.py
git commit -m "chore(db): add weekly plan-execution JSON columns (009)"
```

### Task 1.6: PR-1 收尾验证

- [ ] **Step 1: 后端全量测试**

Run: `.\.venv\Scripts\python.exe -m pytest`
Expected: 全部 PASS（eval 标记默认排除）。

- [ ] **Step 2: 创建 PR-1**

分支 `feature/merge-diary-weekly-review-pr1`，PR 描述包含：标题、功能描述（4 个接口变化 + 结构化字段）、实现思路、测试方式（列出新增测试名）。

---

## PR-2 时间轴骨架 + 导航重组（P0）

> 内容：导航 6→5（计划升一级入口）、`TimelineScene` 落地 `/`（日视图 + 周看板迁移）、`/review/:diaryId` 重定向、删除 HomeScene。`/weekly`、`/review` 路由本 PR 保留（不在导航，PR-3/PR-6 再删）。
>
> 减法决策（对照规格 §3.3/§11）：HomeScene 的 `nudge`（"今天还没写日记"）、`replyBanner`（"有 N 封回信没读"）、连续记录 streak 横幅**不迁移**——它们是压力点/噪音，日记卡与详情面板已承载同等信息。

### Task 2.1: timelineQuery 纯函数工具（TDD）

**Files:**
- Create: `src/shared/utils/timelineQuery.ts`
- Test: `src/__tests__/timelineQuery.spec.ts`

- [ ] **Step 1: 写失败测试**

新建 `src/__tests__/timelineQuery.spec.ts`：

```ts
import { describe, expect, it } from 'vitest'

import { buildTimelineQuery, parseTimelineQuery } from '@/shared/utils/timelineQuery'

describe('timelineQuery', () => {
  it('defaults to day view and the given today', () => {
    expect(parseTimelineQuery({}, '2026-08-25')).toEqual({ view: 'day', date: '2026-08-25' })
  })

  it('parses view and date from the query', () => {
    const parsed = parseTimelineQuery({ view: 'week', date: '2026-08-24' }, '2026-08-25')
    expect(parsed).toEqual({ view: 'week', date: '2026-08-24' })
  })

  it('falls back on invalid view or malformed date', () => {
    const parsed = parseTimelineQuery({ view: 'year', date: '08/25' }, '2026-08-25')
    expect(parsed).toEqual({ view: 'day', date: '2026-08-25' })
  })

  it('handles repeated query params (array form)', () => {
    const parsed = parseTimelineQuery({ view: ['month'], date: ['2026-08-01'] }, '2026-08-25')
    expect(parsed).toEqual({ view: 'month', date: '2026-08-01' })
  })

  it('builds a query object for the router', () => {
    expect(buildTimelineQuery('week', '2026-08-24')).toEqual({ view: 'week', date: '2026-08-24' })
  })
})
```

- [ ] **Step 2: 运行确认失败**

Run: `npx vitest run src/__tests__/timelineQuery.spec.ts`
Expected: FAIL —— 模块不存在。

- [ ] **Step 3: 实现**

新建 `src/shared/utils/timelineQuery.ts`：

```ts
import type { LocationQuery, LocationQueryRaw } from 'vue-router'

export type TimelineView = 'day' | 'week' | 'month'

const VIEWS: readonly TimelineView[] = ['day', 'week', 'month']

const ISO_DATE_RE = /^\d{4}-\d{2}-\d{2}$/

export function isTimelineView(value: unknown): value is TimelineView {
  return typeof value === 'string' && (VIEWS as readonly string[]).includes(value)
}

function firstQueryValue(value: LocationQuery[string]): unknown {
  return Array.isArray(value) ? value[0] : value
}

export function parseTimelineQuery(
  query: LocationQuery,
  todayIso: string,
): { view: TimelineView; date: string } {
  const rawView = firstQueryValue(query.view)
  const view = isTimelineView(rawView) ? rawView : 'day'
  const rawDate = firstQueryValue(query.date)
  const date =
    typeof rawDate === 'string' && ISO_DATE_RE.test(rawDate) ? rawDate : todayIso
  return { view, date }
}

export function buildTimelineQuery(view: TimelineView, date: string): LocationQueryRaw {
  return { view, date }
}
```

- [ ] **Step 4: 运行确认通过**

Run: `npx vitest run src/__tests__/timelineQuery.spec.ts`
Expected: 5 个 PASS。

- [ ] **Step 5: 提交**

```bash
git add src/shared/utils/timelineQuery.ts src/__tests__/timelineQuery.spec.ts
git commit -m "feat(timeline): add query parsing helpers for unified timeline"
```

### Task 2.2: API 层日期参数 + listTasks（TDD）

**Files:**
- Modify: `src/shared/api/diary.ts`（`ListDiaryParams`）
- Modify: `src/shared/api/plan.ts`（新增 `listTasks`）
- Test: `src/__tests__/diaryApi.spec.ts`（追加）、`src/__tests__/planApi.spec.ts`（新建）

- [ ] **Step 1: 写失败测试**

`src/__tests__/diaryApi.spec.ts` 的 `describe('diary API')` 内追加：

```ts
  it('passes date range params through', async () => {
    vi.mocked(axios.create).mockReturnValue(mockAxiosClient({ get }) as never)
    get.mockResolvedValue({ data: [] })

    await listDiaryEntries({ date_from: '2026-08-24', date_to: '2026-08-30' })
    expect(get).toHaveBeenCalledWith('/api/v1/diary/entries', {
      params: { date_from: '2026-08-24', date_to: '2026-08-30' },
    })
  })
```

新建 `src/__tests__/planApi.spec.ts`（结构照抄 diaryApi.spec.ts 的 mock 头）：

```ts
import axios from 'axios'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { mockAxiosClient } from '@/__tests__/helpers/mockAxiosClient'
import { listTasks } from '@/shared/api/plan'
import { resetHttpClient } from '@/shared/api/http'

vi.mock('axios', () => {
  const create = vi.fn()
  return { default: { create } }
})

vi.mock('@/shared/composables/useBackend', () => ({
  resolveBackendBaseUrl: vi.fn(async () => 'http://127.0.0.1:8000'),
  waitForCoreReady: vi.fn(async () => undefined),
}))

describe('plan API', () => {
  const get = vi.fn()

  afterEach(() => {
    vi.clearAllMocks()
    resetHttpClient()
  })

  it('lists tasks with due-date range', async () => {
    vi.mocked(axios.create).mockReturnValue(mockAxiosClient({ get }) as never)
    get.mockResolvedValue({ data: [] })

    await listTasks({ date_from: '2026-08-24', date_to: '2026-08-30' })
    expect(get).toHaveBeenCalledWith('/api/v1/tasks', {
      params: { date_from: '2026-08-24', date_to: '2026-08-30' },
    })
  })
})
```

- [ ] **Step 2: 运行确认失败**

Run: `npx vitest run src/__tests__/diaryApi.spec.ts src/__tests__/planApi.spec.ts`
Expected: FAIL —— 类型不含 date_from/date_to（编译期），listTasks 未导出。

- [ ] **Step 3: 实现**

`src/shared/api/diary.ts`：

```ts
export interface ListDiaryParams {
  skip?: number
  limit?: number
  date_from?: string
  date_to?: string
}
```

`src/shared/api/plan.ts` 在 `getTodayTasks` 附近追加：

```ts
export interface ListTasksParams {
  plan_id?: string
  status?: string
  date_from?: string
  date_to?: string
}

export async function listTasks(params: ListTasksParams = {}): Promise<TaskItem[]> {
  const client = await getHttpClient()
  const { data } = await client.get<TaskItem[]>('/api/v1/tasks', { params })
  return data
}
```

- [ ] **Step 4: 运行确认通过 + 类型检查**

Run: `npx vitest run src/__tests__/diaryApi.spec.ts src/__tests__/planApi.spec.ts && npm run type-check`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add src/shared/api/diary.ts src/shared/api/plan.ts src/__tests__/diaryApi.spec.ts src/__tests__/planApi.spec.ts
git commit -m "feat(api): expose date-range params on diary/task list clients"
```

### Task 2.3: timeline store（TDD）

**Files:**
- Create: `src/stores/timeline.ts`
- Test: `src/__tests__/timelineStore.spec.ts`

- [ ] **Step 1: 写失败测试**

新建 `src/__tests__/timelineStore.spec.ts`：

```ts
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createPinia, setActivePinia } from 'pinia'

const listDiaryEntries = vi.fn(async () => [
  {
    id: 1,
    content: 'a',
    date: '2026-08-25',
    weather: null,
    reply: null,
    created_at: '2026-08-25T10:00:00',
    updated_at: '2026-08-25T10:00:00',
  },
])

vi.mock('@/shared/api/diary', () => ({ listDiaryEntries }))
vi.mock('@/shared/api/card', () => ({
  listCards: vi.fn(async () => []),
  getMoodTrends: vi.fn(async () => []),
}))

import { useTimelineStore } from '@/stores/timeline'
import { listDiaryEntries as mockedList } from '@/shared/api/diary'

describe('timeline store', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('starts on day view anchored at today', () => {
    const store = useTimelineStore()
    expect(store.view).toBe('day')
    expect(store.date).toBe(new Date().toISOString().slice(0, 10))
  })

  it('loads entries for the anchored day', async () => {
    const store = useTimelineStore()
    await store.setDate('2026-08-25')
    expect(mockedList).toHaveBeenCalledWith({
      date_from: '2026-08-25',
      date_to: '2026-08-25',
      limit: 100,
    })
    expect(store.entries).toHaveLength(1)
  })

  it('switching to week view loads the whole ISO week', async () => {
    const store = useTimelineStore()
    await store.setDate('2026-08-25') // 周二
    await store.setView('week')
    expect(mockedList).toHaveBeenLastCalledWith({
      date_from: '2026-08-24',
      date_to: '2026-08-30',
      limit: 100,
    })
  })

  it('shiftPeriod moves one day in day view and one week in week view', async () => {
    const store = useTimelineStore()
    await store.setDate('2026-08-25')
    await store.shiftPeriod(-1)
    expect(store.date).toBe('2026-08-24')

    await store.setView('week')
    await store.shiftPeriod(-1)
    expect(store.date).toBe('2026-08-17') // 前一周周一
  })

  it('month view range covers the whole anchor month', async () => {
    const store = useTimelineStore()
    await store.setDate('2026-08-15')
    await store.setView('month')
    expect(mockedList).toHaveBeenLastCalledWith({
      date_from: '2026-08-01',
      date_to: '2026-08-31',
      limit: 100,
    })
  })

  it('tracks the selected entry', async () => {
    const store = useTimelineStore()
    await store.setDate('2026-08-25')
    store.selectEntry(1)
    expect(store.selectedEntry?.id).toBe(1)
    store.selectEntry(null)
    expect(store.selectedEntry).toBeNull()
  })
})
```

- [ ] **Step 2: 运行确认失败**

Run: `npx vitest run src/__tests__/timelineStore.spec.ts`
Expected: FAIL —— store 模块不存在。

- [ ] **Step 3: 实现**

新建 `src/stores/timeline.ts`：

```ts
import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { listDiaryEntries, type DiaryEntry } from '@/shared/api/diary'
import { formatApiError } from '@/shared/utils/apiError'
import {
  endOfWeekSunday,
  parseLocalDate,
  startOfWeekMonday,
  toIsoDate,
} from '@/shared/utils/diaryFormat'
import type { TimelineView } from '@/shared/utils/timelineQuery'

export const useTimelineStore = defineStore('timeline', () => {
  // ── State ─────────────────────────────────────────────────────
  const view = ref<TimelineView>('day')
  const date = ref(toIsoDate(new Date()))
  const loading = ref(false)
  const error = ref<string | null>(null)

  const entries = ref<DiaryEntry[]>([])
  const selectedEntryId = ref<number | null>(null)

  // ── Getters ───────────────────────────────────────────────────
  const todayIso = computed(() => toIsoDate(new Date()))
  const isToday = computed(() => date.value === todayIso.value)
  const weekStart = computed(() => startOfWeekMonday(parseLocalDate(date.value)))
  const weekStartIso = computed(() => toIsoDate(weekStart.value))
  const weekEndIso = computed(() => toIsoDate(endOfWeekSunday(weekStart.value)))

  const range = computed<{ from: string; to: string }>(() => {
    if (view.value === 'day') return { from: date.value, to: date.value }
    if (view.value === 'week') return { from: weekStartIso.value, to: weekEndIso.value }
    const anchor = parseLocalDate(date.value)
    return {
      from: toIsoDate(new Date(anchor.getFullYear(), anchor.getMonth(), 1)),
      to: toIsoDate(new Date(anchor.getFullYear(), anchor.getMonth() + 1, 0)),
    }
  })

  const selectedEntry = computed(() =>
    selectedEntryId.value == null
      ? null
      : entries.value.find((e) => e.id === selectedEntryId.value) ?? null,
  )

  // ── Actions ───────────────────────────────────────────────────
  async function load() {
    loading.value = true
    error.value = null
    const { from, to } = range.value
    try {
      entries.value = await listDiaryEntries({ date_from: from, date_to: to, limit: 100 })
    } catch (err) {
      error.value = formatApiError(err, '加载日记失败')
    } finally {
      loading.value = false
    }
  }

  async function setView(next: TimelineView) {
    if (view.value === next) return
    view.value = next
    await load()
  }

  async function setDate(iso: string) {
    if (date.value === iso) return
    date.value = iso
    await load()
  }

  async function shiftPeriod(delta: number) {
    if (view.value === 'day') {
      const next = parseLocalDate(date.value)
      next.setDate(next.getDate() + delta)
      await setDate(toIsoDate(next))
      return
    }
    if (view.value === 'week') {
      await setDate(toIsoDate(startOfWeekMonday(parseLocalDate(date.value), delta)))
      return
    }
    const anchor = parseLocalDate(date.value)
    await setDate(toIsoDate(new Date(anchor.getFullYear(), anchor.getMonth() + delta, 1)))
  }

  async function goToday() {
    await setDate(todayIso.value)
  }

  function selectEntry(entryId: number | null) {
    selectedEntryId.value = entryId
  }

  return {
    view,
    date,
    loading,
    error,
    entries,
    selectedEntryId,
    todayIso,
    isToday,
    weekStart,
    weekStartIso,
    weekEndIso,
    range,
    selectedEntry,
    load,
    setView,
    setDate,
    shiftPeriod,
    goToday,
    selectEntry,
  }
})
```

（周视图的任务与心情曲线数据在 PR-3 扩展 `load()`，月视图无需额外数据——月历圆点来自 `entries`。）

- [ ] **Step 4: 运行确认通过**

Run: `npx vitest run src/__tests__/timelineStore.spec.ts`
Expected: 6 个 PASS。

- [ ] **Step 5: 提交**

```bash
git add src/stores/timeline.ts src/__tests__/timelineStore.spec.ts
git commit -m "feat(timeline): add timeline store with view/date navigation"
```

### Task 2.4: 文案文件

**Files:**
- Create: `src/shared/copy/timeline.ts`

- [ ] **Step 1: 创建文案**

```ts
/** Unified timeline scene copy. Plain Chinese in .ts files is the established pattern (see weekly.ts). */

export const timelineCopy = {
  viewDay: '日',
  viewWeek: '周',
  viewMonth: '月',
  writeDiary: '记一笔',
  retry: '重试',
  prevDay: '前一天',
  nextDay: '后一天',
  prevWeek: '前一周',
  nextWeek: '后一周',
  todayTag: '今天',
  backToToday: '回到今天',
  emptyTitle: '这一天还没有记录',
  emptyHint: '从一句话开始就好',
  emptyCta: '记一笔',
  moreRecords: (n: number) => `还有 ${n} 条记录`,
  dayDrawerTitle: (label: string, day: number) => `${label} ${day}日`,
  taskSummary: (total: number, done: number) => `今日 ${total} 项 · 已完成 ${done}`,
  taskSectionDone: '都完成了，慢慢来',
} as const
```

- [ ] **Step 2: 提交**

```bash
git add src/shared/copy/timeline.ts
git commit -m "feat(timeline): add timeline scene copy"
```

### Task 2.5: TaskFoldRow 组件（TDD）

**Files:**
- Create: `src/features/timeline/TaskFoldRow.vue`
- Test: `src/__tests__/TaskFoldRow.spec.ts`

- [ ] **Step 1: 写失败测试**

新建 `src/__tests__/TaskFoldRow.spec.ts`：

```ts
import { describe, expect, it, vi } from 'vitest'
import { mount, type VueWrapper } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/shared/api/plan', () => ({
  listPlans: vi.fn(async () => []),
  getTodayTasks: vi.fn(async () => []),
  updateTaskStatus: vi.fn(async () => ({})),
  deleteTask: vi.fn(async () => undefined),
  deletePlan: vi.fn(async () => undefined),
}))

import TaskFoldRow from '@/features/timeline/TaskFoldRow.vue'
import { usePlanStore } from '@/stores/plan'

function mountRow() {
  setActivePinia(createPinia())
  const planStore = usePlanStore()
  planStore.todayTasks = [
    { id: 't1', plan_id: null, title: '散步', note: null, due_date: null, status: 'pending', source: 'manual', completed_at: null },
    { id: 't2', plan_id: null, title: '读书', note: null, due_date: null, status: 'done', source: 'manual', completed_at: null },
  ] as never
  const toggleSpy = vi.spyOn(planStore, 'toggleTask').mockImplementation(async () => {})
  const wrapper = mount(TaskFoldRow, { global: { plugins: [] } })
  return { wrapper, toggleSpy }
}

describe('TaskFoldRow', () => {
  it('hides entirely when there are no tasks', async () => {
    setActivePinia(createPinia())
    const planStore = usePlanStore()
    planStore.todayTasks = []
    const wrapper = mount(TaskFoldRow)
    expect(wrapper.find('.task-fold').exists()).toBe(false)
  })

  it('renders a neutral summary line and expands on click', async () => {
    const { wrapper } = mountRow()
    expect(wrapper.text()).toContain('今日 2 项 · 已完成 1')
    expect(wrapper.find('input[type="checkbox"]').exists()).toBe(false)

    await wrapper.find('.task-fold__summary').trigger('click')
    expect(wrapper.findAll('input[type="checkbox"]')).toHaveLength(2)
  })

  it('toggles a task through the plan store', async () => {
    const { wrapper, toggleSpy } = mountRow()
    await wrapper.find('.task-fold__summary').trigger('click')
    const first = wrapper.findAll('input[type="checkbox"]')[0]
    await first.setValue(true)
    expect(toggleSpy).toHaveBeenCalledWith('t1', 'pending')
  })
})
```

- [ ] **Step 2: 运行确认失败**

Run: `npx vitest run src/__tests__/TaskFoldRow.spec.ts`
Expected: FAIL —— 组件不存在。

- [ ] **Step 3: 实现**

新建 `src/features/timeline/TaskFoldRow.vue`：

```vue
<script setup lang="ts">
import { computed, ref } from 'vue'
import { PhCaretDown } from '@phosphor-icons/vue'

import { timelineCopy as copy } from '@/shared/copy/timeline'
import { usePlanStore } from '@/stores/plan'

const planStore = usePlanStore()
const expanded = ref(false)

const total = computed(() => planStore.todayTasks.length)
const done = computed(() => planStore.todayTasks.filter((t) => t.status === 'done').length)
</script>

<template>
  <div v-if="total > 0" class="task-fold">
    <button type="button" class="task-fold__summary" @click="expanded = !expanded">
      <span>{{ copy.taskSummary(total, done) }}</span>
      <PhCaretDown :size="14" class="task-fold__caret" :class="{ 'is-open': expanded }" />
    </button>
    <div v-if="expanded" class="task-fold__list">
      <label v-for="task in planStore.todayTasks" :key="task.id" class="task-fold__item">
        <input
          type="checkbox"
          :checked="task.status === 'done'"
          @change="planStore.toggleTask(task.id, task.status)"
        />
        <span class="task-fold__title" :class="{ 'is-done': task.status === 'done' }">
          {{ task.title }}
        </span>
      </label>
    </div>
  </div>
</template>

<style scoped>
.task-fold {
  border: 1px solid var(--color-border);
  border-radius: 0.75rem;
  background: var(--color-bg-elevated);
  padding: 0.375rem 0.625rem;
}
.task-fold__summary {
  display: flex;
  width: 100%;
  align-items: center;
  justify-content: space-between;
  border: none;
  background: transparent;
  color: var(--color-text-secondary);
  font-size: 0.8125rem;
  cursor: pointer;
  padding: 0.25rem 0;
}
.task-fold__caret {
  transition: transform var(--motion-duration) var(--motion-ease);
}
.task-fold__caret.is-open {
  transform: rotate(180deg);
}
.task-fold__list {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  padding: 0.375rem 0 0.25rem;
  border-top: 1px solid var(--color-border);
}
.task-fold__item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.8125rem;
  color: var(--color-text-primary);
  padding: 0.1875rem 0;
  cursor: pointer;
}
.task-fold__item input {
  accent-color: var(--color-accent);
}
.task-fold__title.is-done {
  color: var(--color-text-secondary);
  text-decoration: line-through;
}
</style>
```

- [ ] **Step 4: 运行确认通过**

Run: `npx vitest run src/__tests__/TaskFoldRow.spec.ts`
Expected: 3 个 PASS。

- [ ] **Step 5: 提交**

```bash
git add src/features/timeline/TaskFoldRow.vue src/__tests__/TaskFoldRow.spec.ts
git commit -m "feat(timeline): add collapsed today-task row for day view"
```

### Task 2.6: DayView 组件

**Files:**
- Create: `src/features/timeline/DayView.vue`

- [ ] **Step 1: 实现组件**

新建 `src/features/timeline/DayView.vue`（日记卡点击暂沿用 HomeScene 行为——跳 `/write/:id`；PR-4 改为打开详情面板）：

```vue
<script setup lang="ts">
import { computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { PhCaretLeft, PhCaretRight } from '@phosphor-icons/vue'

import EmotionChips from '@/features/card/EmotionChips.vue'
import GameButton from '@/shared/components/GameButton.vue'
import GlassPanel from '@/shared/components/GlassPanel.vue'
import TaskFoldRow from '@/features/timeline/TaskFoldRow.vue'
import { timelineCopy as copy } from '@/shared/copy/timeline'
import { cardCopy } from '@/shared/copy/card'
import { useTimelineStore } from '@/stores/timeline'
import { useCardStore } from '@/stores/card'
import { usePlanStore } from '@/stores/plan'
import {
  diaryStatus,
  diarySummary,
  parseLocalDate,
  weekdayLabel,
} from '@/shared/utils/diaryFormat'
import type { MemoryCard } from '@/shared/api/card'

const router = useRouter()
const timeline = useTimelineStore()
const cardStore = useCardStore()
const planStore = usePlanStore()

const EMOTION_COLORS: Record<string, string> = {
  '\u5f00\u5fc3': '#4CAF50',
  '\u5e73\u9759': '#607D8B',
  '\u611f\u6fc0': '#D4A574',
  '\u671f\u5f85': '#26A69A',
  '\u5174\u594b': '#FF9800',
  '\u7126\u8651': '#7E57C2',
  '\u75b2\u60eb': '#9E9E9E',
  '\u60b2\u4f24': '#5C6BC0',
  '\u8ff7\u832b': '#78909C',
  '\u6124\u6012': '#EF5350',
}

const dayLabel = computed(() => {
  const d = parseLocalDate(timeline.date)
  return `${d.getMonth() + 1}\u6708${d.getDate()}\u65e5 ${weekdayLabel(d)}`
})

const dayCards = computed(() =>
  cardStore.cards.filter(
    (c) => c.diary_id == null && c.created_at.slice(0, 10) === timeline.date,
  ),
)

const isEmptyDay = computed(
  () => !timeline.loading && timeline.entries.length === 0 && dayCards.value.length === 0,
)

function cardEmotionColor(card: MemoryCard): string {
  return EMOTION_COLORS[card.emotion] ?? 'var(--color-accent)'
}

function openEntry(entryId: number, hasReply: boolean) {
  if (hasReply) {
    router.push({ path: `/write/${entryId}`, hash: '#reply' })
    return
  }
  router.push(`/write/${entryId}`)
}

function openCard(card: MemoryCard) {
  if (card.diary_id) {
    router.push(`/write/${card.diary_id}`)
    return
  }
  cardStore
    .expandCard(card.card_id)
    .then((result) => {
      void timeline.load()
      router.push(`/write/${result.diary_id}`)
    })
    .catch(() => {
      /* handled by store */
    })
}

function createForDate() {
  router.push({ path: '/write', query: { date: timeline.date } })
}

onMounted(() => {
  if (timeline.isToday) void planStore.loadTodayTasks()
})
</script>

<template>
  <section class="day-view">
    <div class="day-view__nav">
      <button type="button" class="day-view__nav-btn" @click="timeline.shiftPeriod(-1)">
        <PhCaretLeft :size="14" />
        {{ copy.prevDay }}
      </button>
      <span class="day-view__label" :class="{ 'is-today': timeline.isToday }">
        {{ dayLabel }}
        <span v-if="timeline.isToday" class="day-view__today">{{ copy.todayTag }}</span>
      </span>
      <button type="button" class="day-view__nav-btn" @click="timeline.shiftPeriod(1)">
        {{ copy.nextDay }}
        <PhCaretRight :size="14" />
      </button>
      <button
        v-if="!timeline.isToday"
        type="button"
        class="day-view__nav-btn"
        @click="timeline.goToday()"
      >
        {{ copy.backToToday }}
      </button>
    </div>

    <section v-if="isEmptyDay" class="day-view__empty">
      <p class="day-view__empty-title">{{ copy.emptyTitle }}</p>
      <p class="day-view__empty-hint">{{ copy.emptyHint }}</p>
      <GameButton variant="primary" @click="createForDate">{{ copy.emptyCta }}</GameButton>
    </section>

    <template v-else>
      <GlassPanel
        v-for="entry in timeline.entries"
        :key="entry.id"
        class="day-view__diary"
        :class="{ 'is-replied': diaryStatus(entry) === 'reply' }"
      >
        <div class="day-view__diary-head">
          <span class="day-view__diary-date">{{ timeline.date }}</span>
          <span v-if="entry.weather" class="day-view__diary-weather">{{ entry.weather }}</span>
        </div>
        <button type="button" class="day-view__diary-body" @click="openEntry(entry.id, Boolean(entry.reply?.trim()))">
          <span class="day-view__diary-preview font-diary">
            {{ diarySummary(entry.content, 120) }}
          </span>
          <span class="day-view__diary-continue">{{ copy.writeDiary }}</span>
        </button>
      </GlassPanel>

      <TaskFoldRow v-if="timeline.isToday" class="day-view__tasks" />

      <GlassPanel
        v-for="card in dayCards"
        :key="card.card_id"
        class="day-view__card"
        :style="{ borderLeftColor: cardEmotionColor(card) }"
      >
        <button type="button" class="day-view__card-body" @click="openCard(card)">
          <span class="day-view__card-summary font-diary">
            {{ diarySummary(card.event_summary, 60, cardCopy.recordedMoodOnly) }}
          </span>
          <EmotionChips
            class="day-view__card-emotion"
            :emotions="card.emotions"
            :emotion="card.emotion"
            :size="12"
            compact
            :max-count="1"
          />
        </button>
      </GlassPanel>
    </template>
  </section>
</template>

<style scoped>
.day-view {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
.day-view__nav {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}
.day-view__nav-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  border: none;
  background: transparent;
  color: var(--color-text-secondary);
  font-size: 0.8125rem;
  cursor: pointer;
  padding: 0.25rem 0.375rem;
}
.day-view__nav-btn:hover {
  color: var(--color-text-primary);
}
.day-view__label {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--color-text-primary);
  display: inline-flex;
  align-items: center;
  gap: 0.375rem;
}
.day-view__today {
  font-size: 0.625rem;
  font-weight: 600;
  color: #fff;
  background: var(--color-accent);
  padding: 0.125rem 0.375rem;
  border-radius: 999px;
  line-height: 1;
}
.day-view__empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.5rem;
  padding: 3rem 1.5rem;
  text-align: center;
  border: 1px dashed var(--color-border);
  border-radius: 0.875rem;
}
.day-view__empty-title {
  font-size: 1rem;
  font-weight: 600;
  color: var(--color-text-primary);
}
.day-view__empty-hint {
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
  margin-bottom: 0.75rem;
}
.day-view__diary.is-replied {
  border-left: 3px solid color-mix(in srgb, var(--color-success) 60%, var(--color-border));
}
.day-view__diary-head {
  display: flex;
  align-items: baseline;
  gap: 0.625rem;
  font-size: 0.75rem;
  color: var(--color-text-secondary);
}
.day-view__diary-body {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 0.375rem;
  width: 100%;
  border: none;
  background: transparent;
  cursor: pointer;
  text-align: left;
  padding: 0;
}
.day-view__diary-preview {
  font-size: 0.875rem;
  line-height: 1.6;
  color: var(--color-text-primary);
  display: -webkit-box;
  -webkit-box-orient: vertical;
  -webkit-line-clamp: 4;
  overflow: hidden;
}
.day-view__diary-continue {
  font-size: 0.75rem;
  color: var(--color-accent);
  font-weight: 600;
}
.day-view__card {
  border-left: 3px solid var(--color-accent);
}
.day-view__card-body {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  width: 100%;
  border: none;
  background: transparent;
  cursor: pointer;
  text-align: left;
  padding: 0;
}
.day-view__card-summary {
  font-size: 0.8125rem;
  color: var(--color-text-primary);
}
</style>
```

- [ ] **Step 2: 类型检查**

Run: `npm run type-check`
Expected: 无错误。

- [ ] **Step 3: 提交**

```bash
git add src/features/timeline/DayView.vue
git commit -m "feat(timeline): add day view with writing-first diary cards"
```

### Task 2.7: WeekView 组件（从 HomeScene 迁移周看板）

**Files:**
- Create: `src/features/timeline/WeekView.vue`

- [ ] **Step 1: 实现组件**

新建 `src/features/timeline/WeekView.vue`——脚本与模板从 `src/pages/HomeScene.vue` 迁移，数据源替换：`diaryStore.entries` → `timeline.entries`；`weekOffset ± 1` → `timeline.shiftPeriod(±1)`；`todayIso` → `timeline.todayIso`；点击日记卡仍跳 `/write/:id`；「+」按钮仍 `createForDate(column.key)`。完整代码：

```vue
<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { PhCaretLeft, PhCaretRight } from '@phosphor-icons/vue'

import DayDetailDrawer from '@/features/home/DayDetailDrawer.vue'
import EmotionChips from '@/features/card/EmotionChips.vue'
import { timelineCopy as copy } from '@/shared/copy/timeline'
import { cardCopy } from '@/shared/copy/card'
import { useTimelineStore } from '@/stores/timeline'
import { useCardStore } from '@/stores/card'
import type { DiaryEntry } from '@/shared/api/diary'
import type { MemoryCard } from '@/shared/api/card'
import {
  diaryStatus,
  diarySummary,
  formatWeekRangeLabel,
  groupEntriesForWeek,
  toIsoDate,
  weekdayLabel,
} from '@/shared/utils/diaryFormat'
import {
  sortKanbanItems,
  splitKanbanItems,
  type KanbanItem,
} from '@/shared/utils/kanbanSort'

const router = useRouter()
const timeline = useTimelineStore()
const cardStore = useCardStore()

type WeekColumn = {
  key: string
  label: string
  isToday: boolean
  dayNumber: number
  visibleItems: KanbanItem[]
  overflowCount: number
  allItems: KanbanItem[]
}

const dayDrawer = ref<{ title: string; items: KanbanItem[] } | null>(null)

const EMOTION_COLORS: Record<string, string> = {
  '\u5f00\u5fc3': '#4CAF50',
  '\u5e73\u9759': '#607D8B',
  '\u611f\u6fc0': '#D4A574',
  '\u671f\u5f85': '#26A69A',
  '\u5174\u594b': '#FF9800',
  '\u7126\u8651': '#7E57C2',
  '\u75b2\u60eb': '#9E9E9E',
  '\u60b2\u4f24': '#5C6BC0',
  '\u8ff7\u832b': '#78909C',
  '\u6124\u6012': '#EF5350',
}

function cardEmotionColor(card: MemoryCard): string {
  return EMOTION_COLORS[card.emotion] ?? 'var(--color-accent)'
}

const weekLabel = computed(() =>
  formatWeekRangeLabel(timeline.weekStart, timeline.weekEndIsoDate ?? timeline.weekEnd),
)

const weekColumns = computed(() => {
  const { dayColumns } = groupEntriesForWeek(
    timeline.entries,
    timeline.weekStart,
    timeline.weekEnd,
  )

  const cardByDiaryId = new Map<number, MemoryCard>()
  const standaloneCardsByDate = new Map<string, MemoryCard[]>()
  for (const card of cardStore.cards) {
    if (card.diary_id != null) {
      cardByDiaryId.set(card.diary_id, card)
    } else {
      const date = card.created_at.slice(0, 10)
      const arr = standaloneCardsByDate.get(date)
      if (arr) arr.push(card)
      else standaloneCardsByDate.set(date, [card])
    }
  }

  const days = Array.from({ length: 7 }, (_, index) => {
    const date = new Date(timeline.weekStart)
    date.setDate(date.getDate() + index)
    const iso = toIsoDate(date)
    const diaryEntries = dayColumns.get(iso) ?? []
    const standaloneCards = standaloneCardsByDate.get(iso) ?? []

    const items: KanbanItem[] = [
      ...diaryEntries.map((e): KanbanItem => ({
        kind: 'diary',
        entry: e,
        linkedCard: cardByDiaryId.get(e.id) ?? null,
      })),
      ...standaloneCards.map((c): KanbanItem => ({ kind: 'card', card: c })),
    ]
    const sorted = sortKanbanItems(items)
    const { visible, overflowCount } = splitKanbanItems(sorted)

    return {
      key: iso,
      label: weekdayLabel(date),
      isToday: iso === timeline.todayIso,
      dayNumber: date.getDate(),
      visibleItems: visible,
      overflowCount,
      allItems: sorted,
    }
  })

  return days as WeekColumn[]
})

function openEntry(entry: DiaryEntry, scrollToReply = false) {
  if (scrollToReply && entry.reply?.trim()) {
    router.push({ path: `/write/${entry.id}`, hash: '#reply' })
    return
  }
  router.push(`/write/${entry.id}`)
}

function openCard(card: MemoryCard) {
  if (card.diary_id) {
    router.push(`/write/${card.diary_id}`)
    return
  }
  cardStore
    .expandCard(card.card_id)
    .then((result) => {
      void timeline.load()
      router.push(`/write/${result.diary_id}`)
    })
    .catch(() => {
      /* handled by store */
    })
}

function openDayDrawer(column: WeekColumn) {
  if (column.allItems.length === 0) return
  const title = column.isToday
    ? `${column.label} ${copy.todayTag} ${column.dayNumber}\u65e5`
    : copy.dayDrawerTitle(column.label, column.dayNumber)
  dayDrawer.value = { title, items: column.allItems }
}

function closeDayDrawer() {
  dayDrawer.value = null
}

function onDrawerOpenDiary(entry: DiaryEntry, scrollToReply?: boolean) {
  closeDayDrawer()
  openEntry(entry, scrollToReply)
}

function onDrawerOpenCard(card: MemoryCard) {
  closeDayDrawer()
  openCard(card)
}

function createForDate(isoDate: string | null) {
  if (isoDate) {
    router.push({ path: '/write', query: { date: isoDate } })
    return
  }
  router.push('/write')
}
</script>

<template>
  <section class="week-view">
    <div class="week-view__nav">
      <button type="button" class="week-view__nav-btn" @click="timeline.shiftPeriod(-1)">
        <PhCaretLeft :size="14" />
        {{ copy.prevWeek }}
      </button>
      <span class="week-view__label">{{ weekLabel }}</span>
      <button type="button" class="week-view__nav-btn" @click="timeline.shiftPeriod(1)">
        {{ copy.nextWeek }}
        <PhCaretRight :size="14" />
      </button>
    </div>

    <div class="week-view__kanban" :class="{ 'is-loading': timeline.loading }">
      <div
        v-for="column in weekColumns"
        :key="column.key"
        class="kanban-col"
        :class="{ 'kanban-col--today': column.isToday }"
      >
        <div class="kanban-col__head">
          <span class="kanban-col__label">
            {{ column.label }}
            <span v-if="column.isToday" class="kanban-col__today">{{ copy.todayTag }}</span>
          </span>
          <span class="kanban-col__day">{{ column.dayNumber }}</span>
        </div>

        <template
          v-for="item in column.visibleItems"
          :key="item.kind === 'diary' ? `d-${item.entry.id}` : `c-${item.card.card_id}`"
        >
          <button
            v-if="item.kind === 'diary'"
            type="button"
            class="kanban-card"
            :class="{ 'kanban-card--replied': diaryStatus(item.entry) === 'reply' }"
            @click="openEntry(item.entry, diaryStatus(item.entry) === 'reply')"
          >
            <span class="kanban-card__summary">{{
              diarySummary(item.entry.content, 28, item.linkedCard?.event_summary)
            }}</span>
            <div class="kanban-card__footer">
              <EmotionChips
                v-if="item.linkedCard"
                class="kanban-card__emotion"
                :emotions="item.linkedCard.emotions"
                :emotion="item.linkedCard.emotion"
                :size="12"
                compact
                :max-count="1"
              />
            </div>
          </button>

          <button
            v-else
            type="button"
            class="kanban-card kanban-card--card"
            :style="{ borderLeftColor: cardEmotionColor(item.card) }"
            @click="openCard(item.card)"
          >
            <span v-if="item.card.event_summary" class="kanban-card__summary">
              {{ diarySummary(item.card.event_summary, 32) }}
            </span>
            <span v-else class="kanban-card__summary kanban-card__summary--muted">
              {{ cardCopy.recordedMoodOnly }}
            </span>
            <div class="kanban-card__footer">
              <EmotionChips
                class="kanban-card__emotion"
                :emotions="item.card.emotions"
                :emotion="item.card.emotion"
                :size="12"
                compact
                :max-count="1"
              />
            </div>
          </button>
        </template>

        <button
          v-if="column.overflowCount > 0"
          type="button"
          class="kanban-more"
          @click="openDayDrawer(column)"
        >
          {{ copy.moreRecords(column.overflowCount) }}
        </button>

        <button type="button" class="kanban-add" @click="createForDate(column.key)">+</button>
      </div>
    </div>

    <Teleport to="body">
      <DayDetailDrawer
        v-if="dayDrawer"
        :title="dayDrawer.title"
        :items="dayDrawer.items"
        @close="closeDayDrawer"
        @open-diary="onDrawerOpenDiary"
        @open-card="onDrawerOpenCard"
      />
    </Teleport>
  </section>
</template>

<style scoped>
.week-view {
  display: flex;
  flex-direction: column;
  gap: 0.875rem;
}
.week-view__nav {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
}
.week-view__nav-btn {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  border: none;
  background: transparent;
  color: var(--color-text-secondary);
  font-size: 0.8125rem;
  cursor: pointer;
  padding: 0.25rem 0.375rem;
}
.week-view__nav-btn:hover {
  color: var(--color-text-primary);
}
.week-view__label {
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--color-text-primary);
}
.week-view__kanban.is-loading {
  opacity: 0.65;
  pointer-events: none;
}
.week-view__kanban {
  display: flex;
  gap: 0.5rem;
  overflow-x: auto;
  padding-bottom: 0.5rem;
}
</style>
```

然后从 `src/pages/HomeScene.vue` 的 `<style scoped>`（442-882 行）**原样复制**以下样式类到本组件的 `<style scoped>` 末尾（类名不变，无前缀，直接可用）：`.kanban-col`、`.kanban-col__head`、`.kanban-col--today`（含 `::after` 与子选择器）、`.kanban-col__label`、`.kanban-col__today`、`.kanban-col__day`、`.kanban-card`（含 hover、`--card`、`--replied`、`__footer`、`__emotion`、`__summary`、`__summary--muted`）、`.kanban-more`（含 hover）、`.kanban-add`（含 hover）——即 HomeScene 样式块 580-735 行的连续区段。

- [ ] **Step 2: store 补 weekEnd 便捷字段**

`src/stores/timeline.ts` 的 getters 增加并导出（供 WeekView 使用）：

```ts
  const weekEnd = computed(() => endOfWeekSunday(weekStart.value))
```

（同时把 `weekEndIso` 实现改为 `toIsoDate(weekEnd.value)`，`return` 列表里加 `weekEnd`；WeekView 里 `timeline.weekEndIsoDate ?? timeline.weekEnd` 的临时写法删除，直接用 `formatWeekRangeLabel(timeline.weekStart, timeline.weekEnd)`。）

- [ ] **Step 3: 类型检查 + 存量测试**

Run: `npm run type-check && npm test`
Expected: 通过（本任务未动既有行为）。

- [ ] **Step 4: 提交**

```bash
git add src/features/timeline/WeekView.vue src/stores/timeline.ts
git commit -m "feat(timeline): migrate week kanban board into WeekView"
```

### Task 2.8: TimelineScene 主场景 + 路由/导航重组

**Files:**
- Create: `src/pages/TimelineScene.vue`
- Modify: `src/router/index.ts`
- Modify: `src/shared/components/NavTabs.vue`
- Modify: `src/App.vue`
- Delete: `src/pages/HomeScene.vue`、`src/shared/copy/homeScene.ts`

- [ ] **Step 1: 实现 TimelineScene**

新建 `src/pages/TimelineScene.vue`：

```vue
<script setup lang="ts">
import { onActivated, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { PhNotePencil } from '@phosphor-icons/vue'

defineOptions({ name: 'TimelineScene' })

import DayView from '@/features/timeline/DayView.vue'
import WeekView from '@/features/timeline/WeekView.vue'
import MemoryCardInput from '@/features/card/MemoryCardInput.vue'
import EmotionChips from '@/features/card/EmotionChips.vue'
import GameButton from '@/shared/components/GameButton.vue'
import { timelineCopy as copy } from '@/shared/copy/timeline'
import { cardCopy } from '@/shared/copy/card'
import { useTimelineStore } from '@/stores/timeline'
import { useCardStore } from '@/stores/card'
import { buildTimelineQuery, parseTimelineQuery } from '@/shared/utils/timelineQuery'
import { toIsoDate } from '@/shared/utils/diaryFormat'

const route = useRoute()
const router = useRouter()
const timeline = useTimelineStore()
const cardStore = useCardStore()

function syncFromRoute() {
  const { view, date } = parseTimelineQuery(route.query, toIsoDate(new Date()))
  if (timeline.view === view && timeline.date === date) return
  timeline.view = view
  timeline.date = date
  void timeline.load()
}

watch(
  () => [timeline.view, timeline.date] as const,
  ([view, date]) => {
    if (route.query.view !== view || route.query.date !== date) {
      void router.replace({ query: buildTimelineQuery(view, date) })
    }
  },
)

watch(
  () => route.query,
  () => syncFromRoute(),
)

function writeForDate() {
  router.push({ path: '/write', query: { date: timeline.date } })
}

onMounted(() => {
  syncFromRoute()
  void cardStore.loadCards()
})

onActivated(() => {
  syncFromRoute()
  void cardStore.loadCards()
})
</script>

<template>
  <main class="timeline-scene">
    <header class="timeline-scene__header">
      <div class="timeline-scene__switcher" role="tablist">
        <button
          v-for="v in (['day', 'week'] as const)"
          :key="v"
          type="button"
          role="tab"
          class="timeline-scene__switch"
          :class="{ 'is-active': timeline.view === v }"
          :aria-selected="timeline.view === v"
          @click="timeline.setView(v)"
        >
          {{ v === 'day' ? copy.viewDay : copy.viewWeek }}
        </button>
      </div>
      <div class="timeline-scene__actions">
        <GameButton variant="ghost" @click="cardStore.openDrawer()">
          <PhNotePencil :size="16" />
          {{ cardCopy.newCard }}
        </GameButton>
        <GameButton class="glow-pulse" @click="writeForDate">
          {{ copy.writeDiary }}
        </GameButton>
      </div>
    </header>

    <div v-if="timeline.error" class="timeline-scene__error">
      <span>{{ timeline.error }}</span>
      <GameButton variant="ghost" @click="timeline.load()">{{ copy.retry }}</GameButton>
    </div>

    <DayView v-if="timeline.view === 'day'" />
    <WeekView v-else-if="timeline.view === 'week'" />

    <Teleport to="body">
      <Transition name="card-drawer">
        <div
          v-if="cardStore.showCardDrawer"
          class="card-drawer-backdrop"
          @click.self="cardStore.closeDrawer()"
        >
          <div class="card-drawer-panel">
            <div class="card-drawer-header">
              <h2 class="card-drawer-title">{{ cardCopy.newCard }}</h2>
              <button type="button" class="card-drawer-close" @click="cardStore.closeDrawer()">
                &times;
              </button>
            </div>
            <div class="card-drawer-body">
              <MemoryCardInput
                mode="standard"
                :auto-close="true"
                @saved="cardStore.loadCards()"
                @close="cardStore.closeDrawer()"
              />
            </div>
            <div v-if="cardStore.cards.length > 0" class="card-drawer-recent">
              <p class="card-drawer-recent-title">{{ cardCopy.recentCards }}</p>
              <div class="card-drawer-recent-list">
                <div
                  v-for="card in cardStore.cards.slice(0, 5)"
                  :key="card.card_id"
                  class="recent-card-item"
                >
                  <EmotionChips
                    class="recent-card-emotion"
                    :emotions="card.emotions"
                    :emotion="card.emotion"
                    :size="13"
                  />
                  <span v-if="card.event_summary" class="recent-card-summary">
                    {{ card.event_summary.slice(0, 40) }}{{ card.event_summary.length > 40 ? '…' : '' }}
                  </span>
                </div>
              </div>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </main>
</template>

<style scoped>
.timeline-scene {
  min-height: calc(100vh - 2.5rem);
  padding: 1.25rem 1rem 1.5rem;
  max-width: 90rem;
  margin: 0 auto;
}
.timeline-scene__header {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 1rem;
}
.timeline-scene__switcher {
  display: inline-flex;
  gap: 0.125rem;
  padding: 0.25rem;
  border: 1px solid var(--color-border);
  border-radius: 0.75rem;
  background: var(--color-bg-elevated);
}
.timeline-scene__switch {
  border: none;
  border-radius: 0.5rem;
  background: transparent;
  color: var(--color-text-secondary);
  font-size: 0.8125rem;
  font-weight: 500;
  padding: 0.3125rem 0.875rem;
  cursor: pointer;
  transition:
    color var(--motion-duration) var(--motion-ease),
    background var(--motion-duration) var(--motion-ease);
}
.timeline-scene__switch:hover {
  color: var(--color-text-primary);
}
.timeline-scene__switch.is-active {
  color: var(--color-accent);
  background: color-mix(in srgb, var(--color-accent) 10%, transparent);
}
.timeline-scene__actions {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}
.timeline-scene__error {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
  margin-bottom: 0.75rem;
  padding: 0.625rem 0.875rem;
  border-radius: 0.75rem;
  border: 1px solid color-mix(in srgb, var(--color-danger) 35%, var(--color-border));
  background: color-mix(in srgb, var(--color-danger) 8%, var(--color-bg-elevated));
  font-size: 0.8125rem;
  color: var(--color-danger);
}
</style>

<style>
/* Card drawer（从 HomeScene 迁移的全局样式，Teleport 到 body 需要） */
.card-drawer-backdrop {
  position: fixed;
  inset: 0;
  z-index: 1000;
  background: rgba(0, 0, 0, 0.35);
  display: flex;
  justify-content: center;
  align-items: flex-start;
  padding: 3rem 1rem 1rem;
  overflow-y: auto;
}
.card-drawer-panel {
  width: 100%;
  max-width: 28rem;
  background: var(--color-bg-elevated);
  border-radius: var(--radius-outer, 1.5rem);
  border: 1px solid var(--color-border);
  box-shadow: 0 12px 40px rgba(0, 0, 0, 0.15);
  overflow: hidden;
}
.card-drawer-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 1.25rem;
  border-bottom: 1px solid var(--color-border);
}
.card-drawer-title {
  font-family: var(--font-ui);
  font-size: 1rem;
  font-weight: 700;
  color: var(--color-text-primary);
}
.card-drawer-close {
  width: 1.75rem;
  height: 1.75rem;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: none;
  border: none;
  font-size: 1.25rem;
  color: var(--color-text-secondary);
  cursor: pointer;
  border-radius: 50%;
}
.card-drawer-close:hover {
  background: var(--color-bg-elevated-2);
}
.card-drawer-body {
  padding: 1.25rem;
}
.card-drawer-recent {
  border-top: 1px solid var(--color-border);
  padding: 1rem 1.25rem;
}
.card-drawer-recent-title {
  font-family: var(--font-ui);
  font-size: 0.75rem;
  font-weight: 600;
  color: var(--color-text-secondary);
  margin-bottom: 0.625rem;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}
.card-drawer-recent-list {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}
.recent-card-item {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.4375rem 0.625rem;
  border-radius: 0.5rem;
  background: var(--color-bg);
  font-size: 0.8125rem;
}
.recent-card-emotion {
  font-family: var(--font-ui);
  font-weight: 600;
  color: var(--color-accent);
  white-space: nowrap;
  min-width: 2.5rem;
}
.recent-card-summary {
  font-family: var(--font-diary);
  color: var(--color-text-primary);
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.card-drawer-enter-active,
.card-drawer-leave-active {
  transition: opacity var(--motion-duration, 220ms) var(--motion-ease, ease);
}
.card-drawer-enter-active .card-drawer-panel,
.card-drawer-leave-active .card-drawer-panel {
  transition: transform var(--motion-duration, 220ms) var(--motion-ease, ease);
}
.card-drawer-enter-from,
.card-drawer-leave-to {
  opacity: 0;
}
.card-drawer-enter-from .card-drawer-panel {
  transform: translateY(1rem) scale(0.98);
}
.card-drawer-leave-to .card-drawer-panel {
  transform: translateY(0.5rem) scale(0.98);
}
</style>
```

（卡片抽屉样式原为 HomeScene scoped 样式，但 Teleport 到 body 后 scoped 属性会失效于插槽外层——原实现能工作是因为样式选择器作用于 Teleport 内容时 Vue 仍会给 Teleport 内模板加 scope id；为稳妥起见迁移为非 scoped 全局块，类名均有 `card-drawer`/`recent-card` 前缀，无冲突风险。）

- [ ] **Step 2: 路由重组**

`src/router/index.ts`：

1. 把 `routes: [...]` 数组提取为模块级导出（供 redirect 测试复用）：

```ts
export const appRoutes: RouteRecordRaw[] = [
  // …原有全部路由，内容不变，仅 / 与 /review/:diaryId 两处改动…
]

export const router = createRouter({
  history: createWebHistory(),
  routes: appRoutes,
})
```

2. `/` 路由改为：

```ts
  { path: '/', name: 'home', component: () => import('@/pages/TimelineScene.vue') },
```

3. `/review/:diaryId` 改为重定向（写作页已存在，立即可用）：

```ts
  { path: '/review/:diaryId', redirect: (to) => ({ path: `/write/${to.params.diaryId}` }) },
```

4. `/weekly`、`/review` 两条路由**本 PR 保持不变**（PR-3/PR-6 处理）。`RouteRecordRaw` 类型需在顶部 import 中补上（来自 'vue-router'）。

- [ ] **Step 3: 导航 6 → 5**

`src/shared/components/NavTabs.vue`：import 图标改为 `PhNotebook, PhMapTrifold, PhBrain, PhChatsCircle, PhCpu, PhGear, PhTerminal`（去掉 `PhCalendarCheck`、`PhClockCounterClockwise`），`tabs` 数组改为：

```ts
const tabs: Tab[] = [
  { key: 'diary', label: '\u65e5\u8bb0', icon: PhNotebook, routeName: 'home' },
  { key: 'plan', label: '\u8ba1\u5212', icon: PhMapTrifold, routeName: 'plan' },
  { key: 'memory', label: '\u8bb0\u5fc6\u5e93', icon: PhBrain, routeName: 'memory' },
  { key: 'chat', label: '\u4f1a\u8bdd', icon: PhChatsCircle, routeName: 'chat' },
  { key: 'models', label: '\u6a21\u578b', icon: PhCpu, routeName: 'models' },
]
```

（`\u8ba1\u5212` = 计划。`activeKey` 计算逻辑不变——route.name 为 `plan` 时返回 `'plan'`，与 key 相等。）

`src/App.vue`：两个集合改为：

```ts
const tabRouteNames = new Set(['home', 'plan', 'memory', 'chat', 'models'])

const tabViewNames = ['TimelineScene', 'PlanScene', 'MemoryScene', 'ChatScene', 'ModelsScene']
```

- [ ] **Step 4: 删除 HomeScene**

删除 `src/pages/HomeScene.vue` 与 `src/shared/copy/homeScene.ts`。然后全局搜索确认无残留引用：

```powershell
rg -n "HomeScene|homeSceneCopy" src/
```

Expected: 无匹配（`features/home/DayDetailDrawer.vue` 保留——WeekView 在用）。

- [ ] **Step 5: redirect 测试（TDD 补齐）**

新建 `src/__tests__/redirects.spec.ts`：

```ts
import { describe, expect, it } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'

import { appRoutes } from '@/router'

function buildRouter() {
  return createRouter({ history: createMemoryHistory(), routes: appRoutes })
}

describe('legacy route redirects', () => {
  it('redirects /review/:diaryId to the write page', async () => {
    const router = buildRouter()
    await router.push('/review/123')
    expect(router.currentRoute.value.name).toBe('write-edit')
    expect(router.currentRoute.value.params.id).toBe('123')
  })
})
```

Run: `npx vitest run src/__tests__/redirects.spec.ts`
Expected: PASS。

- [ ] **Step 6: 全量回归**

Run: `npm test && npm run type-check && npm run lint`
Expected: 全部通过。若 `App.spec.ts` 等存量测试因导航项变化失败，按新的 5 项导航更新断言（当前已确认 App.spec.ts 不引用旧导航，预期无失败）。

- [ ] **Step 7: 手动冒烟**

`npm run dev` 后验证：导航 5 项；`/` 默认日视图；切换周视图看板列正常；`?view=week&date=2026-08-24` 直接打开对应周；`/review/123` 跳转 `/write/123`；写作页无任务元素。

- [ ] **Step 8: 提交**

```bash
git add -A
git commit -m "feat(timeline): land unified timeline at / with 5-tab navigation"
```

- [ ] **Step 9: 推送并开 PR**

```bash
git push -u origin feature/merge-diary-weekly-review-pr2
```

PR 描述模板：

```markdown
### 标题
feat(timeline): 统一时间轴骨架落地 /，导航 6→5

### 功能描述
- 新增 TimelineScene（`/?view=day|week&date=YYYY-MM-DD`）与 timeline store（视图/日期与 URL query 双向同步）
- DayView（写作优先 + 任务折叠行）+ WeekView（HomeScene 周看板迁移）
- 导航 6→5：日记·计划·记忆库·会话·模型（计划升为一级入口）
- `/review/:diaryId` → `/write/:id` 重定向；删除 HomeScene（nudge / replyBanner / streak 压力点不迁移）

### 实现思路
- 视图/日期状态收敛到 timeline store 并与 URL query 同步，刷新不丢状态
- 周看板脚本与样式从 HomeScene 原样迁移，仅替换数据源，降低迁移风险

### 测试方式
- npx vitest run src/__tests__/timelineQuery.spec.ts src/__tests__/timelineStore.spec.ts src/__tests__/TaskFoldRow.spec.ts src/__tests__/redirects.spec.ts
```

---

## PR-3 周视图完整形态（P1）

> 内容：周概览行（心情曲线 + 统计）、周信卡片（三态 + 结构化计划区块 + 勾选）、`/weekly` 重定向、删除 WeeklyScene。

### Task 3.1: mood-trends 与 weekly 的前端 API 类型（TDD）

**Files:**
- Modify: `src/shared/api/card.ts`（`getMoodTrends` 参数对象化）
- Modify: `src/shared/api/weekly.ts`（`WeeklyReport` 新字段）
- Test: `src/__tests__/weeklyApi.spec.ts`（追加）

- [ ] **Step 1: 写失败测试**

`src/__tests__/weeklyApi.spec.ts` 的 describe 内追加（`sampleReport` 定义处补充结构化字段见 Step 3）：

```ts
  it('passes date range to mood trends', async () => {
    const { getMoodTrends } = await import('@/shared/api/card')
    get.mockResolvedValue({ data: [] })
    await getMoodTrends({ date_from: '2026-08-24', date_to: '2026-08-30' })
    expect(get).toHaveBeenCalledWith('/api/v1/cards/stats/mood-trends', {
      params: { date_from: '2026-08-24', date_to: '2026-08-30' },
    })
  })

  it('returns structured plan execution fields on reports', async () => {
    get.mockResolvedValue({ data: [structuredReport] })
    const result = await listWeekly({ limit: 52 })
    expect(result[0].plan_executions[0].title).toBe('早睡挑战')
    expect(result[0].week_tasks[0].status).toBe('done')
  })
```

并在文件顶部 `sampleReport` 旁增加：

```ts
const structuredReport = {
  ...sampleReport,
  plan_executions: [
    {
      plan_id: 'p1',
      title: '早睡挑战',
      done: 1,
      total: 2,
      source_refs: [{ type: 'diary', id: 1, date: '2026-08-24', snippet: '最近总是熬夜' }],
    },
  ],
  week_tasks: [
    { task_id: 't1', title: '周末散步', status: 'done', source: 'agent', due_date: null },
  ],
}
```

（`getMoodTrends` 测试需要该文件的 `get` mock 与 axios mock 头，直接复用。）

- [ ] **Step 2: 运行确认失败**

Run: `npx vitest run src/__tests__/weeklyApi.spec.ts`
Expected: FAIL —— `getMoodTrends` 现签名是 `(days: number)`；`plan_executions` 类型不存在。

- [ ] **Step 3: 实现**

`src/shared/api/card.ts` 的 mood trends 段改为：

```ts
export interface MoodTrendParams {
  days?: number
  date_from?: string
  date_to?: string
}

export async function getMoodTrends(params: MoodTrendParams = {}): Promise<MoodTrendPoint[]> {
  const client = await getHttpClient()
  const { data } = await client.get<MoodTrendPoint[]>('/api/v1/cards/stats/mood-trends', {
    params,
  })
  return data
}
```

运行 `rg -n "getMoodTrends" src/` 确认除测试外无调用方（`MoodTrendChart` 是纯 cards 输入，不走此函数；若有调用方则同步改为参数对象形式）。

`src/shared/api/weekly.ts` 顶部补 `import type { SourceRef } from './plan'`，类型与接口改为：

```ts
export interface PlanExecutionSummary {
  plan_id: string
  title: string
  done: number
  total: number
  source_refs: SourceRef[]
}

export interface WeekTaskItem {
  task_id: string
  title: string
  status: 'pending' | 'done' | 'skipped'
  source: 'manual' | 'agent'
  due_date: string | null
}

export interface WeeklyReport {
  id: number
  period_start: string
  period_end: string
  content: string
  diary_count: number
  card_count: number
  avg_mood: number | null
  token_cost: number | null
  execution_tier: string | null
  created_at: string
  plan_executions: PlanExecutionSummary[]
  week_tasks: WeekTaskItem[]
}
```

- [ ] **Step 4: 运行确认通过**

Run: `npx vitest run src/__tests__/weeklyApi.spec.ts && npm run type-check`
Expected: PASS（若 `weeklyApi.spec.ts` 既有用例的 `sampleReport` 因新必填字段报类型错，为 `sampleReport` 补 `plan_executions: [], week_tasks: []`）。

- [ ] **Step 5: 提交**

```bash
git add src/shared/api/card.ts src/shared/api/weekly.ts src/__tests__/weeklyApi.spec.ts
git commit -m "feat(api): typed structured weekly fields and mood-trend range params"
```

### Task 3.2: timeline store 扩展周数据（TDD）

**Files:**
- Modify: `src/stores/timeline.ts`
- Test: `src/__tests__/timelineStore.spec.ts`（追加）

- [ ] **Step 1: 写失败测试**

`timelineStore.spec.ts` 追加（mock 已就绪，补 `listTasks` mock 返回值控制）：

```ts
  it('week view also loads tasks and mood trend', async () => {
    const { listTasks } = await import('@/shared/api/plan')
    const { getMoodTrends } = await import('@/shared/api/card')
    vi.mocked(listTasks).mockResolvedValue([
      { id: 't1', plan_id: null, title: '散步', note: null, due_date: '2026-08-26', status: 'done', source: 'manual', completed_at: null },
    ] as never)
    vi.mocked(getMoodTrends).mockResolvedValue([
      { date: '2026-08-25', avg_mood: 0.6, card_count: 1 },
    ])

    const store = useTimelineStore()
    await store.setDate('2026-08-25')
    await store.setView('week')

    expect(listTasks).toHaveBeenCalledWith({ date_from: '2026-08-24', date_to: '2026-08-30' })
    expect(getMoodTrends).toHaveBeenCalledWith({ date_from: '2026-08-24', date_to: '2026-08-30' })
    expect(store.tasks).toHaveLength(1)
    expect(store.moodTrend).toHaveLength(1)
  })
```

（文件顶部 `vi.mock('@/shared/api/plan', ...)` 需调整为具名导出 mock：`vi.mock('@/shared/api/plan', () => ({ listTasks: vi.fn(async () => []) }))`。）

- [ ] **Step 2: 运行确认失败**

Run: `npx vitest run src/__tests__/timelineStore.spec.ts`
Expected: 新用例 FAIL（store 无 tasks/moodTrend）。

- [ ] **Step 3: 实现**

`src/stores/timeline.ts`：import 增加 `listTasks, type TaskItem`（`@/shared/api/plan`）与 `getMoodTrends, type MoodTrendPoint`（`@/shared/api/card`）。state 增加：

```ts
  const tasks = ref<TaskItem[]>([])
  const moodTrend = ref<MoodTrendPoint[]>([])
```

`load()` 改为：

```ts
  async function load() {
    loading.value = true
    error.value = null
    const { from, to } = range.value
    try {
      if (view.value === 'week') {
        const [entryRows, taskRows, trendRows] = await Promise.all([
          listDiaryEntries({ date_from: from, date_to: to, limit: 100 }),
          listTasks({ date_from: from, date_to: to }),
          getMoodTrends({ date_from: from, date_to: to }).catch(() => []),
        ])
        entries.value = entryRows
        tasks.value = taskRows
        moodTrend.value = trendRows
      } else {
        entries.value = await listDiaryEntries({ date_from: from, date_to: to, limit: 100 })
        tasks.value = []
        moodTrend.value = []
      }
    } catch (err) {
      error.value = formatApiError(err, '加载日记失败')
    } finally {
      loading.value = false
    }
  }
```

return 列表增加 `tasks`、`moodTrend`。

- [ ] **Step 4: 运行确认通过**

Run: `npx vitest run src/__tests__/timelineStore.spec.ts`
Expected: 全部 PASS。

- [ ] **Step 5: 提交**

```bash
git add src/stores/timeline.ts src/__tests__/timelineStore.spec.ts
git commit -m "feat(timeline): load week tasks and mood trend in week view"
```

### Task 3.3: WeekMoodChart 组件

**Files:**
- Create: `src/features/timeline/WeekMoodChart.vue`

- [ ] **Step 1: 实现**

新建 `src/features/timeline/WeekMoodChart.vue`（渲染方式参照 `src/features/memory/MoodTrendChart.vue` 的 `window.echarts` 全局实例约定）：

```vue
<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'

import type { MoodTrendPoint } from '@/shared/api/card'

const props = defineProps<{ points: MoodTrendPoint[] }>()

const chartEl = ref<HTMLDivElement | null>(null)
/* eslint-disable-next-line @typescript-eslint/no-explicit-any */
let chartInstance: any = null

/* eslint-disable-next-line @typescript-eslint/no-explicit-any */
function render() {
  if (!chartEl.value || props.points.length === 0) return
  /* eslint-disable-next-line @typescript-eslint/no-explicit-any */
  const echarts = (window as any).echarts
  if (!echarts) return

  const style = getComputedStyle(document.documentElement)
  const accent = style.getPropertyValue('--color-accent').trim() || '#D4A574'
  const muted = style.getPropertyValue('--color-text-secondary').trim() || '#7A6F63'
  const rule = style.getPropertyValue('--color-border').trim() || 'rgba(61,52,41,0.12)'

  if (chartInstance) chartInstance.dispose()
  chartInstance = echarts.init(chartEl.value, null, { renderer: 'svg' })
  chartInstance.setOption({
    animation: false,
    grid: { top: 6, right: 4, bottom: 18, left: 4 },
    xAxis: {
      type: 'category',
      data: props.points.map((p) => p.date.slice(5)),
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: muted, fontSize: 9, interval: 2 },
    },
    yAxis: { type: 'value', show: false, min: 0, max: 1 },
    series: [
      {
        type: 'line',
        data: props.points.map((p) => p.avg_mood),
        smooth: true,
        symbol: 'circle',
        symbolSize: 4,
        lineStyle: { color: accent, width: 1.5 },
        itemStyle: { color: accent },
        areaStyle: {
          color: {
            type: 'linear',
            x: 0,
            y: 0,
            x2: 0,
            y2: 1,
            colorStops: [
              { offset: 0, color: `${accent}33` },
              { offset: 1, color: `${accent}00` },
            ],
          },
        },
      },
    ],
    tooltip: {
      trigger: 'axis',
      appendToBody: true,
      /* eslint-disable-next-line @typescript-eslint/no-explicit-any */
      formatter: (params: any) => {
        const index = params[0]?.dataIndex
        if (typeof index !== 'number' || !props.points[index]) return ''
        const p = props.points[index]
        return `${p.date} · ${p.card_count} 张卡片`
      },
    },
  })
}

onMounted(render)
watch(() => props.points, render)
onBeforeUnmount(() => {
  if (chartInstance) chartInstance.dispose()
  chartInstance = null
})
</script>

<template>
  <div v-if="points.length > 0" ref="chartEl" class="week-mood-chart" />
</template>

<style scoped>
.week-mood-chart {
  width: 100%;
  height: 3.5rem;
}
</style>
```

- [ ] **Step 2: 类型检查 + 提交**

Run: `npm run type-check`

```bash
git add src/features/timeline/WeekMoodChart.vue
git commit -m "feat(timeline): add compact week mood chart"
```

### Task 3.4: WeeklyLetterCard 组件（TDD）

**Files:**
- Create: `src/features/timeline/WeeklyLetterCard.vue`
- Test: `src/__tests__/WeeklyLetterCard.spec.ts`

- [ ] **Step 1: 写失败测试**

新建 `src/__tests__/WeeklyLetterCard.spec.ts`：

```ts
import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

const push = vi.fn()

vi.mock('vue-router', () => ({
  useRouter: () => ({ push }),
}))

vi.mock('@/shared/api/weekly', () => ({
  listWeekly: vi.fn(async () => []),
  getLatestWeekly: vi.fn(async () => null),
  generateWeekly: vi.fn(async () => ({})),
  regenerateWeekly: vi.fn(async () => ({})),
  deleteWeekly: vi.fn(async () => undefined),
}))

import WeeklyLetterCard from '@/features/timeline/WeeklyLetterCard.vue'
import { useWeeklyStore } from '@/stores/weekly'
import { usePlanStore } from '@/stores/plan'

const report = {
  id: 9,
  period_start: '2026-08-24',
  period_end: '2026-08-30',
  content: '这一周你经历了许多。',
  diary_count: 3,
  card_count: 5,
  avg_mood: 0.6,
  token_cost: 800,
  execution_tier: 'medium',
  created_at: '2026-08-30T20:00:00',
  plan_executions: [
    {
      plan_id: 'p1',
      title: '早睡挑战',
      done: 1,
      total: 2,
      source_refs: [{ type: 'diary', id: 7, date: '2026-08-24' }],
    },
  ],
  week_tasks: [
    { task_id: 't1', title: '周末散步', status: 'pending', source: 'agent', due_date: null },
  ],
}

function mountCard(weekStartIso: string, reports: WeeklyReport[] = []) {
  setActivePinia(createPinia())
  const weeklyStore = useWeeklyStore()
  const planStore = usePlanStore()
  planStore.toggleTask = vi.fn(async () => {})
  weeklyStore.reports = reports
  return { wrapper: mount(WeeklyLetterCard, { props: { weekStartIso } }), weeklyStore, planStore }
}

describe('WeeklyLetterCard', () => {
  it('offers generation only for the current week when no report exists', () => {
    const future = mountCard('2099-01-04') // far future week = not current
    expect(future.wrapper.text()).toContain('这一周没有留下周信')
    expect(future.wrapper.text()).not.toContain('生成本周周记')

    const current = mountCard(currentMondayIso())
    expect(current.wrapper.text()).toContain('生成本周周记')
  })

  it('renders the letter with structured plan block', () => {
    const { wrapper } = mountCard(report.period_start, [report])
    expect(wrapper.text()).toContain('这一周你经历了许多。')
    expect(wrapper.text()).toContain('早睡挑战')
    expect(wrapper.text()).toContain('1/2')
    expect(wrapper.text()).toContain('周末散步')
    expect(wrapper.text()).toContain('AI 建议')
  })

  it('falls back to plain content for legacy reports without structured data', () => {
    const legacy = { ...report, plan_executions: [], week_tasks: [] }
    const { wrapper } = mountCard(legacy.period_start, [legacy])
    expect(wrapper.text()).toContain('这一周你经历了许多。')
    expect(wrapper.find('.letter-plan').exists()).toBe(false)
  })

  it('toggles week tasks through the plan store and updates locally', async () => {
    const { wrapper, planStore } = mountCard(report.period_start, [report])
    await wrapper.find('.letter-plan__task input[type="checkbox"]').setValue(true)
    expect(planStore.toggleTask).toHaveBeenCalledWith('t1', 'pending')
  })
})

function currentMondayIso(): string {
  const now = new Date()
  const day = now.getDay()
  const diff = day === 0 ? -6 : 1 - day
  const monday = new Date(now.getFullYear(), now.getMonth(), now.getDate() + diff)
  return `${monday.getFullYear()}-${String(monday.getMonth() + 1).padStart(2, '0')}-${String(monday.getDate()).padStart(2, '0')}`
}
```

（import 区需补 `import type { WeeklyReport } from '@/shared/api/weekly'`——type-only import 编译期擦除，不受 `vi.mock` 工厂影响。组件挂载时仅当 `weeklyStore.reports` 为空才调用 `loadReports()`：测试注入数据后跳过加载，断言不会被异步覆盖；空态用例则走 mock 的 `listWeekly` 返回 `[]`。）

- [ ] **Step 2: 运行确认失败**

Run: `npx vitest run src/__tests__/WeeklyLetterCard.spec.ts`
Expected: FAIL —— 组件不存在。

- [ ] **Step 3: 实现**

新建 `src/features/timeline/WeeklyLetterCard.vue`：

```vue
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { PhArrowSquareOut } from '@phosphor-icons/vue'

import AITypingIndicator from '@/shared/components/AITypingIndicator.vue'
import GameButton from '@/shared/components/GameButton.vue'
import GlassPanel from '@/shared/components/GlassPanel.vue'
import { weeklyCopy } from '@/shared/copy/weekly'
import { timelineCopy as copy } from '@/shared/copy/timeline'
import { useWeeklyStore } from '@/stores/weekly'
import { usePlanStore } from '@/stores/plan'
import { diarySummary, startOfWeekMonday, toIsoDate } from '@/shared/utils/diaryFormat'
import type { WeekTaskItem } from '@/shared/api/weekly'

const props = defineProps<{ weekStartIso: string }>()

const router = useRouter()
const weeklyStore = useWeeklyStore()
const planStore = usePlanStore()

const expanded = ref(false)

const currentWeekStartIso = computed(() => toIsoDate(startOfWeekMonday(new Date())))
const isCurrentWeek = computed(() => props.weekStartIso === currentWeekStartIso.value)

const report = computed(() =>
  weeklyStore.reports.find((r) => r.period_start === props.weekStartIso) ?? null,
)

const previewText = computed(() =>
  report.value ? diarySummary(report.value.content, 160) : '',
)

const hasStructuredPlan = computed(
  () =>
    report.value != null &&
    (report.value.plan_executions.length > 0 || report.value.week_tasks.length > 0),
)

const showGenerate = computed(() => isCurrentWeek.value && report.value == null)

onMounted(() => {
  if (weeklyStore.reports.length === 0) {
    weeklyStore.loadReports().catch(() => {})
  }
})

function diaryRefs(items: { type: string; date?: string }[]) {
  return items.filter((r) => r.type === 'diary')
}

function openRef(refId: string | number) {
  router.push(`/write/${refId}`)
}

async function onGenerate() {
  try {
    await weeklyStore.generate()
  } catch {
    /* surfaced via weeklyStore.error */
  }
}

async function onRegenerate() {
  try {
    await weeklyStore.regenerate()
  } catch {
    /* surfaced via weeklyStore.error */
  }
}

async function onToggleTask(task: WeekTaskItem) {
  const next = task.status === 'done' ? 'pending' : 'done'
  try {
    await planStore.toggleTask(task.task_id, task.status)
    task.status = next
  } catch {
    /* surfaced via planStore.error */
  }
}
</script>

<template>
  <GlassPanel class="weekly-letter" elevated>
    <header class="weekly-letter__head">
      <h2 class="weekly-letter__title">{{ weeklyCopy.letterTitle }}</h2>
      <GameButton
        v-if="showGenerate"
        variant="primary"
        :disabled="weeklyStore.generating"
        @click="onGenerate"
      >
        {{ weeklyStore.generating ? weeklyCopy.generating : weeklyCopy.generate }}
      </GameButton>
      <GameButton
        v-else-if="isCurrentWeek && report"
        variant="secondary"
        :disabled="weeklyStore.generating"
        @click="onRegenerate"
      >
        {{ weeklyCopy.regenerate }}
      </GameButton>
    </header>

    <p v-if="weeklyStore.error" class="weekly-letter__error">{{ weeklyStore.error }}</p>

    <div v-if="weeklyStore.generating" class="weekly-letter__typing">
      <AITypingIndicator :label="weeklyCopy.generating" />
    </div>

    <template v-else-if="report">
      <p class="weekly-letter__meta">
        {{ weeklyCopy.diaryCount(report.diary_count) }} · {{ weeklyCopy.cardCount(report.card_count) }}
      </p>
      <p class="weekly-letter__content font-diary">
        {{ expanded ? report.content : previewText }}
      </p>
      <button type="button" class="weekly-letter__toggle" @click="expanded = !expanded">
        {{ expanded ? weeklyCopy.collapse : weeklyCopy.expand }}
      </button>

      <div v-if="hasStructuredPlan" class="letter-plan">
        <p class="letter-plan__title">{{ copy.planSectionTitle }}</p>
        <div v-for="pe in report.plan_executions" :key="pe.plan_id" class="letter-plan__row">
          <span class="letter-plan__name">{{ pe.title }}</span>
          <span class="letter-plan__count">{{ pe.done }}/{{ pe.total }}</span>
          <button
            v-for="(r, i) in diaryRefs(pe.source_refs)"
            :key="i"
            type="button"
            class="letter-plan__ref"
            @click="openRef(r.id)"
          >
            {{ copy.fromDiary(r.date) }} <PhArrowSquareOut :size="12" />
          </button>
        </div>

        <label v-for="task in report.week_tasks" :key="task.task_id" class="letter-plan__task">
          <input
            type="checkbox"
            :checked="task.status === 'done'"
            @change="onToggleTask(task)"
          />
          <span class="letter-plan__task-title" :class="{ 'is-done': task.status === 'done' }">
            {{ task.title }}
          </span>
          <span v-if="task.source === 'agent'" class="letter-plan__task-source">
            {{ copy.aiSuggested }}
          </span>
        </label>
      </div>
    </template>

    <p v-else class="weekly-letter__empty">
      {{ isCurrentWeek ? weeklyCopy.emptyHint : copy.noLetterThisWeek }}
    </p>
  </GlassPanel>
</template>

<style scoped>
.weekly-letter {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
.weekly-letter__head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
}
.weekly-letter__title {
  font-size: 0.9375rem;
  font-weight: 600;
  color: var(--color-text-primary);
  margin: 0;
}
.weekly-letter__error {
  font-size: 0.8125rem;
  color: var(--color-danger, #b3563e);
  margin: 0;
}
.weekly-letter__meta {
  font-size: 0.75rem;
  color: var(--color-text-secondary);
  margin: 0;
}
.weekly-letter__content {
  font-size: 0.875rem;
  line-height: 1.7;
  color: var(--color-text-primary);
  margin: 0;
  white-space: pre-line;
}
.weekly-letter__toggle {
  align-self: flex-start;
  border: none;
  background: transparent;
  color: var(--color-accent, #d4a574);
  font-size: 0.8125rem;
  cursor: pointer;
  padding: 0;
}
.weekly-letter__empty {
  font-size: 0.8125rem;
  color: var(--color-text-secondary);
  margin: 0;
}
.letter-plan {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  border-top: 1px solid var(--color-border, rgba(61, 52, 41, 0.12));
  padding-top: 0.75rem;
}
.letter-plan__title {
  font-size: 0.75rem;
  font-weight: 600;
  letter-spacing: 0.04em;
  color: var(--color-text-secondary);
  margin: 0;
}
.letter-plan__row {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.8125rem;
}
.letter-plan__name {
  flex: 1;
  color: var(--color-text-primary);
}
.letter-plan__count {
  color: var(--color-text-secondary);
  font-variant-numeric: tabular-nums;
}
.letter-plan__ref {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  border: none;
  background: transparent;
  color: var(--color-accent, #d4a574);
  font-size: 0.75rem;
  cursor: pointer;
  padding: 0;
}
.letter-plan__task {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-size: 0.8125rem;
  cursor: pointer;
}
.letter-plan__task-title.is-done {
  text-decoration: line-through;
  color: var(--color-text-secondary);
}
.letter-plan__task-source {
  font-size: 0.6875rem;
  color: var(--color-text-secondary);
  border: 1px solid var(--color-border, rgba(61, 52, 41, 0.12));
  border-radius: 999px;
  padding: 0.0625rem 0.5rem;
}
</style>
```

- [ ] **Step 4: 补文案键**

`src/shared/copy/weekly.ts` 的对象内追加（放在 `emptyHint` 之后）：

```ts
  letterTitle: '本周的信',
  expand: '展开全文',
  collapse: '收起',
```

`src/shared/copy/timeline.ts` 的对象内追加（放在 `taskSectionDone` 之后）：

```ts
  noLetterThisWeek: '这一周没有留下周信',
  planSectionTitle: '这一周的计划',
  fromDiary: (date: string) => `来自 ${date} 的日记`,
  aiSuggested: 'AI 建议',
```

- [ ] **Step 5: 运行确认通过**

Run: `npx vitest run src/__tests__/WeeklyLetterCard.spec.ts && npm run type-check`
Expected: 全部 PASS。

- [ ] **Step 6: 提交**

```bash
git add src/features/timeline/WeeklyLetterCard.vue src/__tests__/WeeklyLetterCard.spec.ts src/shared/copy/weekly.ts src/shared/copy/timeline.ts
git commit -m "feat(timeline): weekly letter card with structured plan block"
```

### Task 3.5: WeekView 集成周概览行与周信卡片

**Files:**
- Modify: `src/features/timeline/WeekView.vue`
- Modify: `src/shared/copy/timeline.ts`

- [ ] **Step 1: 文案键**

`src/shared/copy/timeline.ts` 追加：

```ts
  weekOverview: (diary: number, card: number, done: number, total: number) =>
    `${diary} 篇日记 · ${card} 张卡片 · 任务 ${done}/${total}`,
```

- [ ] **Step 2: 修改 WeekView**

`src/features/timeline/WeekView.vue` 的 script 增加导入：

```ts
import WeekMoodChart from '@/features/timeline/WeekMoodChart.vue'
import WeeklyLetterCard from '@/features/timeline/WeeklyLetterCard.vue'
```

script 增加统计 computed（放在 `weekLabel` 之后）：

```ts
const weekStats = computed(() => {
  const cards = cardStore.cards.filter((c) => {
    const d = c.created_at.slice(0, 10)
    return d >= timeline.weekStartIso && d <= timeline.weekEndIso
  })
  const done = timeline.tasks.filter((t) => t.status === 'done').length
  return {
    diary: timeline.entries.length,
    card: cards.length,
    taskDone: done,
    taskTotal: timeline.tasks.length,
  }
})
```

template 在 `</div>`（周导航结束）与 `<div class="week-view__kanban"` 之间插入：

```vue
    <div class="week-view__overview">
      <WeekMoodChart :points="timeline.moodTrend" />
      <p class="week-view__stats">
        {{ copy.weekOverview(weekStats.diary, weekStats.card, weekStats.taskDone, weekStats.taskTotal) }}
      </p>
    </div>
```

template 在 `<div class="week-view__kanban">…</div>` 之后、`<Teleport>` 之前插入：

```vue
    <WeeklyLetterCard :week-start-iso="timeline.weekStartIso" />
```

`<style scoped>` 追加：

```css
.week-view__overview {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.5rem 0.75rem;
}
.week-view__stats {
  margin: 0;
  font-size: 0.75rem;
  color: var(--color-text-secondary);
  white-space: nowrap;
}
```

（WeekMoodChart 在 `points.length === 0` 时自渲染空 `div`，概览行无数据时仅显示统计文本——无需额外空态分支。）

- [ ] **Step 3: 类型检查 + 存量测试**

Run: `npm run type-check && npm test`
Expected: 通过。

- [ ] **Step 4: 提交**

```bash
git add src/features/timeline/WeekView.vue src/shared/copy/timeline.ts
git commit -m "feat(timeline): week overview row and letter card in week view"
```

### Task 3.6: /weekly 重定向 + 删除 WeeklyScene + weekly 依赖瘦身

**Files:**
- Modify: `src/router/index.ts:70-73`
- Delete: `src/pages/WeeklyScene.vue`
- Modify: `src/stores/weekly.ts`
- Modify: `src/shared/api/weekly.ts`
- Modify: `src/shared/copy/weekly.ts`
- Modify: `src/__tests__/weeklyApi.spec.ts`

- [ ] **Step 1: 路由重定向**

`src/router/index.ts` 将 `/weekly` 路由替换为重定向（保留 `/weekly` 兼容收藏夹/历史地址，落到时间轴周视图）：

```ts
    {
      path: '/weekly',
      redirect: { path: '/', query: { view: 'week' } },
    },
```

- [ ] **Step 2: 删除 WeeklyScene**

删除 `src/pages/WeeklyScene.vue`（414 行，功能已由周视图 + WeeklyLetterCard 完整承接）。

运行 `rg -n "WeeklyScene" src/` 确认无残留引用（router 已在上一步移除）。

- [ ] **Step 3: weekly store 瘦身**

WeeklyScene 是 `loadLatest`/`latest`/`remove`/`deleting` 的唯一调用方，删除后为死代码。`src/stores/weekly.ts` 改为：

```ts
import { defineStore } from 'pinia'
import { ref } from 'vue'

import {
  generateWeekly,
  listWeekly,
  regenerateWeekly,
  type WeeklyReport,
} from '@/shared/api/weekly'
import { formatApiError } from '@/shared/utils/apiError'

export const useWeeklyStore = defineStore('weekly', () => {
  const reports = ref<WeeklyReport[]>([])
  const loading = ref(false)
  const generating = ref(false)
  const error = ref<string | null>(null)

  async function loadReports(): Promise<WeeklyReport[]> {
    loading.value = true
    error.value = null
    try {
      reports.value = await listWeekly({ limit: 52 })
      return reports.value
    } catch (err) {
      error.value = formatApiError(err, '加载周记失败')
      throw err
    } finally {
      loading.value = false
    }
  }

  function _upsert(report: WeeklyReport) {
    const idx = reports.value.findIndex((r) => r.period_start === report.period_start)
    if (idx >= 0) reports.value.splice(idx, 1, report)
    else reports.value.unshift(report)
    reports.value.sort((a, b) => b.period_start.localeCompare(a.period_start))
  }

  async function generate(): Promise<WeeklyReport> {
    generating.value = true
    error.value = null
    try {
      const report = await generateWeekly()
      _upsert(report)
      return report
    } catch (err) {
      error.value = formatApiError(err, '生成周记失败')
      throw err
    } finally {
      generating.value = false
    }
  }

  async function regenerate(): Promise<WeeklyReport> {
    generating.value = true
    error.value = null
    try {
      const report = await regenerateWeekly()
      _upsert(report)
      return report
    } catch (err) {
      error.value = formatApiError(err, '重新生成周记失败')
      throw err
    } finally {
      generating.value = false
    }
  }

  return {
    reports,
    loading,
    generating,
    error,
    loadReports,
    generate,
    regenerate,
  }
})
```

（`isAxiosError` 与 404 分支随 `loadLatest` 一并移除；`latest` 由 `reports[0]` 派生的场景已不存在——WeeklyLetterCard 按 `period_start` 匹配。）

- [ ] **Step 4: API 层瘦身**

`src/shared/api/weekly.ts` 删除 `getLatestWeekly`、`deleteWeekly` 两个函数（后端端点保留不动，仅移除前端死代码）。

- [ ] **Step 5: 更新 API 测试**

`src/__tests__/weeklyApi.spec.ts`：import 行改为

```ts
import { generateWeekly, listWeekly } from '@/shared/api/weekly'
```

删除 `getLatestWeekly`、`deleteWeekly` 的两个用例（`rg -n "getLatestWeekly|deleteWeekly" src/__tests__/weeklyApi.spec.ts` 定位）。同时给 `sampleReport` 补 `plan_executions: [], week_tasks: []`（Task 3.1 Step 4 若未处理）。

- [ ] **Step 6: weekly 文案瘦身**

`src/shared/copy/weekly.ts` 删除仅被 WeeklyScene 使用的键：`title`、`back`、`subtitle`、`empty`、`historyTitle`、`loadError`、`generateError`、`delete`、`deleteConfirm`、`deleteConfirmDesc`、`cancel`、`confirmDelete`。保留：`generate`、`generating`、`regenerate`、`emptyHint`、`diaryCount`、`cardCount`、`letterTitle`、`expand`、`collapse`。

运行 `rg -n "weeklyCopy\." src/` 确认保留键之外无引用。

- [ ] **Step 7: 全量验证**

Run: `npm run type-check && npm test`
Expected: 通过，无 WeeklyScene 残留引用报错。

- [ ] **Step 8: 提交**

```bash
git add -A src/router/index.ts src/pages/WeeklyScene.vue src/stores/weekly.ts src/shared/api/weekly.ts src/shared/copy/weekly.ts src/__tests__/weeklyApi.spec.ts
git commit -m "refactor(weekly): redirect /weekly to timeline week view and slim store"
```

### Task 3.7: PR-3 收尾验证

- [ ] **Step 1: 全量回归**

Run: `npm run type-check && npm test`
Expected: 全部通过。

- [ ] **Step 2: 手动冒烟（可选但推荐）**

启动前后端，访问 `/#/`：
1. 切到周视图：概览行显示心情曲线与统计；7 列看板正常；底部周信卡片三态（未生成→生成按钮 / 已生成→预览展开 / 历史周→无信文案）。
2. 周信含结构化计划区块：计划行 `1/2`、任务勾选、AI 建议徽标、溯源链接跳 `/write/:id`。
3. 旧周报（无结构化数据）回退纯文本渲染。
4. 访问 `/#/weekly` 自动落到 `/#/?view=week`。

- [ ] **Step 3: 推送并开 PR**

```bash
git push -u origin feature/merge-diary-weekly-review-pr3
```

PR 描述模板（沿用仓库规范：标题 / 功能描述 / 实现思路 / 测试方式）：

```markdown
### 标题
feat(timeline): 周视图完整形态——周概览行 + 周信卡片（三态 + 结构化计划）

### 功能描述
- 周概览行：心情曲线（mood-trends 按周区间取数）+ 日记/卡片/任务统计
- 周信卡片：未生成/生成中/已生成三态；结构化计划执行区块（计划汇总、任务勾选、AI 建议溯源）；旧周报回退纯文本
- `/weekly` 重定向至时间轴周视图；删除 WeeklyScene；weekly store/API/文案瘦身

### 实现思路
- WeekMoodChart 复用全局 echarts 实例约定，SVG 渲染，0 数据自隐藏
- WeeklyLetterCard 从 weeklyStore 按 period_start 匹配报告，挂载时按需 loadReports
- 任务勾选直接走 planStore.toggleTask（PATCH /tasks/:id），与计划场景共享状态

### 测试方式
- npx vitest run src/__tests__/WeeklyLetterCard.spec.ts src/__tests__/weeklyApi.spec.ts src/__tests__/timelineStore.spec.ts
- 手动冒烟见 Task 3.7 Step 2
```

---

## PR-4 月视图 + 详情面板（P1）

> 内容：月视图（月历网格，CalendarView 改造迁移）、详情面板（ReviewScene aside 迁移，浏览态）、DayView/WeekView 点击行为改为打开面板。`/review` 与 `ReviewScene` 的清理留给 PR-6（卡片视图迁移完成后统一删）。

### Task 4.1: MonthView 组件（TDD）

**Files:**
- Create: `src/features/timeline/MonthView.vue`
- Test: `src/__tests__/MonthView.spec.ts`

- [ ] **Step 1: 写失败测试**

新建 `src/__tests__/MonthView.spec.ts`：

```ts
import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('@/shared/api/diary', () => ({
  listDiaryEntries: vi.fn(async () => []),
}))
vi.mock('@/shared/api/plan', () => ({
  listTasks: vi.fn(async () => []),
  getTodayTasks: vi.fn(async () => []),
}))
vi.mock('@/shared/api/card', () => ({
  getMoodTrends: vi.fn(async () => []),
}))

import MonthView from '@/features/timeline/MonthView.vue'
import { useTimelineStore } from '@/stores/timeline'
import { toIsoDate } from '@/shared/utils/diaryFormat'
import type { DiaryEntry } from '@/shared/api/diary'

const todayIso = toIsoDate(new Date())

function makeEntry(id: number, date: string): DiaryEntry {
  return { id, content: 'x', date, weather: null, reply: null, created_at: date, updated_at: date }
}

function mountView() {
  setActivePinia(createPinia())
  const store = useTimelineStore()
  const wrapper = mount(MonthView)
  return { wrapper, store }
}

describe('MonthView', () => {
  it('renders the anchor month label and highlights today', () => {
    const { wrapper } = mountView()
    const label = new Date().toLocaleDateString('zh-CN', { year: 'numeric', month: 'long' })
    expect(wrapper.text()).toContain(label)
    expect(wrapper.find(`[data-iso="${todayIso}"]`).classes()).toContain('is-today')
  })

  it('marks days with entries and jumps to day view on click', async () => {
    const { wrapper, store } = mountView()
    store.entries = [makeEntry(1, todayIso)]
    await nextTick()

    const todayCell = wrapper.find(`[data-iso="${todayIso}"]`)
    expect(todayCell.classes()).toContain('has-entry')

    const otherDay = toIsoDate(new Date(new Date().getFullYear(), new Date().getMonth(), 12))
    await wrapper.find(`[data-iso="${otherDay}"]`).trigger('click')
    expect(store.view).toBe('day')
    expect(store.date).toBe(otherDay)
  })
})
```

（import 区需补 `import { nextTick } from 'vue'`。`store.entries = [...]` 直接赋值——setup store 的 ref 经 pinia 解包为可写属性。）

- [ ] **Step 2: 运行确认失败**

Run: `npx vitest run src/__tests__/MonthView.spec.ts`
Expected: FAIL —— 组件不存在。

- [ ] **Step 3: 实现**

新建 `src/features/timeline/MonthView.vue`（月历逻辑迁移自 `src/features/review/CalendarView.vue`，数据源改为 timeline store）：

```vue
<script setup lang="ts">
import { computed } from 'vue'
import { PhCaretLeft, PhCaretRight } from '@phosphor-icons/vue'

import { timelineCopy as copy } from '@/shared/copy/timeline'
import { useTimelineStore } from '@/stores/timeline'
import { parseLocalDate, toIsoDate } from '@/shared/utils/diaryFormat'

const timeline = useTimelineStore()

const monthLabel = computed(() =>
  parseLocalDate(timeline.date).toLocaleDateString('zh-CN', { year: 'numeric', month: 'long' }),
)

const datesWithEntries = computed(
  () => new Set(timeline.entries.map((e) => e.date).filter((d): d is string => Boolean(d))),
)

const calendarCells = computed(() => {
  const anchor = parseLocalDate(timeline.date)
  const year = anchor.getFullYear()
  const month = anchor.getMonth()
  const firstDay = new Date(year, month, 1)
  const startOffset = firstDay.getDay() === 0 ? 6 : firstDay.getDay() - 1
  const daysInMonth = new Date(year, month + 1, 0).getDate()

  const cells: Array<{ iso: string | null; day: number | null; hasEntry: boolean }> = []
  for (let i = 0; i < startOffset; i += 1) {
    cells.push({ iso: null, day: null, hasEntry: false })
  }
  for (let day = 1; day <= daysInMonth; day += 1) {
    const iso = toIsoDate(new Date(year, month, day))
    cells.push({ iso, day, hasEntry: datesWithEntries.value.has(iso) })
  }
  return cells
})

async function openDay(iso: string | null) {
  if (!iso) return
  await timeline.setDate(iso)
  await timeline.setView('day')
}
</script>

<template>
  <section class="month-view">
    <div class="month-view__nav">
      <button type="button" class="month-view__nav-btn" @click="timeline.shiftPeriod(-1)">
        <PhCaretLeft :size="14" />
      </button>
      <span class="month-view__label">{{ monthLabel }}</span>
      <button type="button" class="month-view__nav-btn" @click="timeline.shiftPeriod(1)">
        <PhCaretRight :size="14" />
      </button>
      <button
        v-if="!timeline.isToday"
        type="button"
        class="month-view__nav-btn month-view__back"
        @click="timeline.goToday()"
      >
        {{ copy.backToToday }}
      </button>
    </div>

    <div class="month-view__weekdays">
      <span v-for="label in ['一', '二', '三', '四', '五', '六', '日']" :key="label">
        {{ label }}
      </span>
    </div>

    <div class="month-view__grid">
      <button
        v-for="(cell, index) in calendarCells"
        :key="`${cell.iso ?? 'empty'}-${index}`"
        type="button"
        class="month-view__cell"
        :class="{
          'is-empty': !cell.day,
          'has-entry': cell.hasEntry,
          'is-today': cell.iso === timeline.todayIso,
        }"
        :data-iso="cell.iso"
        :disabled="!cell.day"
        @click="openDay(cell.iso)"
      >
        <span v-if="cell.day">{{ cell.day }}</span>
        <span v-if="cell.hasEntry" class="month-view__dot" aria-hidden="true" />
      </button>
    </div>
  </section>
</template>

<style scoped>
.month-view {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
.month-view__nav {
  display: flex;
  align-items: center;
  gap: 0.75rem;
}
.month-view__nav-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 0.25rem;
  width: 2rem;
  height: 2rem;
  border-radius: 0.5rem;
  border: 1px solid var(--color-border);
  background: var(--color-surface-raised);
  color: var(--color-text-secondary);
  cursor: pointer;
}
.month-view__back {
  width: auto;
  padding: 0 0.5rem;
  font-size: 0.8125rem;
}
.month-view__label {
  font-size: 0.9375rem;
  font-weight: 600;
  color: var(--color-text-primary);
}
.month-view__weekdays {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 0.25rem;
  font-size: 0.6875rem;
  color: var(--color-text-secondary);
  text-align: center;
}
.month-view__grid {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 0.25rem;
}
.month-view__cell {
  position: relative;
  aspect-ratio: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 0.5rem;
  border: 1px solid transparent;
  background: var(--color-surface-raised);
  font-size: 0.8125rem;
  color: var(--color-text-primary);
  cursor: pointer;
  transition:
    border-color 0.2s ease,
    background 0.2s ease;
}
.month-view__cell.is-empty {
  visibility: hidden;
  pointer-events: none;
}
.month-view__cell.has-entry:hover {
  border-color: var(--color-border);
}
.month-view__cell.is-today {
  border-color: var(--color-accent);
  background: color-mix(in srgb, var(--color-accent) 14%, var(--color-surface-raised));
  font-weight: 600;
}
.month-view__dot {
  position: absolute;
  bottom: 0.25rem;
  width: 0.375rem;
  height: 0.375rem;
  border-radius: 50%;
  background: var(--color-accent);
}
</style>
```

（与 CalendarView 的差异：数据源由 `props.entries` 改为 `timeline.entries`（store 在 month view 已按整月范围取数）；新增 `is-today` 高亮；点击行为由 `emit('selectDate')` 改为「跳该日 + 切日视图」——设计 5.3 的减法取舍，不做周跳转。）

- [ ] **Step 4: 运行确认通过**

Run: `npx vitest run src/__tests__/MonthView.spec.ts && npm run type-check`
Expected: PASS。

- [ ] **Step 5: 提交**

```bash
git add src/features/timeline/MonthView.vue src/__tests__/MonthView.spec.ts
git commit -m "feat(timeline): month view grid with today highlight and day jump"
```

### Task 4.2: 详情面板 DetailPanel（TDD）

**Files:**
- Create: `src/features/timeline/DetailPanel.vue`
- Test: `src/__tests__/DetailPanel.spec.ts`
- Modify: `src/shared/copy/timeline.ts`

- [ ] **Step 1: 补文案键**

`src/shared/copy/timeline.ts` 追加：

```ts
  detailReplyLabel: '回信',
  detailContinue: '继续编辑',
  detailViewReply: '查看回信',
  detailGetReply: '获取回信',
  detailExport: '导出 Markdown',
  detailDelete: '删除日记',
  detailDeleteConfirm: '确定删除这篇日记吗？',
  detailDeleteConfirmDesc: '删除后无法恢复，关联的记忆卡片不受影响',
  detailDeleteCancel: '取消',
  detailDeleteConfirmBtn: '确认删除',
```

- [ ] **Step 2: 写失败测试**

新建 `src/__tests__/DetailPanel.spec.ts`：

```ts
import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

const push = vi.fn()

vi.mock('vue-router', () => ({
  useRouter: () => ({ push }),
}))

vi.mock('@/shared/api/diary', () => ({
  listDiaryEntries: vi.fn(async () => []),
}))
vi.mock('@/shared/api/analysis', () => ({
  getAnalysis: vi.fn(async () => { throw Object.assign(new Error('404'), { response: { status: 404 } }) }),
}))
vi.mock('@/shared/api/card', () => ({
  listCards: vi.fn(async () => []),
}))
vi.mock('@/shared/utils/cardFormat', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/shared/utils/cardFormat')>()),
  findCardForDiary: vi.fn(() => null),
}))

import DetailPanel from '@/features/timeline/DetailPanel.vue'
import { useTimelineStore } from '@/stores/timeline'
import { useDiaryStore } from '@/stores/diary'
import type { DiaryEntry } from '@/shared/api/diary'

const entry: DiaryEntry = {
  id: 7,
  content: '今天走了很久，想通了一些事。',
  date: '2026-08-25',
  weather: '晴',
  reply: '听起来散步帮你理清了思绪。',
  created_at: '2026-08-25T21:00:00',
  updated_at: '2026-08-25T21:30:00',
}

function mountPanel() {
  setActivePinia(createPinia())
  const timeline = useTimelineStore()
  const diaryStore = useDiaryStore()
  diaryStore.removeEntry = vi.fn(async () => {})
  timeline.entries = [entry]
  timeline.selectEntry(7)
  return { wrapper: mount(DetailPanel), timeline, diaryStore }
}

describe('DetailPanel', () => {
  it('renders date, weather, summary, status and reply preview', () => {
    const { wrapper } = mountPanel()
    expect(wrapper.text()).toContain('2026-08-25')
    expect(wrapper.text()).toContain('晴')
    expect(wrapper.text()).toContain('今天走了很久')
    expect(wrapper.text()).toContain('听起来散步帮你理清了思绪')
  })

  it('navigates to write page on continue', async () => {
    const { wrapper } = mountPanel()
    await wrapper.findAll('button').find((b) => b.text().includes('继续编辑'))!.trigger('click')
    expect(push).toHaveBeenCalledWith('/write/7')
  })

  it('navigates to analysis page on view reply', async () => {
    const { wrapper } = mountPanel()
    await wrapper.findAll('button').find((b) => b.text().includes('查看回信'))!.trigger('click')
    expect(push).toHaveBeenCalledWith('/analysis/7')
  })

  it('deletes entry after confirmation and clears selection', async () => {
    const { wrapper, timeline, diaryStore } = mountPanel()
    await wrapper.findAll('button').find((b) => b.text().includes('删除日记'))!.trigger('click')
    await wrapper.findAll('button').find((b) => b.text().includes('确认删除'))!.trigger('click')
    expect(diaryStore.removeEntry).toHaveBeenCalledWith(7)
    expect(timeline.selectedEntry).toBeNull()
  })

  it('hides reply block for drafts', () => {
    const draft = { ...entry, reply: null }
    setActivePinia(createPinia())
    const timeline = useTimelineStore()
    timeline.entries = [draft]
    timeline.selectEntry(7)
    const wrapper = mount(DetailPanel)
    expect(wrapper.text()).not.toContain('回信')
  })
})
```

（`find(...)!` 非空断言在 vitest 环境可用；若 lint 报 no-non-null-assertion，改为先断言存在再 trigger。）

- [ ] **Step 3: 运行确认失败**

Run: `npx vitest run src/__tests__/DetailPanel.spec.ts`
Expected: FAIL —— 组件不存在。

- [ ] **Step 4: 实现**

新建 `src/features/timeline/DetailPanel.vue`（面板逻辑迁移自 `src/pages/ReviewScene.vue` 的 `aside.review-scene__detail` 区段）：

```vue
<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import { PhXCircle } from '@phosphor-icons/vue'

import CardTypeBadge from '@/features/card/CardTypeBadge.vue'
import EmotionChips from '@/features/card/EmotionChips.vue'
import GameButton from '@/shared/components/GameButton.vue'
import GlassPanel from '@/shared/components/GlassPanel.vue'
import { timelineCopy as copy } from '@/shared/copy/timeline'
import { useTimelineStore } from '@/stores/timeline'
import { useDiaryStore } from '@/stores/diary'
import { useCardStore } from '@/stores/card'
import { useAnalysisStore } from '@/stores/analysis'
import { formatApiError } from '@/shared/utils/apiError'
import { findCardForDiary } from '@/shared/utils/cardFormat'
import {
  diaryEntrySummary,
  diaryStatus,
  diaryStatusLabel,
  diarySummary,
} from '@/shared/utils/diaryFormat'

const router = useRouter()
const timeline = useTimelineStore()
const diaryStore = useDiaryStore()
const cardStore = useCardStore()
const analysisStore = useAnalysisStore()

const showDeleteConfirm = ref(false)
const deleteError = ref<string | null>(null)

const entry = computed(() => timeline.selectedEntry)

const linkedCard = computed(() =>
  entry.value ? findCardForDiary(cardStore.cards, entry.value.id) : null,
)

const aiReplyPreview = computed(() => {
  const text = analysisStore.current?.reply?.trim() || entry.value?.reply?.trim() || ''
  return text ? diarySummary(text, 160) : null
})

const showAiPreview = computed(
  () => entry.value != null && diaryStatus(entry.value) !== 'draft' && Boolean(aiReplyPreview.value),
)

watch(
  entry,
  (next) => {
    showDeleteConfirm.value = false
    deleteError.value = null
    analysisStore.clear()
    if (next && diaryStatus(next) !== 'draft') {
      analysisStore.loadForDiary(next.id).catch(() => {})
    }
  },
  { immediate: true },
)

function close() {
  timeline.selectEntry(null)
}

function continueWriting() {
  if (!entry.value) return
  router.push(`/write/${entry.value.id}`)
}

function viewReply() {
  if (!entry.value) return
  router.push(`/analysis/${entry.value.id}`)
}

function exportMarkdown() {
  if (!entry.value) return
  const e = entry.value
  const date = e.date || '未知日期'
  const weather = e.weather ? `  \n*天气：${e.weather}*` : ''
  const aiAns = e.reply?.trim() || analysisStore.current?.reply?.trim() || ''
  const md = `# ${date}\n${weather}\n\n## 日记\n\n${e.content}\n${aiAns ? `\n---\n\n## 回信\n\n${aiAns}\n` : ''}`
  const blob = new Blob([md], { type: 'text/markdown;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `nightdiary-${date}.md`
  a.click()
  URL.revokeObjectURL(url)
}

async function executeDelete() {
  if (!entry.value) return
  showDeleteConfirm.value = false
  deleteError.value = null
  const id = entry.value.id
  try {
    await diaryStore.removeEntry(id)
    timeline.selectEntry(null)
    await timeline.load()
  } catch (err) {
    deleteError.value = formatApiError(err, '删除日记失败')
  }
}
</script>

<template>
  <GlassPanel v-if="entry" class="detail-panel" elevated>
    <button type="button" class="detail-panel__close" title="关闭" @click="close">
      <PhXCircle :size="16" />
    </button>

    <p class="detail-panel__date">{{ entry.date ?? entry.created_at.slice(0, 10) }}</p>
    <p v-if="entry.weather" class="detail-panel__weather">{{ entry.weather }}</p>

    <div v-if="linkedCard" class="detail-panel__card-origin">
      <EmotionChips :emotions="linkedCard.emotions" :emotion="linkedCard.emotion" :size="12" />
      <CardTypeBadge :card-type="linkedCard.card_type" />
    </div>

    <p class="detail-panel__summary font-diary">
      {{ diaryEntrySummary(entry, cardStore.cards, 120) }}
    </p>

    <span
      v-if="diaryStatusLabel(diaryStatus(entry))"
      class="detail-panel__chip"
    >
      {{ diaryStatusLabel(diaryStatus(entry)) }}
    </span>

    <div v-if="showAiPreview" class="detail-panel__ai">
      <p class="detail-panel__ai-label">{{ copy.detailReplyLabel }}</p>
      <p class="detail-panel__ai-preview font-diary">{{ aiReplyPreview }}</p>
    </div>

    <div class="detail-panel__actions">
      <GameButton variant="secondary" @click="continueWriting">{{ copy.detailContinue }}</GameButton>
      <GameButton
        v-if="diaryStatus(entry) !== 'draft'"
        variant="primary"
        @click="viewReply"
      >
        {{ entry.reply?.trim() ? copy.detailViewReply : copy.detailGetReply }}
      </GameButton>
      <GameButton variant="ghost" @click="exportMarkdown">{{ copy.detailExport }}</GameButton>
      <GameButton variant="ghost" class="detail-panel__delete" @click="showDeleteConfirm = true">
        {{ copy.detailDelete }}
      </GameButton>
    </div>

    <p v-if="deleteError" class="detail-panel__error">{{ deleteError }}</p>

    <div v-if="showDeleteConfirm" class="detail-panel__confirm">
      <p class="detail-panel__confirm-title">{{ copy.detailDeleteConfirm }}</p>
      <p class="detail-panel__confirm-desc">{{ copy.detailDeleteConfirmDesc }}</p>
      <div class="detail-panel__confirm-actions">
        <GameButton variant="ghost" @click="showDeleteConfirm = false">
          {{ copy.detailDeleteCancel }}
        </GameButton>
        <GameButton variant="primary" @click="executeDelete">{{ copy.detailDeleteConfirmBtn }}</GameButton>
      </div>
    </div>
  </GlassPanel>
</template>

<style scoped>
.detail-panel {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 0.625rem;
  padding: 1.25rem;
}
.detail-panel__close {
  position: absolute;
  top: 0.75rem;
  right: 0.75rem;
  border: none;
  background: transparent;
  color: var(--color-text-secondary);
  cursor: pointer;
  padding: 0.25rem;
}
.detail-panel__close:hover {
  color: var(--color-text-primary);
}
.detail-panel__date {
  margin: 0;
  font-size: 0.9375rem;
  font-weight: 600;
  color: var(--color-text-primary);
}
.detail-panel__weather {
  margin: 0;
  font-size: 0.75rem;
  color: var(--color-text-secondary);
}
.detail-panel__card-origin {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}
.detail-panel__summary {
  margin: 0;
  font-size: 0.875rem;
  line-height: 1.7;
  color: var(--color-text-primary);
}
.detail-panel__chip {
  align-self: flex-start;
  font-size: 0.6875rem;
  color: var(--color-text-secondary);
  border: 1px solid var(--color-border);
  border-radius: 999px;
  padding: 0.125rem 0.5rem;
}
.detail-panel__ai {
  border-top: 1px solid var(--color-border);
  padding-top: 0.625rem;
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
}
.detail-panel__ai-label {
  margin: 0;
  font-size: 0.6875rem;
  font-weight: 600;
  letter-spacing: 0.04em;
  color: var(--color-text-secondary);
}
.detail-panel__ai-preview {
  margin: 0;
  font-size: 0.8125rem;
  line-height: 1.7;
  color: var(--color-text-primary);
}
.detail-panel__actions {
  display: flex;
  flex-direction: column;
  gap: 0.375rem;
  margin-top: 0.5rem;
}
.detail-panel__delete {
  color: var(--color-danger, #b3563e);
}
.detail-panel__error {
  margin: 0;
  font-size: 0.75rem;
  color: var(--color-danger, #b3563e);
}
.detail-panel__confirm {
  border-top: 1px solid var(--color-border);
  padding-top: 0.75rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.detail-panel__confirm-title {
  margin: 0;
  font-size: 0.875rem;
  font-weight: 600;
  color: var(--color-text-primary);
}
.detail-panel__confirm-desc {
  margin: 0;
  font-size: 0.75rem;
  color: var(--color-text-secondary);
}
.detail-panel__confirm-actions {
  display: flex;
  justify-content: flex-end;
  gap: 0.5rem;
}
</style>
```

（与 ReviewScene aside 的差异：选中态从路由参数改为 `timeline.selectedEntry`；删除后 `timeline.load()` 刷新当前时间轴范围而非整页 entries；`entriesOnSelectedDate` 多篇分支不迁移——时间轴日视图一天多篇时列表平铺展示，无需选择器。）

- [ ] **Step 5: 运行确认通过**

Run: `npx vitest run src/__tests__/DetailPanel.spec.ts && npm run type-check`
Expected: PASS。

- [ ] **Step 6: 提交**

```bash
git add src/features/timeline/DetailPanel.vue src/__tests__/DetailPanel.spec.ts src/shared/copy/timeline.ts
git commit -m "feat(timeline): diary detail panel for browse mode"
```

### Task 4.3: TimelineScene 集成月视图与详情面板 + 点击行为改造

**Files:**
- Modify: `src/pages/TimelineScene.vue`
- Modify: `src/features/timeline/DayView.vue`
- Modify: `src/features/timeline/WeekView.vue`
- Test: `src/__tests__/TimelineScene.spec.ts`（新建）

- [ ] **Step 1: 写失败测试**

新建 `src/__tests__/TimelineScene.spec.ts`：

```ts
import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('vue-router', () => ({
  useRoute: () => ({ query: {}, params: {} }),
  useRouter: () => ({ push: vi.fn(), replace: vi.fn() }),
}))

vi.mock('@/shared/api/diary', () => ({
  listDiaryEntries: vi.fn(async () => []),
}))
vi.mock('@/shared/api/plan', () => ({
  listTasks: vi.fn(async () => []),
  getTodayTasks: vi.fn(async () => []),
}))
vi.mock('@/shared/api/card', () => ({
  listCards: vi.fn(async () => []),
  getMoodTrends: vi.fn(async () => []),
}))
vi.mock('@/shared/api/weekly', () => ({
  listWeekly: vi.fn(async () => []),
  generateWeekly: vi.fn(async () => ({})),
  regenerateWeekly: vi.fn(async () => ({})),
}))
vi.mock('@/shared/api/analysis', () => ({
  getAnalysis: vi.fn(async () => null),
}))

import { nextTick } from 'vue'
import TimelineScene from '@/pages/TimelineScene.vue'
import { useTimelineStore } from '@/stores/timeline'

function mountScene() {
  setActivePinia(createPinia())
  return { wrapper: mount(TimelineScene), timeline: useTimelineStore() }
}

describe('TimelineScene', () => {
  it('renders month view when view is month', async () => {
    const { wrapper, timeline } = mountScene()
    timeline.view = 'month'
    await nextTick()
    expect(wrapper.find('.month-view').exists()).toBe(true)
  })

  it('renders detail panel when an entry is selected', async () => {
    const { wrapper, timeline } = mountScene()
    timeline.entries = [
      { id: 3, content: 'x', date: '2026-08-25', weather: null, reply: null, created_at: '2026-08-25', updated_at: '2026-08-25' },
    ]
    timeline.selectEntry(3)
    await nextTick()
    expect(wrapper.find('.detail-panel').exists()).toBe(true)
  })
})
```

（TimelineScene 挂载的子组件链较深（DayView 引 TaskFoldRow → planStore、WeekView 引 WeeklyLetterCard → weeklyStore），故 mock 覆盖 diary/plan/card/weekly/analysis 五个 api 模块。若 mount 因 echarts 全局实例缺失告警，不影响断言——WeekMoodChart 仅在 points 非空时 init。）

- [ ] **Step 2: 运行确认失败**

Run: `npx vitest run src/__tests__/TimelineScene.spec.ts`
Expected: FAIL —— `.month-view` / `.detail-panel` 不存在。

- [ ] **Step 3: 修改 TimelineScene**

`src/pages/TimelineScene.vue`：

1. script 增加导入：

```ts
import MonthView from '@/features/timeline/MonthView.vue'
import DetailPanel from '@/features/timeline/DetailPanel.vue'
```

2. script 增加视图标签映射（switcher 从三元表达式改为查表）：

```ts
import type { TimelineView } from '@/shared/utils/timelineQuery'

const viewLabels: Record<TimelineView, string> = {
  day: copy.viewDay,
  week: copy.viewWeek,
  month: copy.viewMonth,
}
```

3. template 中 switcher 改为：

```vue
        <button
          v-for="v in (['day', 'week', 'month'] as const)"
          :key="v"
          type="button"
          role="tab"
          class="timeline-scene__switch"
          :class="{ 'is-active': timeline.view === v }"
          :aria-selected="timeline.view === v"
          @click="timeline.setView(v)"
        >
          {{ viewLabels[v] }}
        </button>
```

4. template 中视图区改为双栏布局：

```vue
    <div class="timeline-scene__layout" :class="{ 'has-detail': timeline.selectedEntry }">
      <div class="timeline-scene__main">
        <DayView v-if="timeline.view === 'day'" />
        <WeekView v-else-if="timeline.view === 'week'" />
        <MonthView v-else />
      </div>
      <aside v-if="timeline.selectedEntry" class="timeline-scene__detail">
        <DetailPanel />
      </aside>
    </div>
```

5. `<style scoped>` 追加：

```css
.timeline-scene__layout {
  display: grid;
  grid-template-columns: 1fr;
  gap: 1rem;
  align-items: start;
}
.timeline-scene__detail {
  min-width: 0;
}
@media (min-width: 64rem) {
  .timeline-scene__layout.has-detail {
    grid-template-columns: 1fr min(20rem, 34%);
  }
  .timeline-scene__detail {
    position: sticky;
    top: 1rem;
    max-height: calc(100vh - 4rem);
    overflow-y: auto;
  }
}
@media (max-width: 63.99rem) {
  .timeline-scene__detail {
    position: fixed;
    inset: 0;
    z-index: 60;
    overflow-y: auto;
    padding: 4.5rem 1rem 1.5rem;
    background: color-mix(in srgb, var(--color-bg) 92%, transparent);
    backdrop-filter: blur(8px);
  }
}
```

（移动端全屏覆盖见设计 5.4；`z-index: 60` 避开 NavTabs 层级——若实际层级冲突，以 `src/App.vue` 现有 z-index 体系为准调整。）

- [ ] **Step 4: 改造 DayView 点击行为**

`src/features/timeline/DayView.vue`：

1. `openEntry` 简化为跳写作页（面板打开走 selectEntry）：

```ts
function openEntry(entryId: number) {
  router.push(`/write/${entryId}`)
}
```

2. 日记卡模板拆分——预览区点击打开面板，「继续写」独立按钮进编辑态：

```vue
        <div class="day-view__diary-head">
          <span class="day-view__diary-date">{{ timeline.date }}</span>
          <span v-if="entry.weather" class="day-view__diary-weather">{{ entry.weather }}</span>
        </div>
        <button type="button" class="day-view__diary-body" @click="timeline.selectEntry(entry.id)">
          <span class="day-view__diary-preview font-diary">
            {{ diarySummary(entry.content, 120) }}
          </span>
        </button>
        <div class="day-view__diary-actions">
          <button type="button" class="day-view__diary-continue" @click="openEntry(entry.id)">
            {{ copy.writeDiary }}
          </button>
        </div>
```

3. `<style scoped>` 中 `.day-view__diary-continue` 从按钮内 span 样式改为独立按钮样式（原样式若定义在 `.day-view__diary-body` 内部选择器下，移出为顶层类）：

```css
.day-view__diary-actions {
  display: flex;
  justify-content: flex-end;
}
.day-view__diary-continue {
  border: none;
  background: transparent;
  color: var(--color-accent, #d4a574);
  font-size: 0.8125rem;
  cursor: pointer;
  padding: 0.25rem 0;
}
.day-view__diary-continue:hover {
  text-decoration: underline;
}
```

- [ ] **Step 5: 改造 WeekView 点击行为**

`src/features/timeline/WeekView.vue` 的 `openEntry` 改为打开详情面板：

```ts
function openEntry(entry: DiaryEntry) {
  timeline.selectEntry(entry.id)
}
```

模板中两处调用点同步去掉第二参数：看板日记卡 `@click="openEntry(item.entry)"`；`onDrawerOpenDiary`（DayDetailDrawer 的 open-diary 事件）改为 `timeline.selectEntry(entry.id)`。

（`DiaryEntry` import 已存在，无需新增。）

- [ ] **Step 6: 运行确认通过**

Run: `npx vitest run src/__tests__/TimelineScene.spec.ts && npm run type-check`
Expected: PASS（若 DayView/WeekView 存量测试因 openEntry 签名变化失败，同步更新调用断言）。

- [ ] **Step 7: 全量回归**

Run: `npm test && npm run lint`
Expected: 全部通过。

- [ ] **Step 8: 提交**

```bash
git add -A
git commit -m "feat(timeline): integrate month view and detail panel with browse-mode clicks"
```

### Task 4.4: PR-4 收尾验证

- [ ] **Step 1: 手动冒烟**

启动前后端，访问 `/#/`：
1. 视图切换器出现「日 / 周 / 月」；月视图网格有日记的日期带圆点，今日高亮；点任意日期落到该日日视图。
2. 日视图点日记卡预览 → 右侧滑出详情面板（桌面双栏、窄屏全屏覆盖）；面板显示日期/天气/情绪/状态/回信预览；「继续编辑」→ `/write/:id`；「查看回信」→ `/analysis/:id`；导出 Markdown 下载正常；删除带二次确认。
3. 周视图点看板日记卡 → 同一面板；关闭面板回到看板。

- [ ] **Step 2: 推送并开 PR**

```bash
git push -u origin feature/merge-diary-weekly-review-pr4
```

PR 描述模板：

```markdown
### 标题
feat(timeline): 月视图 + 详情面板（浏览态）

### 功能描述
- 月视图：月历网格（CalendarView 改造迁移），有日记圆点、今日高亮，点击日期跳日视图
- 详情面板：ReviewScene aside 迁移——日期/天气/关联卡片/状态/回信预览 + 编辑/回信/导出/删除
- 日/周视图点击日记卡改为打开面板（浏览态），「继续写」独立按钮进编辑态
- 桌面双栏 `1fr min(20rem, 34%)`，移动端全屏覆盖

### 实现思路
- MonthView 数据源为 timeline store（month range），不再走 props
- DetailPanel 选中态走 timeline.selectedEntry，删除后刷新当前范围
- 面板逻辑与写作页（/write）彻底分离：浏览不进编辑器

### 测试方式
- npx vitest run src/__tests__/MonthView.spec.ts src/__tests__/DetailPanel.spec.ts src/__tests__/TimelineScene.spec.ts
- 手动冒烟见 Task 4.4 Step 1
```

---

## PR-5 计划场景升级（P2）

> 内容：计划卡 `source_refs` 溯源渲染（引用块 + 日记跳转）、过期任务中性灰（减法纪律：无红色警告）、PlanScene 文案集中化。导航入口已在 PR-2 落地（NavTabs「计划」）。AI 提案确认沿用会话场景 PlanProposalCard，本板块不重复。

### Task 5.1: PlanRefsBlock 组件（TDD）

**Files:**
- Create: `src/features/plan/PlanRefsBlock.vue`
- Create: `src/shared/copy/plan.ts`
- Test: `src/__tests__/PlanRefsBlock.spec.ts`

- [ ] **Step 1: 创建文案文件**

新建 `src/shared/copy/plan.ts`：

```ts
/** Centralized copy for the plan scene. */

export const planCopy = {
  title: '我的计划',
  todayTitle: '今日待办',
  todayEmpty: '今天没有待办，享受当下吧',
  plansTitle: '计划',
  plansEmpty: '还没有计划，可以在对话中让 AI 帮你规划',
  aiBadge: 'AI 建议',
  delete: '删除',
  refsLabel: '来自你的日记',
} as const
```

- [ ] **Step 2: 写失败测试**

新建 `src/__tests__/PlanRefsBlock.spec.ts`：

```ts
import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

const push = vi.fn()

vi.mock('vue-router', () => ({
  useRouter: () => ({ push }),
}))

import PlanRefsBlock from '@/features/plan/PlanRefsBlock.vue'
import type { SourceRef } from '@/shared/api/plan'

const refs: SourceRef[] = [
  { type: 'diary', id: 7, date: '2026-08-12', snippet: '最近三周 5 次提到失眠与换工作的犹豫' },
  { type: 'diary', id: 9, date: '2026-08-19', snippet: '又聊到了那件悬而未决的事' },
  { type: 'episodic', id: 'mem-1' },
]

function mountBlock(list: SourceRef[]) {
  return mount(PlanRefsBlock, { props: { refs: list } })
}

describe('PlanRefsBlock', () => {
  it('renders diary refs with snippet and short date link', () => {
    const wrapper = mountBlock(refs)
    expect(wrapper.text()).toContain('来自你的日记')
    expect(wrapper.text()).toContain('最近三周 5 次提到失眠')
    expect(wrapper.text()).toContain('8/12')
    expect(wrapper.text()).toContain('8/19')
  })

  it('navigates to the diary page on date click', async () => {
    const wrapper = mountBlock(refs)
    await wrapper.findAll('.plan-refs__date')[0].trigger('click')
    expect(push).toHaveBeenCalledWith('/write/7')
  })

  it('renders nothing when no diary refs', () => {
    const wrapper = mountBlock([{ type: 'episodic', id: 'mem-1' }])
    expect(wrapper.find('.plan-refs').exists()).toBe(false)
  })
})
```

- [ ] **Step 3: 运行确认失败**

Run: `npx vitest run src/__tests__/PlanRefsBlock.spec.ts`
Expected: FAIL —— 组件不存在。

- [ ] **Step 4: 实现**

新建 `src/features/plan/PlanRefsBlock.vue`：

```vue
<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { PhArrowSquareOut } from '@phosphor-icons/vue'

import { planCopy } from '@/shared/copy/plan'
import type { SourceRef } from '@/shared/api/plan'

const props = defineProps<{ refs: SourceRef[] }>()

const router = useRouter()

const diaryRefs = computed(() => props.refs.filter((r) => r.type === 'diary'))

function shortDate(iso: string): string {
  const [, m, d] = iso.split('-')
  return `${Number(m)}/${Number(d)}`
}

function openRef(ref: SourceRef) {
  router.push(`/write/${ref.id}`)
}
</script>

<template>
  <blockquote v-if="diaryRefs.length > 0" class="plan-refs">
    <p class="plan-refs__label">{{ planCopy.refsLabel }}</p>
    <div v-for="(ref, i) in diaryRefs" :key="i" class="plan-refs__row">
      <span v-if="ref.snippet" class="plan-refs__snippet">{{ ref.snippet }}</span>
      <button v-if="ref.date" type="button" class="plan-refs__date" @click="openRef(ref)">
        {{ shortDate(ref.date) }} <PhArrowSquareOut :size="11" />
      </button>
    </div>
  </blockquote>
</template>

<style scoped>
.plan-refs {
  margin: 8px 0;
  padding: 8px 12px;
  border-left: 2px solid var(--color-accent, #d4a574);
  background: color-mix(in srgb, var(--color-accent) 6%, transparent);
  border-radius: 0 8px 8px 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.plan-refs__label {
  margin: 0;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  color: var(--color-text-secondary, #71717a);
}
.plan-refs__row {
  display: flex;
  align-items: baseline;
  gap: 8px;
  font-size: 13px;
}
.plan-refs__snippet {
  color: var(--color-text-primary);
  flex: 1;
}
.plan-refs__date {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  border: none;
  background: transparent;
  color: var(--color-accent, #d4a574);
  font-size: 12px;
  cursor: pointer;
  padding: 0;
  white-space: nowrap;
}
.plan-refs__date:hover {
  text-decoration: underline;
}
</style>
```

- [ ] **Step 5: 运行确认通过**

Run: `npx vitest run src/__tests__/PlanRefsBlock.spec.ts && npm run type-check`
Expected: PASS。

- [ ] **Step 6: 提交**

```bash
git add src/features/plan/PlanRefsBlock.vue src/shared/copy/plan.ts src/__tests__/PlanRefsBlock.spec.ts
git commit -m "feat(plan): render plan source refs with diary links"
```

### Task 5.2: PlanScene 集成溯源块与过期中性灰（TDD）

**Files:**
- Modify: `src/features/plan/PlanScene.vue`
- Test: `src/__tests__/PlanScene.spec.ts`（新建）

- [ ] **Step 1: 写失败测试**

新建 `src/__tests__/PlanScene.spec.ts`：

```ts
import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

vi.mock('vue-router', () => ({
  useRouter: () => ({ push: vi.fn() }),
}))

vi.mock('@/shared/api/plan', () => ({
  listPlans: vi.fn(async () => []),
  getTodayTasks: vi.fn(async () => []),
}))

import PlanScene from '@/features/plan/PlanScene.vue'
import { usePlanStore } from '@/stores/plan'
import { toIsoDate } from '@/shared/utils/diaryFormat'
import type { PlanItem, TaskItem } from '@/shared/api/plan'

const plan: PlanItem = {
  id: 'p1',
  title: '早睡挑战',
  motivation: null,
  source_refs: [{ type: 'diary', id: 7, date: '2026-08-12', snippet: '最近总是熬夜' }],
  status: 'active',
  source: 'agent',
  tasks: [],
}

const yesterday = toIsoDate(new Date(Date.now() - 86400000))
const tomorrow = toIsoDate(new Date(Date.now() + 86400000))

function task(id: string, due: string | null, status: TaskItem['status'] = 'pending'): TaskItem {
  return { id, plan_id: 'p1', title: `任务${id}`, note: null, due_date: due, status, source: 'manual', completed_at: null }
}

function mountScene(plans: PlanItem[] = [], todayTasks: TaskItem[] = []) {
  setActivePinia(createPinia())
  const store = usePlanStore()
  store.plans = plans
  store.todayTasks = todayTasks
  return { wrapper: mount(PlanScene), store }
}

describe('PlanScene', () => {
  it('renders source refs block inside plan card', () => {
    const { wrapper } = mountScene([plan])
    expect(wrapper.find('.plan-refs').exists()).toBe(true)
    expect(wrapper.text()).toContain('最近总是熬夜')
  })

  it('marks overdue tasks neutral gray without red', () => {
    const { wrapper } = mountScene([], [task('t1', yesterday), task('t2', tomorrow)])
    const rows = wrapper.findAll('.task-row')
    expect(rows[0].classes()).toContain('is-overdue')
    expect(rows[1].classes()).not.toContain('is-overdue')
  })

  it('does not mark done tasks overdue', () => {
    const { wrapper } = mountScene([], [task('t1', yesterday, 'done')])
    expect(wrapper.find('.task-row').classes()).not.toContain('is-overdue')
  })
})
```

- [ ] **Step 2: 运行确认失败**

Run: `npx vitest run src/__tests__/PlanScene.spec.ts`
Expected: FAIL —— `.plan-refs` 不存在、无 `is-overdue`。

- [ ] **Step 3: 实现**

`src/features/plan/PlanScene.vue` 修改：

1. script 改为：

```ts
<script setup lang="ts">
import { computed, onMounted } from 'vue'

import PlanRefsBlock from '@/features/plan/PlanRefsBlock.vue'
import { planCopy } from '@/shared/copy/plan'
import { usePlanStore } from '@/stores/plan'
import { toIsoDate } from '@/shared/utils/diaryFormat'

defineOptions({ name: 'PlanScene' })

const planStore = usePlanStore()

const todayIso = computed(() => toIsoDate(new Date()))

function isOverdue(dueDate: string | null, status: string): boolean {
  return Boolean(dueDate) && dueDate! < todayIso.value && status !== 'done'
}

onMounted(() => {
  planStore.loadPlans()
  planStore.loadTodayTasks()
})
</script>
```

2. template 的今日待办行增加 overdue 类（中性灰，无红色）：

```vue
        <div
          v-for="task in planStore.todayTasks"
          :key="task.id"
          class="task-row"
          :class="{ 'is-overdue': isOverdue(task.due_date, task.status) }"
        >
          <input
            type="checkbox"
            :checked="task.status === 'done'"
            @change="planStore.toggleTask(task.id, task.status)"
          />
          <span :class="{ done: task.status === 'done' }">{{ task.title }}</span>
          <span v-if="task.due_date" class="due">{{ task.due_date }}</span>
          <button class="btn-del" @click="planStore.removeTask(task.id)">×</button>
        </div>
```

3. template 的计划卡在 `plan-motivation` 之后、`plan-progress` 之前插入：

```vue
          <PlanRefsBlock :refs="plan.source_refs" />
```

4. template 中所有硬编码文案替换为 `planCopy.*`（标题、空态、AI 建议 badge、删除按钮）。

5. `<style scoped>` 追加（中性灰——减法纪律：过期不警示）：

```css
.task-row.is-overdue {
  opacity: 0.65;
}
.task-row.is-overdue .due {
  color: var(--color-text-secondary, #a1a1aa);
}
```

- [ ] **Step 4: 运行确认通过**

Run: `npx vitest run src/__tests__/PlanScene.spec.ts && npm run type-check`
Expected: PASS。

- [ ] **Step 5: 全量回归 + 提交**

Run: `npm test && npm run lint`
Expected: 全部通过。

```bash
git add src/features/plan/PlanScene.vue src/__tests__/PlanScene.spec.ts
git commit -m "feat(plan): source refs rendering and neutral overdue styling"
```

### Task 5.3: PR-5 收尾验证

- [ ] **Step 1: 手动冒烟**

访问 `/#/plan`：
1. 含 `source_refs` 的计划卡显示引用块（accent 左边线 + 摘录 + 日期链接），点日期跳 `/write/:id`。
2. 昨天到期未完成的任务整行降低不透明度，无红色/警告措辞；今天/明天到期的正常。
3. 已完成任务无 overdue 态。

- [ ] **Step 2: 推送并开 PR**

```bash
git push -u origin feature/merge-diary-weekly-review-pr5
```

PR 描述模板：

```markdown
### 标题
feat(plan): 计划卡溯源渲染 + 过期任务中性灰

### 功能描述
- 计划卡新增 source_refs 引用块：日记摘录 + 日期链接跳 /write/:id
- 过期任务中性灰（降低不透明度），无红色警告（减法纪律）
- PlanScene 文案集中化到 shared/copy/plan.ts

### 实现思路
- PlanRefsBlock 过滤 type=diary 的引用，短日期（8/12）+ 跳转按钮
- overdue 判定：due_date < today 且未完成；仅样式弱化不改数据

### 测试方式
- npx vitest run src/__tests__/PlanRefsBlock.spec.ts src/__tests__/PlanScene.spec.ts
- 手动冒烟见 Task 5.3 Step 1
```

---

## PR-6 记忆库吸收卡片视图 + 回顾页清理（P2）

> 内容：回顾页 `mode=cards` 视图（搜索 + 卡片列表 + 展开为日记 + 删除）迁移至 MemoryScene「记忆卡片」分区；跳转链接改为内嵌分区；删除 ReviewScene、CalendarView、TimelineView；`/review` 重定向 `/memory`。这是合并重构的收官 PR。

### Task 6.1: CardsSection 组件（TDD）

**Files:**
- Create: `src/features/memory/CardsSection.vue`
- Modify: `src/shared/copy/memory.ts`
- Test: `src/__tests__/CardsSection.spec.ts`

- [ ] **Step 1: 补文案键**

`src/shared/copy/memory.ts` 追加（放在 `goToCards` 之后，`goToCards` 本身在 Task 6.2 删除）：

```ts
  cardsSearchPlaceholder: '搜索记忆卡片……',
  cardsSearch: '搜索',
  cardsSearching: '搜索中……',
  cardsSearchEmpty: '没有找到匹配的记忆卡片',
  cardsEmpty: '还没有记忆卡片',
  cardsEmptyHint: '在日记页点击「记一笔」创建你的第一张卡片',
  cardsExpandToDiary: '展开为日记',
  cardsDelete: '删除',
```

- [ ] **Step 2: 写失败测试**

新建 `src/__tests__/CardsSection.spec.ts`：

```ts
import { describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createPinia, setActivePinia } from 'pinia'

const push = vi.fn()

vi.mock('vue-router', () => ({
  useRouter: () => ({ push }),
}))

const searchCards = vi.fn()

vi.mock('@/shared/api/card', () => ({
  searchCards: (...args: unknown[]) => searchCards(...args),
  listCards: vi.fn(async () => []),
}))

import CardsSection from '@/features/memory/CardsSection.vue'
import { useCardStore } from '@/stores/card'
import type { MemoryCard } from '@/shared/api/card'

const linkedCard: MemoryCard = {
  card_id: 'c1',
  diary_id: 7,
  event_summary: '散步时想通了换工作的事',
  emotions: ['平静'],
  emotion: '平静',
  card_type: 'event',
  tags: ['散步'],
  created_at: '2026-08-25T21:00:00',
}

const standaloneCard: MemoryCard = { ...linkedCard, card_id: 'c2', diary_id: null }

function mountSection(cards: MemoryCard[] = []) {
  setActivePinia(createPinia())
  const store = useCardStore()
  store.cards = cards
  store.expandCard = vi.fn(async () => ({ diary_id: 9, ...standaloneCard }))
  store.removeCard = vi.fn(async () => {})
  store.loadCards = vi.fn(async () => {})
  return { wrapper: mount(CardsSection), store }
}

describe('CardsSection', () => {
  it('renders cards with summary and time', () => {
    const { wrapper } = mountSection([linkedCard])
    expect(wrapper.text()).toContain('散步时想通了换工作的事')
    expect(wrapper.text()).toContain('平静')
  })

  it('shows empty state when no cards', () => {
    const { wrapper } = mountSection([])
    expect(wrapper.text()).toContain('还没有记忆卡片')
  })

  it('searches and replaces the list with results', async () => {
    searchCards.mockResolvedValue({ query: '散步', results: [standaloneCard] })
    const { wrapper } = mountSection([linkedCard])
    await wrapper.find('input').setValue('散步')
    await wrapper.find('input').trigger('keydown.enter')
    await Promise.resolve()
    expect(searchCards).toHaveBeenCalledWith('散步', 20)
    expect(wrapper.text()).not.toContain('散步时想通了换工作的事')
  })

  it('expands a standalone card into a diary and navigates', async () => {
    const { wrapper, store } = mountSection([standaloneCard])
    await wrapper.find('.cards-section__action-btn').trigger('click')
    await Promise.resolve()
    expect(store.expandCard).toHaveBeenCalledWith('c2')
    expect(push).toHaveBeenCalledWith('/write/9')
  })

  it('deletes a card', async () => {
    const { wrapper, store } = mountSection([linkedCard])
    const del = wrapper.findAll('.cards-section__action-btn').at(-1)!
    await del.trigger('click')
    expect(store.removeCard).toHaveBeenCalledWith('c1')
  })
})
```

（`MemoryCard` 若有更多必填字段以 `src/shared/api/card.ts` 实际定义为准补齐；`emotion`/`emotions`/`card_type`/`tags` 为 EmotionChips/CardTypeBadge 所需。）

- [ ] **Step 3: 运行确认失败**

Run: `npx vitest run src/__tests__/CardsSection.spec.ts`
Expected: FAIL —— 组件不存在。

- [ ] **Step 4: 实现**

新建 `src/features/memory/CardsSection.vue`（搜索与卡片列表逻辑迁移自 `src/pages/ReviewScene.vue` 的 `mode === 'cards'` 区段）：

```vue
<script setup lang="ts">
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { PhArrowSquareOut, PhMagnifyingGlass, PhXCircle } from '@phosphor-icons/vue'

import CardTypeBadge from '@/features/card/CardTypeBadge.vue'
import EmotionChips from '@/features/card/EmotionChips.vue'
import GameButton from '@/shared/components/GameButton.vue'
import { memoryCopy as copy } from '@/shared/copy/memory'
import { useCardStore } from '@/stores/card'
import { searchCards, type CardSearchResult, type MemoryCard } from '@/shared/api/card'
import { formatApiError } from '@/shared/utils/apiError'

const router = useRouter()
const cardStore = useCardStore()

const searchQuery = ref('')
const searchResults = ref<CardSearchResult[]>([])
const searchLoading = ref(false)
const searchActive = ref(false)
const error = ref<string | null>(null)

const displayCards = computed<MemoryCard[]>(() =>
  searchActive.value ? searchResults.value : cardStore.cards,
)

async function doSearch() {
  const q = searchQuery.value.trim()
  if (!q) {
    searchActive.value = false
    searchResults.value = []
    return
  }
  searchLoading.value = true
  searchActive.value = true
  error.value = null
  try {
    const result = await searchCards(q, 20)
    searchResults.value = result.results
  } catch (err) {
    error.value = formatApiError(err, '搜索失败')
  } finally {
    searchLoading.value = false
  }
}

function clearSearch() {
  searchQuery.value = ''
  searchActive.value = false
  searchResults.value = []
}

function formatTime(card: MemoryCard): string {
  const d = new Date(card.created_at)
  return `${d.toLocaleDateString('zh-CN')} ${d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })}`
}

async function expandCard(card: MemoryCard) {
  error.value = null
  try {
    const result = await cardStore.expandCard(card.card_id)
    await cardStore.loadCards()
    router.push(`/write/${result.diary_id}`)
  } catch (err) {
    error.value = formatApiError(err, '展开卡片失败')
  }
}

async function deleteCard(card: MemoryCard) {
  error.value = null
  try {
    await cardStore.removeCard(card.card_id)
    if (searchActive.value) {
      searchResults.value = searchResults.value.filter((r) => r.card_id !== card.card_id)
    }
  } catch (err) {
    error.value = formatApiError(err, '删除卡片失败')
  }
}
</script>

<template>
  <div class="cards-section">
    <p v-if="error" class="cards-section__error">{{ error }}</p>

    <div class="cards-section__search">
      <div class="cards-section__search-row">
        <PhMagnifyingGlass :size="16" class="cards-section__search-icon" />
        <input
          v-model="searchQuery"
          class="cards-section__search-input"
          :placeholder="copy.cardsSearchPlaceholder"
          @keydown.enter="doSearch"
        />
        <button v-if="searchQuery" class="cards-section__search-clear" @click="clearSearch">
          <PhXCircle :size="14" />
        </button>
      </div>
      <GameButton
        variant="ghost"
        :disabled="!searchQuery.trim() || searchLoading"
        @click="doSearch"
      >
        {{ searchLoading ? copy.cardsSearching : copy.cardsSearch }}
      </GameButton>
    </div>

    <template v-if="searchActive">
      <p v-if="!searchLoading && searchResults.length === 0" class="cards-section__empty">
        {{ copy.cardsSearchEmpty }}
      </p>
      <div
        v-for="card in searchResults"
        :key="card.card_id"
        class="cards-section__item glass-panel"
      >
        <div class="cards-section__item-head">
          <EmotionChips :emotions="card.emotions" :emotion="card.emotion" />
          <CardTypeBadge :card-type="card.card_type" />
        </div>
        <p v-if="card.event_summary" class="cards-section__item-summary font-diary">
          {{ card.event_summary }}
        </p>
        <div v-if="card.tags.length > 0" class="cards-section__item-tags">
          <span v-for="tag in card.tags" :key="tag" class="cards-section__item-tag">
            {{ tag }}
          </span>
        </div>
        <div class="cards-section__item-footer">
          <span class="cards-section__item-time">{{ formatTime(card) }}</span>
          <div class="cards-section__item-actions">
            <button
              v-if="!card.diary_id"
              class="cards-section__action-btn"
              :title="copy.cardsExpandToDiary"
              @click="expandCard(card)"
            >
              <PhArrowSquareOut :size="14" />
            </button>
            <button
              class="cards-section__action-btn cards-section__action-btn--danger"
              :title="copy.cardsDelete"
              @click="deleteCard(card)"
            >
              &times;
            </button>
          </div>
        </div>
      </div>
    </template>

    <template v-else>
      <div v-if="cardStore.cards.length === 0" class="cards-section__empty">
        <p>{{ copy.cardsEmpty }}</p>
        <p class="cards-section__empty-hint">{{ copy.cardsEmptyHint }}</p>
      </div>

      <div
        v-for="card in cardStore.cards"
        :key="card.card_id"
        class="cards-section__item glass-panel"
      >
        <div class="cards-section__item-head">
          <EmotionChips :emotions="card.emotions" :emotion="card.emotion" />
          <CardTypeBadge :card-type="card.card_type" />
        </div>
        <p v-if="card.event_summary" class="cards-section__item-summary font-diary">
          {{ card.event_summary }}
        </p>
        <div v-if="card.tags.length > 0" class="cards-section__item-tags">
          <span v-for="tag in card.tags" :key="tag" class="cards-section__item-tag">
            {{ tag }}
          </span>
        </div>
        <div class="cards-section__item-footer">
          <span class="cards-section__item-time">{{ formatTime(card) }}</span>
          <div class="cards-section__item-actions">
            <button
              v-if="!card.diary_id"
              class="cards-section__action-btn"
              :title="copy.cardsExpandToDiary"
              @click="expandCard(card)"
            >
              <PhArrowSquareOut :size="14" />
            </button>
            <button
              class="cards-section__action-btn cards-section__action-btn--danger"
              :title="copy.cardsDelete"
              @click="deleteCard(card)"
            >
              &times;
            </button>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<style scoped>
.cards-section {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}
.cards-section__error {
  padding: 0.5rem 0.75rem;
  border-radius: 0.5rem;
  background: color-mix(in srgb, var(--color-danger) 12%, transparent);
  color: var(--color-danger);
  font-size: 0.8125rem;
  margin: 0;
}
.cards-section__search {
  display: flex;
  gap: 0.5rem;
  align-items: center;
}
.cards-section__search-row {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--color-border);
  border-radius: 0.625rem;
  background: var(--color-bg-elevated);
}
.cards-section__search-icon {
  color: var(--color-text-secondary);
  flex-shrink: 0;
}
.cards-section__search-input {
  flex: 1;
  border: none;
  background: transparent;
  outline: none;
  font-size: 0.875rem;
  color: var(--color-text-primary);
  font-family: var(--font-ui);
}
.cards-section__search-clear {
  border: none;
  background: transparent;
  color: var(--color-text-secondary);
  cursor: pointer;
  padding: 0;
  display: inline-flex;
}
.cards-section__empty {
  text-align: center;
  padding: 1.5rem 1rem;
  border: 1px dashed var(--color-border);
  border-radius: 0.75rem;
  color: var(--color-text-secondary);
  font-size: 0.875rem;
  margin: 0;
}
.cards-section__empty-hint {
  font-size: 0.75rem;
  margin: 0.375rem 0 0;
  opacity: 0.8;
}
.cards-section__item {
  padding: 0.875rem 1rem;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}
.cards-section__item-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}
.cards-section__item-summary {
  margin: 0;
  font-size: 0.875rem;
  line-height: 1.6;
  color: var(--color-text-primary);
}
.cards-section__item-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 0.375rem;
}
.cards-section__item-tag {
  font-size: 0.6875rem;
  color: var(--color-text-secondary);
  border: 1px solid var(--color-border);
  border-radius: 999px;
  padding: 0.0625rem 0.5rem;
}
.cards-section__item-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}
.cards-section__item-time {
  font-size: 0.6875rem;
  color: var(--color-text-secondary);
}
.cards-section__item-actions {
  display: flex;
  gap: 0.25rem;
}
.cards-section__action-btn {
  border: none;
  background: transparent;
  color: var(--color-text-secondary);
  cursor: pointer;
  padding: 0.25rem;
  border-radius: 0.375rem;
  display: inline-flex;
  font-size: 1rem;
  line-height: 1;
}
.cards-section__action-btn:hover {
  color: var(--color-text-primary);
  background: var(--color-bg-elevated-2, var(--color-bg-elevated));
}
.cards-section__action-btn--danger:hover {
  color: var(--color-danger);
}
</style>
```

（import 区需补 `computed`：`import { computed, ref } from 'vue'`——`displayCards` 当前模板未直接使用可删，保留 `computed` 导入与否以最终代码为准；实现时若无引用则删除该 computed 与 `computed` 导入。）

- [ ] **Step 5: 运行确认通过**

Run: `npx vitest run src/__tests__/CardsSection.spec.ts && npm run type-check`
Expected: PASS。

- [ ] **Step 6: 提交**

```bash
git add src/features/memory/CardsSection.vue src/shared/copy/memory.ts src/__tests__/CardsSection.spec.ts
git commit -m "feat(memory): cards management section with search"
```

### Task 6.2: MemoryScene 集成卡片分区

**Files:**
- Modify: `src/pages/MemoryScene.vue`
- Modify: `src/shared/copy/memory.ts`

- [ ] **Step 1: 替换跳转链接为内嵌分区**

`src/pages/MemoryScene.vue`：

1. script 增加导入，删除 `goToCards`：

```ts
import CardsSection from '@/features/memory/CardsSection.vue'
```

2. `goToDiary` 从 `review-detail` 命名路由改为直跳写作页：

```ts
function goToDiary(diaryId: string) {
  router.push(`/write/${diaryId}`)
}
```

3. script 中删除 `goToCards` 函数与 `PhArrowRight`、`PhNotePencil` 图标导入（确认无其他使用后）。

4. template 的「Cards management entry」区段（`memory-cards-link` GlassPanel 整块）替换为：

```vue
    <!-- ── Cards management ─────────────────────────────────────── -->
    <section class="memory-scene__section">
      <h2 class="memory-scene__section-title">
        <PhCards :size="16" weight="duotone" />
        {{ copy.cardsTitle }}
      </h2>
      <p class="memory-scene__section-desc">{{ copy.cardsDesc }}</p>
      <CardsSection />
    </section>
```

5. `<style scoped>` 删除 `.memory-cards-link` 相关三段样式。

- [ ] **Step 2: 文案瘦身**

`src/shared/copy/memory.ts` 删除 `goToCards` 键（无引用方）。

- [ ] **Step 3: 类型检查 + 存量测试**

Run: `npm run type-check && npm test`
Expected: 通过。

- [ ] **Step 4: 提交**

```bash
git add src/pages/MemoryScene.vue src/shared/copy/memory.ts
git commit -m "feat(memory): embed cards section, drop review-page navigation"
```

### Task 6.3: 删除 ReviewScene 与 review 路由

**Files:**
- Delete: `src/pages/ReviewScene.vue`、`src/features/review/CalendarView.vue`、`src/features/review/TimelineView.vue`
- Modify: `src/router/index.ts:95-104`
- Modify: `src/__tests__/redirects.spec.ts`

- [ ] **Step 1: 路由重定向**

`src/router/index.ts` 将 `/review` 与 `/review/:diaryId` 两条路由替换为：

```ts
    {
      path: '/review',
      redirect: { path: '/memory' },
    },
    {
      path: '/review/:diaryId',
      redirect: (to) => ({ path: `/write/${to.params.diaryId}` }),
    },
```

- [ ] **Step 2: 删除文件**

删除 `src/pages/ReviewScene.vue`、`src/features/review/CalendarView.vue`、`src/features/review/TimelineView.vue`（`src/features/review/` 目录随之清空删除）。功能去向：月历→MonthView（PR-4）、时间线→时间轴日/周/月视图（PR-2/4）、卡片→CardsSection（本 PR）、详情面板→DetailPanel（PR-4）。

运行确认无残留引用：

```powershell
rg -n "ReviewScene|CalendarView|TimelineView|review-detail|name: 'review'" src/
```

Expected: 无匹配（`AnalysisScene` 的 `/analysis/:diaryId` 路由名是 `analysis`，不受影响）。

- [ ] **Step 3: redirect 测试补充**

`src/__tests__/redirects.spec.ts` 的 describe 内追加：

```ts
  it('redirects /review to the memory scene', async () => {
    const router = buildRouter()
    await router.push('/review')
    expect(router.currentRoute.value.name).toBe('memory')
  })

  it('redirects /weekly to the timeline week view', async () => {
    const router = buildRouter()
    await router.push('/weekly')
    expect(router.currentRoute.value.path).toBe('/')
    expect(router.currentRoute.value.query.view).toBe('week')
  })
```

- [ ] **Step 4: 全量验证**

Run: `npm run type-check && npm test && npm run lint`
Expected: 全部通过。

- [ ] **Step 5: 提交**

```bash
git add -A
git commit -m "refactor(review): remove review scene, redirect /review to memory"
```

### Task 6.4: PR-6 收尾 + 全局减法纪律验收

- [ ] **Step 1: 手动冒烟**

1. `/#/memory`：概览、人格画像、心情曲线、情节记忆、**记忆卡片**（搜索 + 列表 + 展开/删除）五个分区完整；卡片搜索回车出结果、清空恢复全量。
2. `/#/review` → 自动落到 `/#/memory`；`/#/review/123` → `/#/write/123`。
3. `/#/weekly` → `/#/?view=week`。
4. 情节记忆的「查看日记」→ `/write/:id`（不再经 review-detail）。

- [ ] **Step 2: 减法纪律清单验收（设计文档 §11 全局验收标准）**

逐项核对并勾选：

- [ ] 导航无红点 / badge
- [ ] 无逾期红色警告（过期任务中性灰）
- [ ] 无"你已 N 天未写日记"类提醒
- [ ] 写作面（`/write` 路径）零任务元素
- [ ] 日视图无任务时折叠行隐藏
- [ ] 周信复盘为观察框架（事实陈述 + 日记归因），无完成率警告措辞

- [ ] **Step 3: 推送并开 PR**

```bash
git push -u origin feature/merge-diary-weekly-review-pr6
```

PR 描述模板：

```markdown
### 标题
feat(memory): 吸收记忆卡片视图，删除回顾页（合并重构收官）

### 功能描述
- MemoryScene 新增「记忆卡片」分区：搜索（searchCards）+ 卡片列表 + 展开为日记 + 删除
- 删除 ReviewScene / CalendarView / TimelineView，四类功能各有去处（月历→MonthView、时间线→时间轴、卡片→CardsSection、面板→DetailPanel）
- `/review` → `/memory`，`/review/:id` → `/write/:id`，`/weekly` → `/?view=week`

### 实现思路
- CardsSection 自持搜索态（结果态/全量态二选一），删除后同步从结果中移除
- 全部旧路由保留 redirect，收藏夹/外链不 404

### 测试方式
- npx vitest run src/__tests__/CardsSection.spec.ts src/__tests__/redirects.spec.ts
- 减法纪律清单验收见 Task 6.4 Step 2
```
