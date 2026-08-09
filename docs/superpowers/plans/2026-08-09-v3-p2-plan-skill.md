# V3 P2: 协议块基础设施 + 计划 Skill 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把夜记场景二从纯聊天升级为生活助手——Agent 通过多轮对话帮助用户规划生活，生成结构化计划提案，用户采纳后落库。五层垂直切片单 P2 交付。

**Architecture:** 数据层（Plan/Task 表 + REST CRUD）+ 协议块 SSE（PROTOCOL_BLOCK 事件 + 三种 block_type）+ Agent 层（ChatIntent 6→8 + PlannerAgent 多轮澄清 + 只读工具）+ 前端（PlanScene 常驻 + 会话内协议块瞬时渲染 + segments 模型）。零写权限：Agent 只读 + 提案，所有写入通过用户采纳 REST 完成。

**Tech Stack:** Python 3.11 / FastAPI / SQLAlchemy / Alembic / asyncio / Vue 3 / TypeScript / SSE

**Spec:** `docs/superpowers/specs/2026-08-09-v3-p2-plan-skill.md`

---

## 文件结构

### 新建文件（后端）
| 文件 | 职责 |
|------|------|
| `server/app/infrastructure/models/plan.py` | PlanRow + TaskRow ORM |
| `server/alembic/versions/003_plan_task_domain.py` | 建表迁移 |
| `server/app/api/v1/plan.py` | 计划/任务 REST 端点 |
| `server/app/api/schemas.py`（扩展） | Plan/Task 的 Pydantic schema |
| `server/app/services/plan_service.py` | 计划/任务业务逻辑 |
| `server/app/domain/agents/planner_agent.py` | PlannerAgent——多轮澄清 + plan_proposal 生成 |
| `server/app/domain/agents/plan_completeness.py` | 信息完整度判断（what/how/when） |
| `server/tests/unit/infrastructure/test_plan_models.py` | ORM 测试 |
| `server/tests/unit/api/test_plan_routes.py` | REST 测试 |
| `server/tests/unit/domain/agents/test_planner_agent.py` | PlannerAgent 测试 |
| `server/tests/e2e/test_plan_skill_flow.py` | e2e 多轮规划流测试 |

### 新建文件（前端）
| 文件 | 职责 |
|------|------|
| `src/features/plan/PlanScene.vue` | 计划管理页 |
| `src/features/plan/PlanCard.vue` | 单个计划卡片 |
| `src/features/plan/TaskItem.vue` | 单个任务条目 |
| `src/features/chat/PlanProposalCard.vue` | 会话内 plan_proposal 渲染 |
| `src/features/chat/TaskProposalCard.vue` | 会话内 task_proposal 渲染 |
| `src/features/chat/ClarificationCard.vue` | 会话内 clarification_request 渲染 |
| `src/shared/api/plan.ts` | 计划/任务 API 调用 |
| `src/stores/plan.ts` | 计划 store |

### 修改文件
| 文件 | 改动 |
|------|------|
| `server/app/domain/agents/types.py` | ChatIntent 新增 PLAN_EXPLORATION / TASK_COMMAND |
| `server/app/domain/agents/chat_intent_classifier.py` | 新增两类意图关键词 + 路由 |
| `server/app/services/ai/tool_factory.py` | 新增 list_todos / get_plan_progress 只读工具 |
| `server/app/services/ai/conversation_loop.py` | Stage 4 意图分支：plan_exploration → PlannerAgent |
| `server/app/shared/streaming_events.py` | 新增 publish_protocol_block |
| `server/app/infrastructure/models/__init__.py` | 导出 PlanRow / TaskRow |
| `server/app/api/v1/__init__.py` 或 router 注册 | 挂载 plan router |
| `server/app/main.py` | 注册 plan router |
| `src/shared/composables/useStreamingReply.ts` | segments 渲染模型 |
| `src/features/chat/ChatMessage.vue` | 按段渲染（文本 + 协议块） |
| `src/router/index.ts` | 新增 /plan 路由 |
| `src/views/` 或主导航 | PlanScene 入口 |

---

## 第一周：数据层 + REST + 协议块基础设施

## Task 1: Plan/Task ORM 模型 + Alembic 迁移

**Files:**
- Create: `server/app/infrastructure/models/plan.py`
- Modify: `server/app/infrastructure/models/__init__.py`
- Create: `server/alembic/versions/003_plan_task_domain.py`
- Create: `server/tests/unit/infrastructure/test_plan_models.py`

- [ ] **Step 1: 阅读现有 ORM 模式**

阅读 `server/app/infrastructure/models/pipeline_trace.py` 或 `conversation.py` 完整文件，理解：
- Base 的导入路径（通常 `from app.infrastructure.database import Base`）
- Mapped / mapped_column 的用法
- 表名约定、主键约定（uuid hex 还是自增 int）
- user_id 外键的约定（`ForeignKey("users.id")`）
- `__init__.py` 的 re-export 模式

- [ ] **Step 2: 编写 ORM 失败测试**

创建 `server/tests/unit/infrastructure/test_plan_models.py`：

```python
"""Unit tests for Plan and Task ORM models."""

from datetime import date, datetime

import pytest

from app.infrastructure.database import Base, get_engine
from app.infrastructure.models.plan import PlanRow, TaskRow
from sqlalchemy.orm import Session


@pytest.fixture
def db_session():
    """内存 SQLite 数据库用于隔离测试。"""
    engine = get_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)


def test_plan_row_basic_fields(db_session):
    """PlanRow 应能持久化基本字段。"""
    plan = PlanRow(
        id="plan-001",
        user_id="user-1",
        title="晚间放松例程",
        motivation="改善睡眠",
        source_refs_json='[{"type":"diary","id":1}]',
        status="active",
        source="agent",
        created_from_conversation_id="conv-1",
    )
    db_session.add(plan)
    db_session.commit()

    fetched = db_session.query(PlanRow).filter_by(id="plan-001").one()
    assert fetched.title == "晚间放松例程"
    assert fetched.source == "agent"
    assert fetched.motivation == "改善睡眠"


def test_task_row_belongs_to_plan(db_session):
    """TaskRow 通过 plan_id 归属 PlanRow。"""
    plan = PlanRow(id="plan-1", user_id="user-1", title="测试计划")
    db_session.add(plan)
    db_session.commit()

    task = TaskRow(
        id="task-1",
        plan_id="plan-1",
        user_id="user-1",
        title="睡前不看手机",
        status="pending",
    )
    db_session.add(task)
    db_session.commit()

    fetched = db_session.query(TaskRow).filter_by(id="task-1").one()
    assert fetched.plan_id == "plan-1"
    assert fetched.status == "pending"


def test_task_row_can_be_standalone(db_session):
    """TaskRow 的 plan_id 可为空（独立 task）。"""
    task = TaskRow(
        id="task-standalone",
        plan_id=None,
        user_id="user-1",
        title="买菜",
        due_date=date(2026, 8, 10),
    )
    db_session.add(task)
    db_session.commit()

    fetched = db_session.query(TaskRow).filter_by(id="task-standalone").one()
    assert fetched.plan_id is None
    assert fetched.due_date == date(2026, 8, 10)


def test_delete_plan_cascades_to_tasks(db_session):
    """删除 Plan 应级联删除其下所有 Tasks。"""
    plan = PlanRow(id="plan-cascade", user_id="user-1", title="测试")
    db_session.add(plan)
    db_session.commit()

    for i in range(3):
        db_session.add(TaskRow(
            id=f"task-cascade-{i}",
            plan_id="plan-cascade",
            user_id="user-1",
            title=f"task {i}",
        ))
    db_session.commit()

    assert db_session.query(TaskRow).filter_by(plan_id="plan-cascade").count() == 3

    db_session.delete(plan)
    db_session.commit()

    assert db_session.query(TaskRow).filter_by(plan_id="plan-cascade").count() == 0


def test_user_isolation(db_session):
    """不同 user_id 的数据应隔离。"""
    db_session.add(PlanRow(id="plan-a", user_id="user-1", title="用户1的计划"))
    db_session.add(PlanRow(id="plan-b", user_id="user-2", title="用户2的计划"))
    db_session.commit()

    user1_plans = db_session.query(PlanRow).filter_by(user_id="user-1").all()
    assert len(user1_plans) == 1
    assert user1_plans[0].id == "plan-a"
```

注意：如果项目用 `conftest.py` 里的 `db_session` fixture，直接用现有的。如果用 `get_engine` 的方式不对，调整导入方式。

- [ ] **Step 3: 运行测试确认失败**

```bash
cd d:\work\night_diary_v2\server
.venv\Scripts\python.exe -m pytest tests/unit/infrastructure/test_plan_models.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.infrastructure.models.plan'`

- [ ] **Step 4: 创建 plan.py ORM 模型**

创建 `server/app/infrastructure/models/plan.py`：

```python
"""ORM models for the plan/task domain (V3 P2).

A ``Plan`` is a named container of related tasks with a motivation and
source references (diary/memory citations). A ``Task`` is a single
actionable to-do, optionally belonging to a Plan.

Both tables carry ``source`` (manual vs agent) and
``created_from_conversation_id`` so we can audit which plans/tasks
originated from an Agent proposal vs direct user creation.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import Date, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.infrastructure.database import Base


class PlanRow(Base):
    """A plan: a named container of tasks with motivation and source refs."""

    __tablename__ = "plans"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    motivation: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_refs_json: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(20), default="active")  # active/archived/completed
    source: Mapped[str] = mapped_column(String(20), default="manual")  # manual/agent
    created_from_conversation_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    tasks: Mapped[list[TaskRow]] = relationship(
        back_populates="plan",
        cascade="all, delete-orphan",
    )


class TaskRow(Base):
    """A single to-do item, optionally belonging to a Plan."""

    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    plan_id: Mapped[str | None] = mapped_column(
        String(32), ForeignKey("plans.id", ondelete="CASCADE"), nullable=True, index=True
    )
    user_id: Mapped[str] = mapped_column(String(64), ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending/done/skipped
    source: Mapped[str] = mapped_column(String(20), default="manual")
    created_from_conversation_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    plan: Mapped[PlanRow | None] = relationship(back_populates="tasks")
```

注意：`Base` 的导入路径可能不同（检查 `database.py` 实际导出）。如果项目用 `DeclarativeBase`，参考现有模型的导入。

- [ ] **Step 5: 在 __init__.py 导出新模型**

修改 `server/app/infrastructure/models/__init__.py`，在末尾添加：

```python
from app.infrastructure.models.plan import PlanRow, TaskRow

__all__ = ["PipelineTraceRow", "PlanRow", "TaskRow"]
```

- [ ] **Step 6: 运行测试确认通过**

```bash
cd d:\work\night_diary_v2\server
.venv\Scripts\python.exe -m pytest tests/unit/infrastructure/test_plan_models.py -v
```

Expected: 5 个测试全部 PASS

- [ ] **Step 7: 创建 Alembic 迁移**

创建 `server/alembic/versions/003_plan_task_domain.py`。先阅读 `002_pipeline_traces_and_trace_id.py` 完整文件理解迁移的 idempotent 模式（项目用 `_table_exists` 检查避免重复建表）。

```python
"""Create plans and tasks tables for the plan/task domain (V3 P2).

Revision ID: 003_plan_task
Revises: 002_pipeline_traces
Create Date: 2026-08-09

Idempotent: checks whether each table already exists before creating.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect

revision = "003_plan_task"
down_revision = "002_pipeline_traces"
branch_labels = None
depends_on = None


def _table_exists(bind, table_name: str) -> bool:
    return table_name in inspect(bind).get_table_names()


def upgrade() -> None:
    bind = op.get_bind()

    if not _table_exists(bind, "plans"):
        op.create_table(
            "plans",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column("user_id", sa.String(64), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("motivation", sa.Text, nullable=True),
            sa.Column("source_refs_json", sa.Text, nullable=False, server_default="[]"),
            sa.Column("status", sa.String(20), nullable=False, server_default="active"),
            sa.Column("source", sa.String(20), nullable=False, server_default="manual"),
            sa.Column("created_from_conversation_id", sa.String(32), nullable=True),
            sa.Column("created_at", sa.DateTime, nullable=False),
            sa.Column("updated_at", sa.DateTime, nullable=False),
        )
        op.create_index("ix_plans_user_id", "plans", ["user_id"])

    if not _table_exists(bind, "tasks"):
        op.create_table(
            "tasks",
            sa.Column("id", sa.String(32), primary_key=True),
            sa.Column(
                "plan_id",
                sa.String(32),
                sa.ForeignKey("plans.id", ondelete="CASCADE"),
                nullable=True,
            ),
            sa.Column("user_id", sa.String(64), sa.ForeignKey("users.id"), nullable=False),
            sa.Column("title", sa.String(200), nullable=False),
            sa.Column("note", sa.Text, nullable=True),
            sa.Column("due_date", sa.Date, nullable=True),
            sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
            sa.Column("source", sa.String(20), nullable=False, server_default="manual"),
            sa.Column("created_from_conversation_id", sa.String(32), nullable=True),
            sa.Column("completed_at", sa.DateTime, nullable=True),
            sa.Column("created_at", sa.DateTime, nullable=False),
            sa.Column("updated_at", sa.DateTime, nullable=False),
        )
        op.create_index("ix_tasks_plan_id", "tasks", ["plan_id"])
        op.create_index("ix_tasks_user_id", "tasks", ["user_id"])


def downgrade() -> None:
    op.drop_table("tasks")
    op.drop_table("plans")
```

- [ ] **Step 8: 测试迁移可执行**

```bash
cd d:\work\night_diary_v2\server
.venv\Scripts\python.exe -m alembic upgrade head
.venv\Scripts\python.exe -m alembic downgrade -1
.venv\Scripts\python.exe -m alembic upgrade head
```

Expected: 三条命令都成功（up → down → up 验证幂等）

- [ ] **Step 9: lint 检查**

```bash
cd d:\work\night_diary_v2\server
.venv\Scripts\python.exe -m ruff check app/infrastructure/models/plan.py alembic/versions/003_plan_task_domain.py tests/unit/infrastructure/test_plan_models.py
.venv\Scripts\python.exe -m mypy app/infrastructure/models/plan.py
```

- [ ] **Step 10: 提交**

```bash
cd d:\work\night_diary_v2
& 'C:\Program Files\Git\cmd\git.exe' add server/app/infrastructure/models/plan.py server/app/infrastructure/models/__init__.py server/alembic/versions/003_plan_task_domain.py server/tests/unit/infrastructure/test_plan_models.py
& 'C:\Program Files\Git\cmd\git.exe' commit -m "feat(plan): add Plan/Task ORM models and Alembic migration

PlanRow: container with title/motivation/source_refs/status.
TaskRow: single to-do, optional plan_id, due_date, status.
Cascade delete: removing a plan removes its tasks.
source field (manual/agent) + created_from_conversation_id for audit."
```

---

## Task 2: Plan/Task 业务 Service 层

**Files:**
- Create: `server/app/services/plan_service.py`
- Create: `server/tests/unit/services/test_plan_service.py`

- [ ] **Step 1: 阅读现有 service 模式**

阅读 `server/app/services/diary_service.py` 前 80 行，理解：
- service 函数的签名（`db: Session, user_id: str, ...`）
- 异常抛出模式（用 `app.shared.errors` 里的类）
- uuid 生成方式（`uuid.uuid4().hex`）

- [ ] **Step 2: 编写 service 失败测试**

创建 `server/tests/unit/services/test_plan_service.py`：

```python
"""Unit tests for plan_service."""

import pytest
from sqlalchemy.orm import Session

from app.infrastructure.database import Base, get_engine
from app.infrastructure.models import PlanRow, TaskRow
from app.services import plan_service


@pytest.fixture
def db():
    engine = get_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)


def test_create_plan(db):
    plan = plan_service.create_plan(
        db, user_id="user-1", title="测试计划", motivation="动机",
        source_refs=[{"type": "diary", "id": 1}],
        source="agent", created_from_conversation_id="conv-1",
    )
    assert plan.id
    assert plan.title == "测试计划"
    assert plan.source == "agent"
    assert plan.user_id == "user-1"


def test_list_plans_filters_by_user(db):
    plan_service.create_plan(db, user_id="user-1", title="A")
    plan_service.create_plan(db, user_id="user-2", title="B")
    plans = plan_service.list_plans(db, user_id="user-1")
    assert len(plans) == 1
    assert plans[0].title == "A"


def test_get_plan_with_tasks(db):
    plan = plan_service.create_plan(db, user_id="user-1", title="带任务的计划")
    plan_service.create_task(db, user_id="user-1", plan_id=plan.id, title="task1")
    plan_service.create_task(db, user_id="user-1", plan_id=plan.id, title="task2")

    fetched = plan_service.get_plan(db, plan_id=plan.id, user_id="user-1")
    assert len(fetched.tasks) == 2


def test_create_task_standalone(db):
    task = plan_service.create_task(
        db, user_id="user-1", plan_id=None, title="独立任务",
        due_date="2026-08-15",
    )
    assert task.plan_id is None
    assert task.due_date is not None


def test_get_today_tasks(db):
    from datetime import date
    today = date.today()
    plan_service.create_task(db, user_id="user-1", title="今日到期", due_date=today.isoformat())
    plan_service.create_task(db, user_id="user-1", title="明日", due_date=(date.today().replace(day=today.day + 1)).isoformat())
    plan_service.create_task(db, user_id="user-1", title="无截止日的 pending")

    today_tasks = plan_service.get_today_tasks(db, user_id="user-1")
    titles = [t.title for t in today_tasks]
    assert "今日到期" in titles
    # 无截止日的 pending task 也算"今日待办"（需要在今天处理）
    assert "无截止日的 pending" in titles
    assert "明日" not in titles


def test_complete_task(db):
    task = plan_service.create_task(db, user_id="user-1", title="待完成")
    plan_service.update_task_status(db, task_id=task.id, user_id="user-1", status="done")
    fetched = plan_service.get_task(db, task_id=task.id, user_id="user-1")
    assert fetched.status == "done"
    assert fetched.completed_at is not None


def test_delete_plan_cascades(db):
    plan = plan_service.create_plan(db, user_id="user-1", title="要删的")
    plan_service.create_task(db, user_id="user-1", plan_id=plan.id, title="t1")
    plan_service.delete_plan(db, plan_id=plan.id, user_id="user-1")
    # task 应该也没了
    tasks = plan_service.list_tasks(db, user_id="user-1", plan_id=plan.id)
    assert len(tasks) == 0
```

- [ ] **Step 3: 运行测试确认失败**

```bash
cd d:\work\night_diary_v2\server
.venv\Scripts\python.exe -m pytest tests/unit/services/test_plan_service.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.plan_service'`

- [ ] **Step 4: 创建 plan_service.py**

创建 `server/app/services/plan_service.py`：

```python
"""Business logic for plans and tasks (V3 P2).

All functions enforce user_id scoping for multi-tenant isolation.
Caller (API layer) is responsible for authentication; service layer
trusts the user_id passed in.
"""

from __future__ import annotations

import json
import logging
import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.infrastructure.models import PlanRow, TaskRow
from app.shared.errors import NotFoundError

logger = logging.getLogger(__name__)


def _new_id() -> str:
    return uuid.uuid4().hex


# ── Plan operations ───────────────────────────────────────────────────


def create_plan(
    db: Session,
    *,
    user_id: str,
    title: str,
    motivation: str | None = None,
    source_refs: list[dict[str, Any]] | None = None,
    source: str = "manual",
    created_from_conversation_id: str | None = None,
) -> PlanRow:
    row = PlanRow(
        id=_new_id(),
        user_id=user_id,
        title=title,
        motivation=motivation,
        source_refs_json=json.dumps(source_refs or [], ensure_ascii=False),
        status="active",
        source=source,
        created_from_conversation_id=created_from_conversation_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    logger.info("Created plan id=%s user=%s source=%s", row.id, user_id, source)
    return row


def list_plans(
    db: Session, *, user_id: str, status: str | None = None
) -> list[PlanRow]:
    stmt = select(PlanRow).where(PlanRow.user_id == user_id)
    if status:
        stmt = stmt.where(PlanRow.status == status)
    stmt = stmt.order_by(PlanRow.created_at.desc())
    return list(db.scalars(stmt))


def get_plan(db: Session, *, plan_id: str, user_id: str) -> PlanRow:
    row = db.get(PlanRow, plan_id)
    if row is None or row.user_id != user_id:
        raise NotFoundError(resource="plan", resource_id=plan_id)
    return row


def update_plan(
    db: Session, *, plan_id: str, user_id: str, **fields: Any
) -> PlanRow:
    row = get_plan(db, plan_id=plan_id, user_id=user_id)
    for key, value in fields.items():
        if hasattr(row, key) and value is not None:
            setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return row


def delete_plan(db: Session, *, plan_id: str, user_id: str) -> None:
    row = get_plan(db, plan_id=plan_id, user_id=user_id)
    db.delete(row)
    db.commit()


# ── Task operations ───────────────────────────────────────────────────


def create_task(
    db: Session,
    *,
    user_id: str,
    title: str,
    plan_id: str | None = None,
    note: str | None = None,
    due_date: str | None = None,
    source: str = "manual",
    created_from_conversation_id: str | None = None,
) -> TaskRow:
    parsed_due = date.fromisoformat(due_date) if due_date else None
    row = TaskRow(
        id=_new_id(),
        plan_id=plan_id,
        user_id=user_id,
        title=title,
        note=note,
        due_date=parsed_due,
        status="pending",
        source=source,
        created_from_conversation_id=created_from_conversation_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_tasks(
    db: Session,
    *,
    user_id: str,
    plan_id: str | None = None,
    status: str | None = None,
) -> list[TaskRow]:
    stmt = select(TaskRow).where(TaskRow.user_id == user_id)
    if plan_id:
        stmt = stmt.where(TaskRow.plan_id == plan_id)
    if status:
        stmt = stmt.where(TaskRow.status == status)
    stmt = stmt.order_by(TaskRow.created_at.desc())
    return list(db.scalars(stmt))


def get_task(db: Session, *, task_id: str, user_id: str) -> TaskRow:
    row = db.get(TaskRow, task_id)
    if row is None or row.user_id != user_id:
        raise NotFoundError(resource="task", resource_id=task_id)
    return row


def update_task_status(
    db: Session, *, task_id: str, user_id: str, status: str
) -> TaskRow:
    row = get_task(db, task_id=task_id, user_id=user_id)
    row.status = status
    if status == "done":
        row.completed_at = datetime.utcnow()
    else:
        row.completed_at = None
    db.commit()
    db.refresh(row)
    return row


def update_task(
    db: Session, *, task_id: str, user_id: str, **fields: Any
) -> TaskRow:
    row = get_task(db, task_id=task_id, user_id=user_id)
    for key, value in fields.items():
        if hasattr(row, key) and value is not None:
            setattr(row, key, value)
    db.commit()
    db.refresh(row)
    return row


def delete_task(db: Session, *, task_id: str, user_id: str) -> None:
    row = get_task(db, task_id=task_id, user_id=user_id)
    db.delete(row)
    db.commit()


def get_today_tasks(db: Session, *, user_id: str) -> list[TaskRow]:
    """Today's actionable tasks: due today OR pending without due_date or plan.

    Excludes done/skipped.
    """
    today = date.today()
    stmt = (
        select(TaskRow)
        .where(TaskRow.user_id == user_id)
        .where(TaskRow.status == "pending")
        .where(
            (TaskRow.due_date == today)
            | (TaskRow.due_date.is_(None))
        )
        .order_by(TaskRow.due_date.asc().nullslast(), TaskRow.created_at.asc())
    )
    return list(db.scalars(stmt))
```

- [ ] **Step 5: 运行测试确认通过**

```bash
cd d:\work\night_diary_v2\server
.venv\Scripts\python.exe -m pytest tests/unit/services/test_plan_service.py -v
```

Expected: 8 个测试全部 PASS

- [ ] **Step 6: lint 检查**

```bash
cd d:\work\night_diary_v2\server
.venv\Scripts\python.exe -m ruff check app/services/plan_service.py tests/unit/services/test_plan_service.py
.venv\Scripts\python.exe -m mypy app/services/plan_service.py
```

- [ ] **Step 7: 提交**

```bash
cd d:\work\night_diary_v2
& 'C:\Program Files\Git\cmd\git.exe' add server/app/services/plan_service.py server/tests/unit/services/test_plan_service.py
& 'C:\Program Files\Git\cmd\git.exe' commit -m "feat(plan): add plan_service with CRUD and today-tasks aggregation

All operations enforce user_id scoping. get_today_tasks returns tasks
due today OR pending without due_date (actionable today)."
```

---

## Task 3: Plan/Task REST API

**Files:**
- Create: `server/app/api/v1/plan.py`
- Modify: `server/app/api/schemas.py`（扩展）
- Modify: `server/app/main.py` 或 `server/app/api/v1/__init__.py`（注册 router）
- Create: `server/tests/unit/api/test_plan_routes.py`

- [ ] **Step 1: 阅读现有 API 模式**

阅读 `server/app/api/v1/diary.py` 完整文件，理解 router 定义、认证依赖、schema 模式、错误处理。同时阅读 `server/app/api/schemas.py` 末尾理解 Pydantic schema 定义方式。阅读 `server/app/main.py` 找到 router 注册的地方（通常 `app.include_router(...)`）。

- [ ] **Step 2: 在 schemas.py 添加 Plan/Task schema**

在 `server/app/api/schemas.py` 末尾追加：

```python
# ── Plan / Task (V3 P2) ──────────────────────────────────────────────


class SourceRef(BaseModel):
    """A citation backing a plan's motivation (diary/memory/episodic)."""
    type: str = Field(description="diary | episodic | memory")
    id: str | int
    date: str | None = None
    snippet: str | None = None


class TaskCreateRequest(BaseModel):
    title: str = Field(max_length=200)
    note: str | None = None
    due_date: str | None = Field(default=None, description="ISO date YYYY-MM-DD")
    plan_id: str | None = None
    source: str = Field(default="manual", pattern="^(manual|agent)$")
    created_from_conversation_id: str | None = None


class TaskResponse(BaseModel):
    id: str
    plan_id: str | None = None
    title: str
    note: str | None = None
    due_date: str | None = None
    status: str
    source: str
    completed_at: str | None = None
    created_at: str


class TaskUpdateRequest(BaseModel):
    title: str | None = None
    note: str | None = None
    due_date: str | None = None
    status: str | None = Field(default=None, pattern="^(pending|done|skipped)$")


class PlanCreateRequest(BaseModel):
    title: str = Field(max_length=200)
    motivation: str | None = None
    source_refs: list[SourceRef] = Field(default_factory=list)
    tasks: list[TaskCreateRequest] = Field(default_factory=list)
    source: str = Field(default="manual", pattern="^(manual|agent)$")
    created_from_conversation_id: str | None = None


class PlanResponse(BaseModel):
    id: str
    title: str
    motivation: str | None = None
    source_refs: list[SourceRef] = Field(default_factory=list)
    status: str
    source: str
    tasks: list[TaskResponse] = Field(default_factory=list)
    created_at: str


class PlanUpdateRequest(BaseModel):
    title: str | None = None
    motivation: str | None = None
    status: str | None = Field(default=None, pattern="^(active|archived|completed)$")
```

- [ ] **Step 3: 创建 plan.py API**

创建 `server/app/api/v1/plan.py`：

```python
"""Plan and Task REST API routes (V3 P2).

All routes require authentication and enforce user_id scoping via the
service layer. Plans and tasks created here may have source="agent" when
originating from an accepted Agent proposal (created_from_conversation_id
links back to the originating conversation for audit).
"""

from __future__ import annotations

from fastapi import APIRouter, Query, status

from app.api.deps import CurrentUserDep, DbDep
from app.api.schemas import (
    PlanCreateRequest,
    PlanResponse,
    PlanUpdateRequest,
    TaskCreateRequest,
    TaskResponse,
    TaskUpdateRequest,
)
from app.services import plan_service

router = APIRouter(prefix="/plans", tags=["plan"])


def _task_to_response(row) -> TaskResponse:
    return TaskResponse(
        id=row.id,
        plan_id=row.plan_id,
        title=row.title,
        note=row.note,
        due_date=row.due_date.isoformat() if row.due_date else None,
        status=row.status,
        source=row.source,
        completed_at=row.completed_at.isoformat() if row.completed_at else None,
        created_at=row.created_at.isoformat() if row.created_at else "",
    )


def _plan_to_response(row, tasks=None) -> PlanResponse:
    return PlanResponse(
        id=row.id,
        title=row.title,
        motivation=row.motivation,
        source_refs=__import__("json").loads(row.source_refs_json or "[]"),
        status=row.status,
        source=row.source,
        tasks=[_task_to_response(t) for t in (tasks or row.tasks)],
        created_at=row.created_at.isoformat() if row.created_at else "",
    )


# ── Plan CRUD ─────────────────────────────────────────────────────────


@router.post("", response_model=PlanResponse, status_code=status.HTTP_201_CREATED)
def create_plan(body: PlanCreateRequest, db: DbDep, user: CurrentUserDep) -> PlanResponse:
    """Create a plan with optional embedded tasks (atomic)."""
    import json
    plan = plan_service.create_plan(
        db,
        user_id=str(user.id),
        title=body.title,
        motivation=body.motivation,
        source_refs=[r.model_dump() for r in body.source_refs],
        source=body.source,
        created_from_conversation_id=body.created_from_conversation_id,
    )
    # Create embedded tasks atomically
    created_tasks = []
    for task_body in body.tasks:
        task = plan_service.create_task(
            db,
            user_id=str(user.id),
            plan_id=plan.id,
            title=task_body.title,
            note=task_body.note,
            due_date=task_body.due_date,
            source=task_body.source,
            created_from_conversation_id=task_body.created_from_conversation_id,
        )
        created_tasks.append(task)
    return _plan_to_response(plan, created_tasks)


@router.get("", response_model=list[PlanResponse])
def list_plans(
    db: DbDep,
    user: CurrentUserDep,
    plan_status: str | None = Query(default=None, alias="status"),
) -> list[PlanResponse]:
    plans = plan_service.list_plans(db, user_id=str(user.id), status=plan_status)
    return [_plan_to_response(p) for p in plans]


@router.get("/{plan_id}", response_model=PlanResponse)
def get_plan(plan_id: str, db: DbDep, user: CurrentUserDep) -> PlanResponse:
    plan = plan_service.get_plan(db, plan_id=plan_id, user_id=str(user.id))
    return _plan_to_response(plan)


@router.patch("/{plan_id}", response_model=PlanResponse)
def update_plan(
    plan_id: str, body: PlanUpdateRequest, db: DbDep, user: CurrentUserDep
) -> PlanResponse:
    plan = plan_service.update_plan(
        db, plan_id=plan_id, user_id=str(user.id), **body.model_dump(exclude_unset=True)
    )
    return _plan_to_response(plan)


@router.delete("/{plan_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_plan(plan_id: str, db: DbDep, user: CurrentUserDep) -> None:
    plan_service.delete_plan(db, plan_id=plan_id, user_id=str(user.id))


# ── Task routes (nested under /plans for task-in-plan, but also standalone) ──
# For standalone tasks, we mount a separate /tasks router below.


tasks_router = APIRouter(prefix="/tasks", tags=["task"])


@tasks_router.post("", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
def create_task(body: TaskCreateRequest, db: DbDep, user: CurrentUserDep) -> TaskResponse:
    task = plan_service.create_task(
        db,
        user_id=str(user.id),
        plan_id=body.plan_id,
        title=body.title,
        note=body.note,
        due_date=body.due_date,
        source=body.source,
        created_from_conversation_id=body.created_from_conversation_id,
    )
    return _task_to_response(task)


@tasks_router.get("", response_model=list[TaskResponse])
def list_tasks(
    db: DbDep,
    user: CurrentUserDep,
    plan_id: str | None = Query(default=None),
    task_status: str | None = Query(default=None, alias="status"),
) -> list[TaskResponse]:
    tasks = plan_service.list_tasks(
        db, user_id=str(user.id), plan_id=plan_id, status=task_status
    )
    return [_task_to_response(t) for t in tasks]


@tasks_router.get("/today", response_model=list[TaskResponse])
def get_today_tasks(db: DbDep, user: CurrentUserDep) -> list[TaskResponse]:
    """Today's actionable tasks: due today OR pending without due_date."""
    tasks = plan_service.get_today_tasks(db, user_id=str(user.id))
    return [_task_to_response(t) for t in tasks]


@tasks_router.patch("/{task_id}", response_model=TaskResponse)
def update_task(
    task_id: str, body: TaskUpdateRequest, db: DbDep, user: CurrentUserDep
) -> TaskResponse:
    fields = body.model_dump(exclude_unset=True)
    if "status" in fields:
        task = plan_service.update_task_status(
            db, task_id=task_id, user_id=str(user.id), status=fields.pop("status")
        )
        if fields:
            task = plan_service.update_task(
                db, task_id=task_id, user_id=str(user.id), **fields
            )
    else:
        task = plan_service.update_task(
            db, task_id=task_id, user_id=str(user.id), **fields
        )
    return _task_to_response(task)


@tasks_router.delete("/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_task(task_id: str, db: DbDep, user: CurrentUserDep) -> None:
    plan_service.delete_task(db, task_id=task_id, user_id=str(user.id))
```

- [ ] **Step 4: 注册 router**

在 `server/app/main.py` 中找到 router 注册的地方，添加：

```python
from app.api.v1.plan import router as plan_router, tasks_router as task_router

app.include_router(plan_router, prefix="/api/v1")
app.include_router(task_router, prefix="/api/v1")
```

注意：检查现有 router 注册的 prefix 模式，保持一致。如果现有是 `app.include_router(diary_router, prefix="/api/v1")`，就用相同方式。

- [ ] **Step 5: 编写 API 测试**

创建 `server/tests/unit/api/test_plan_routes.py`：

```python
"""Unit tests for plan/task REST API routes."""

import pytest
from fastapi.testclient import TestClient


def test_create_plan_with_tasks(test_client, auth_headers):
    """POST /plans 应创建 plan 并原子嵌入 tasks。"""
    response = test_client.post(
        "/api/v1/plans",
        json={
            "title": "晚间例程",
            "motivation": "改善睡眠",
            "source_refs": [{"type": "diary", "id": 1}],
            "tasks": [
                {"title": "睡前不看手机"},
                {"title": "泡茶", "due_date": "2026-08-10"},
            ],
            "source": "agent",
            "created_from_conversation_id": "conv-1",
        },
        headers=auth_headers,
    )
    assert response.status_code == 201
    data = response.json()
    assert data["title"] == "晚间例程"
    assert data["source"] == "agent"
    assert len(data["tasks"]) == 2


def test_list_plans(test_client, auth_headers):
    """GET /plans 应列出当前用户的计划。"""
    test_client.post(
        "/api/v1/plans",
        json={"title": "计划A"},
        headers=auth_headers,
    )
    response = test_client.get("/api/v1/plans", headers=auth_headers)
    assert response.status_code == 200
    plans = response.json()
    assert any(p["title"] == "计划A" for p in plans)


def test_create_standalone_task(test_client, auth_headers):
    """POST /tasks 创建独立 task。"""
    response = test_client.post(
        "/api/v1/tasks",
        json={"title": "买菜", "due_date": "2026-08-10"},
        headers=auth_headers,
    )
    assert response.status_code == 201
    assert response.json()["title"] == "买菜"


def test_get_today_tasks(test_client, auth_headers):
    """GET /tasks/today 应返回今日待办。"""
    from datetime import date
    today = date.today().isoformat()
    test_client.post(
        "/api/v1/tasks",
        json={"title": "今日到期", "due_date": today},
        headers=auth_headers,
    )
    test_client.post(
        "/api/v1/tasks",
        json={"title": "无截止日的 pending"},
        headers=auth_headers,
    )
    response = test_client.get("/api/v1/tasks/today", headers=auth_headers)
    assert response.status_code == 200
    titles = [t["title"] for t in response.json()]
    assert "今日到期" in titles
    assert "无截止日的 pending" in titles


def test_complete_task(test_client, auth_headers):
    """PATCH /tasks/{id} 标记完成。"""
    create = test_client.post(
        "/api/v1/tasks",
        json={"title": "待完成"},
        headers=auth_headers,
    )
    task_id = create.json()["id"]
    response = test_client.patch(
        f"/api/v1/tasks/{task_id}",
        json={"status": "done"},
        headers=auth_headers,
    )
    assert response.status_code == 200
    assert response.json()["status"] == "done"
    assert response.json()["completed_at"] is not None


def test_delete_plan_404_for_other_user(test_client, auth_headers):
    """获取不存在的 plan 应 404。"""
    response = test_client.get(
        "/api/v1/plans/nonexistent-id",
        headers=auth_headers,
    )
    assert response.status_code == 404


def test_unauthenticated_rejected(test_client):
    """未认证应 401。"""
    response = test_client.get("/api/v1/plans")
    assert response.status_code == 401
```

注意：fixture `test_client` 和 `auth_headers` 用项目现有的（参考 `test_conversation_routes.py` 或 conftest）。

- [ ] **Step 6: 运行 API 测试**

```bash
cd d:\work\night_diary_v2\server
.venv\Scripts\python.exe -m pytest tests/unit/api/test_plan_routes.py -v
```

Expected: 全部 PASS

- [ ] **Step 7: lint 检查**

```bash
cd d:\work\night_diary_v2\server
.venv\Scripts\python.exe -m ruff check app/api/v1/plan.py app/api/schemas.py tests/unit/api/test_plan_routes.py
.venv\Scripts\python.exe -m mypy app/api/v1/plan.py
```

- [ ] **Step 8: 提交**

```bash
cd d:\work\night_diary_v2
& 'C:\Program Files\Git\cmd\git.exe' add server/app/api/v1/plan.py server/app/api/schemas.py server/app/main.py server/tests/unit/api/test_plan_routes.py
& 'C:\Program Files\Git\cmd\git.exe' commit -m "feat(api): add Plan/Task REST endpoints

POST/GET/PATCH/DELETE /api/v1/plans (with embedded task creation).
POST/GET/PATCH/DELETE /api/v1/tasks.
GET /api/v1/tasks/today aggregation.
source field (manual/agent) + created_from_conversation_id for audit."
```

---

## Task 4: 协议块 SSE 发布函数

**Files:**
- Modify: `server/app/shared/streaming_events.py`
- Modify: `server/tests/unit/shared/test_streaming_events.py`

- [ ] **Step 1: 编写 publish_protocol_block 失败测试**

在 `server/tests/unit/shared/test_streaming_events.py` 末尾追加：

```python
@pytest.mark.asyncio
async def test_publish_protocol_block_sends_correct_structure():
    """publish_protocol_block 应发送 PROTOCOL_BLOCK 事件，block 嵌套结构正确。"""
    from app.shared.streaming_events import publish_protocol_block, StreamingEventType

    bus = get_event_bus()
    trace_id = "test-trace-protocol"
    queue = await bus.subscribe(trace_id)

    await publish_protocol_block(
        trace_id,
        block_type="plan_proposal",
        block_id="temp-uuid-1",
        data={"title": "晚间例程", "tasks": []},
    )

    event = queue.get_nowait()
    assert event["type"] == StreamingEventType.PROTOCOL_BLOCK
    assert event["trace_id"] == trace_id
    assert event["block"]["block_type"] == "plan_proposal"
    assert event["block"]["block_id"] == "temp-uuid-1"
    assert event["block"]["data"]["title"] == "晚间例程"

    await bus.unsubscribe(trace_id, queue)


@pytest.mark.asyncio
async def test_publish_protocol_block_task_proposal():
    """publish_protocol_block 对 task_proposal 类型也应工作。"""
    from app.shared.streaming_events import publish_protocol_block

    bus = get_event_bus()
    trace_id = "test-trace-task-proposal"
    queue = await bus.subscribe(trace_id)

    await publish_protocol_block(
        trace_id,
        block_type="task_proposal",
        block_id="temp-uuid-2",
        data={"title": "写报告", "due_date": "2026-08-10"},
    )

    event = queue.get_nowait()
    assert event["block"]["block_type"] == "task_proposal"
    assert event["block"]["data"]["title"] == "写报告"

    await bus.unsubscribe(trace_id, queue)
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd d:\work\night_diary_v2\server
.venv\Scripts\python.exe -m pytest tests/unit/shared/test_streaming_events.py -v -k protocol_block
```

Expected: FAIL — `ImportError: cannot import name 'publish_protocol_block'`

- [ ] **Step 3: 在 streaming_events.py 添加 publish_protocol_block**

在 `server/app/shared/streaming_events.py` 末尾追加：

```python
async def publish_protocol_block(
    trace_id: str,
    *,
    block_type: str,
    block_id: str,
    data: dict[str, Any],
) -> None:
    """Publish a PROTOCOL_BLOCK event carrying structured content.

    Protocol blocks are produced by skills (e.g. PlannerAgent's
    ``plan_proposal``). The frontend renders them as interactive cards
    within the streaming reply — distinct from plain TEXT_DELTA content.

    The ``block`` field nests block_type / block_id / data so the SSE
    event envelope stays flat (type / trace_id at top level, structured
    payload under ``block``).
    """
    bus = get_event_bus()
    await bus.publish(
        trace_id,
        {
            "type": StreamingEventType.PROTOCOL_BLOCK,
            "trace_id": trace_id,
            "block": {
                "block_type": block_type,
                "block_id": block_id,
                "data": data,
            },
        },
    )
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd d:\work\night_diary_v2\server
.venv\Scripts\python.exe -m pytest tests/unit/shared/test_streaming_events.py -v
```

Expected: 全部 PASS（含新测试）

- [ ] **Step 5: lint 检查**

```bash
cd d:\work\night_diary_v2\server
.venv\Scripts\python.exe -m ruff check app/shared/streaming_events.py
.venv\Scripts\python.exe -m mypy app/shared/streaming_events.py
```

- [ ] **Step 6: 提交**

```bash
cd d:\work\night_diary_v2
& 'C:\Program Files\Git\cmd\git.exe' add server/app/shared/streaming_events.py server/tests/unit/shared/test_streaming_events.py
& 'C:\Program Files\Git\cmd\git.exe' commit -m "feat(streaming): add publish_protocol_block helper

Protocol blocks nest under 'block' key: {block_type, block_id, data}.
Produced by skills (PlannerAgent), rendered as cards by frontend."
```

---

## Task 5: ChatIntent 扩展 + 只读工具

**Files:**
- Modify: `server/app/domain/agents/types.py`
- Modify: `server/app/domain/agents/chat_intent_classifier.py`
- Modify: `server/app/services/ai/tool_factory.py`
- Modify: `server/tests/unit/domain/agents/test_chat_intent_classifier.py`
- Modify: `server/tests/unit/services/ai/test_tool_factory.py`

- [ ] **Step 1: 扩展 ChatIntent 枚举**

在 `server/app/domain/agents/types.py` 的 `ChatIntent` 类中，在 `ENTITY_QUERY` 之后添加：

```python
class ChatIntent(StrEnum):
    """Chat-specific intents for the conversation (multi-turn dialogue) scenario."""

    CASUAL_CHAT = "casual_chat"
    EMOTIONAL_VENT = "emotional_vent"
    RETROSPECTIVE_QUERY = "retrospective_query"
    ADVICE_SEEKING = "advice_seeking"
    CRISIS_SIGNAL = "crisis_signal"
    ENTITY_QUERY = "entity_query"
    # P2 新增
    PLAN_EXPLORATION = "plan_exploration"
    TASK_COMMAND = "task_command"
```

- [ ] **Step 2: 在 ChatIntentClassifier 添加关键词 + 路由**

在 `server/app/domain/agents/chat_intent_classifier.py` 中：

**添加关键词常量**（在现有 `_RETROSPECTIVE_KEYWORDS` 等附近）：

```python
_PLAN_EXPLORATION_KEYWORDS = (
    "帮我规划",
    "想养成",
    "想开始",
    "计划一下",
    "做个计划",
    "安排一下",
    "帮我安排",
    "想坚持",
    "想戒掉",
    "想改掉",
    "规划",
)

_TASK_COMMAND_KEYWORDS = (
    "加到待办",
    "加个待办",
    "记一下待办",
    "提醒我",
    "完成了",
    "做完了",
    "标记完成",
)
```

**在规则层路由判断中添加**（找到 `_rule_classify` 或类似的规则分类函数，在现有意图判断之后、默认 casual_chat 之前添加）：

```python
# P2: 计划相关意图
for kw in _TASK_COMMAND_KEYWORDS:
    if kw in text:
        return ChatIntentResult(
            intent_category=ChatIntent.TASK_COMMAND.value,
            need_tools=["list_todos"],
            tier="light",
            max_iterations=2,
            confidence=0.85,
        )

for kw in _PLAN_EXPLORATION_KEYWORDS:
    if kw in text:
        return ChatIntentResult(
            intent_category=ChatIntent.PLAN_EXPLORATION.value,
            need_tools=["list_todos", "get_plan_progress"],
            tier="heavy",
            max_iterations=5,
            confidence=0.8,
        )
```

注意：必须放在危机检测**之后**（危机优先），retrospective/advice 判断**之前**或之后（根据优先级，"规划"通常不和"上次"等同时出现，顺序影响小）。参考现有 `_rule_classify` 函数的实际位置。

- [ ] **Step 3: 在 tool_factory 添加只读工具**

在 `server/app/services/ai/tool_factory.py` 的 `build_tool_specs()` 函数中，在现有 5 个工具之后添加：

```python
ToolSpec(
    name="list_todos",
    description="列出用户当前的待办任务（只读）。可用于了解用户已有的计划负荷，避免重复建议。",
    parameters={
        "type": "object",
        "properties": {
            "status": {
                "type": "string",
                "enum": ["pending", "done", "all"],
                "default": "pending",
                "description": "过滤任务状态",
            },
            "plan_id": {
                "type": "string",
                "description": "可选：限定某个计划内的 tasks",
            },
        },
    },
),
ToolSpec(
    name="get_plan_progress",
    description="查询单个计划的执行进度（只读）。",
    parameters={
        "type": "object",
        "properties": {
            "plan_id": {"type": "string", "description": "计划 ID"},
        },
        "required": ["plan_id"],
    },
),
```

同时在工具实现（`build_tool_map` 或类似函数）中添加这两个工具的函数实现：

```python
def _list_todos(status: str = "pending", plan_id: str | None = None, **_):
    """列出当前用户的待办任务。"""
    from app.services import plan_service
    from app.infrastructure.database import SessionLocal

    db = SessionLocal()
    try:
        # user_id 从调用上下文获取（参考现有工具如何拿 user_id）
        # 这里需要看现有工具的实现模式——可能通过 closure 捕获
        tasks = plan_service.list_tasks(db, user_id=_current_user_id(), plan_id=plan_id, status=status if status != "all" else None)
        if not tasks:
            return "当前没有待办任务。"
        lines = [f"- {t.title}（状态：{t.status}）" for t in tasks[:10]]
        return f"当前待办（共 {len(tasks)} 条）：\n" + "\n".join(lines)
    finally:
        db.close()


def _get_plan_progress(plan_id: str, **_):
    """查询计划进度。"""
    from app.services import plan_service
    from app.infrastructure.database import SessionLocal

    db = SessionLocal()
    try:
        plan = plan_service.get_plan(db, plan_id=plan_id, user_id=_current_user_id())
        tasks = plan.tasks
        done = sum(1 for t in tasks if t.status == "done")
        total = len(tasks)
        return f"计划「{plan.title}」进度：{done}/{total} 完成。"
    finally:
        db.close()
```

**关键**：`_current_user_id()` 需要根据现有工具的实现方式获取。搜索 `tool_factory.py` 看现有工具（如 `get_user_address`）怎么拿 user_id——可能是通过 closure、thread-local、或参数注入。如果现有工具是通过 `build_tool_map(user_id=...)` 注入，沿用同样方式。

- [ ] **Step 4: 编写意图分类测试**

在 `server/tests/unit/domain/agents/test_chat_intent_classifier.py` 末尾追加：

```python
def test_classify_plan_exploration():
    """'帮我规划' 应分类为 plan_exploration。"""
    from app.domain.agents.chat_intent_classifier import ChatIntentClassifier
    # 参考 conftest 拿 mock llm
    classifier = ChatIntentClassifier(llm=_mock_llm())
    result = classifier.classify("帮我规划一下下周的学习计划")
    assert result.intent_category == "plan_exploration"
    assert "list_todos" in result.need_tools
    assert result.tier == "heavy"


def test_classify_task_command():
    """'加到待办' 应分类为 task_command。"""
    classifier = ChatIntentClassifier(llm=_mock_llm())
    result = classifier.classify("把明天开会加到待办")
    assert result.intent_category == "task_command"
    assert result.tier == "light"
    assert result.max_iterations == 2


def test_crisis_overrides_plan_exploration():
    """危机关键词 + 规划词，危机优先。"""
    classifier = ChatIntentClassifier(llm=_mock_llm())
    result = classifier.classify("我不想活了，帮我规划一下")
    assert result.intent_category == "crisis_signal"
```

注意：`_mock_llm()` 用 conftest 现有的 mock。如果测试因 LLM 层触发失败，调整 mock 让规则层先短路。

- [ ] **Step 5: 运行测试确认通过**

```bash
cd d:\work\night_diary_v2\server
.venv\Scripts\python.exe -m pytest tests/unit/domain/agents/test_chat_intent_classifier.py -v
```

Expected: 新增 3 个测试 + 现有全部 PASS

- [ ] **Step 6: 运行工具测试**

```bash
cd d:\work\night_diary_v2\server
.venv\Scripts\python.exe -m pytest tests/unit/services/ai/test_tool_factory.py -v
```

如果现有测试用 mock 检查 tool_specs 数量，可能需要更新断言数量（从 5 变 7）。

- [ ] **Step 7: lint 检查**

```bash
cd d:\work\night_diary_v2\server
.venv\Scripts\python.exe -m ruff check app/domain/agents/types.py app/domain/agents/chat_intent_classifier.py app/services/ai/tool_factory.py
.venv\Scripts\python.exe -m mypy app/domain/agents/types.py
```

- [ ] **Step 8: 提交**

```bash
cd d:\work\night_diary_v2
& 'C:\Program Files\Git\cmd\git.exe' add server/app/domain/agents/types.py server/app/domain/agents/chat_intent_classifier.py server/app/services/ai/tool_factory.py server/tests/unit/domain/agents/test_chat_intent_classifier.py server/tests/unit/services/ai/test_tool_factory.py
& 'C:\Program Files\Git\cmd\git.exe' commit -m "feat(intent): add plan_exploration and task_command intents + read-only tools

ChatIntent 6 -> 8. Two new read-only tools: list_todos, get_plan_progress.
Crisis keywords still take priority over plan exploration (safety gate)."
```

---

（计划继续：Task 6-10 在第二部分——PlannerAgent、前端 segments 模型、协议块卡片组件、PlanScene、e2e 测试）

---

## 第二周：PlannerAgent + 前端渲染模型

## Task 6: PlannerAgent 核心逻辑

**Files:**
- Create: `server/app/domain/agents/planner_agent.py`
- Create: `server/app/domain/agents/plan_completeness.py`
- Create: `server/tests/unit/domain/agents/test_planner_agent.py`

- [ ] **Step 1: 编写信息完整度判断的失败测试**

创建 `server/tests/unit/domain/agents/test_planner_agent.py`：

```python
"""Unit tests for PlannerAgent and plan completeness logic."""

import pytest

from app.domain.agents.plan_completeness import (
    CompletenessResult,
    assess_plan_completeness,
)


def test_completeness_both_present():
    """what 和 how 都有 → complete。"""
    result = assess_plan_completeness("我想早睡", "11点前睡，睡前不看手机")
    assert result.is_complete is True
    assert not result.missing_fields


def test_completeness_missing_how():
    """有 what 缺 how → 不完整，缺 how。"""
    result = assess_plan_completeness("我想养成早睡的习惯", "")
    assert result.is_complete is False
    assert "how" in result.missing_fields


def test_completeness_missing_what():
    """缺 what → 不完整。"""
    result = assess_plan_completeness("", "")
    assert result.is_complete is False
    assert "what" in result.missing_fields


def test_completeness_extracts_what():
    """应能提取 what 字段供后续使用。"""
    result = assess_plan_completeness("我想坚持跑步", "")
    assert result.what is not None
    assert "跑步" in result.what or "跑步" in str(result.context)
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd d:\work\night_diary_v2\server
.venv\Scripts\python.exe -m pytest tests/unit/domain/agents/test_planner_agent.py -v -k completeness
```

Expected: FAIL — `ModuleNotFoundError`

- [ ] **Step 3: 创建 plan_completeness.py**

创建 `server/app/domain/agents/plan_completeness.py`：

```python
"""Plan information completeness assessment.

Determines whether the user has provided enough information (what + how)
for the PlannerAgent to generate a plan proposal, or whether a
clarification round is needed.

This is intentionally a lightweight rule-based check (zero LLM cost) —
the PlannerAgent LLM call is only invoked once the user has provided at
least a goal (what). The LLM then decides whether to propose a plan or
ask a follow-up.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class CompletenessResult:
    """Result of assessing plan information completeness."""

    is_complete: bool
    what: str | None = None
    how: str | None = None
    when: str | None = None
    missing_fields: list[str] = field(default_factory=list)
    context: dict[str, Any] = field(default_factory=dict)


# 启发式信号词
_GOAL_SIGNALS = re.compile(
    r"(想|要|希望|打算|计划|开始|养成|坚持|戒掉|改掉|完成|实现|达到)"
)
_METHOD_SIGNALS = re.compile(
    r"(怎么|如何|通过|用|靠|方式|方法|步骤|具体|每天|每周|定时|固定)"
)


def assess_plan_completeness(current_input: str, prior_context: str = "") -> CompletenessResult:
    """Assess whether current + prior input contain enough to propose a plan.

    A "complete" plan request needs at least:
    - ``what``: a goal (what the user wants to achieve)
    - ``how``: a method (optionally, how they plan to do it)

    If ``how`` is missing, the PlannerAgent may either propose a default
    method (with source refs) or ask for clarification.
    """
    combined = f"{prior_context} {current_input}".strip()
    has_what = bool(_GOAL_SIGNALS.search(combined)) and len(combined) > 2
    has_how = bool(_METHOD_SIGNALS.search(combined))

    missing: list[str] = []
    if not has_what:
        missing.append("what")
    if not has_how:
        missing.append("how")

    return CompletenessResult(
        is_complete=has_what,  # what 足够即可生成 proposal（how 可由 Agent 建议）
        what=current_input.strip() if has_what else None,
        how=current_input.strip() if has_how else None,
        missing_fields=missing,
        context={"raw_input": current_input, "prior": prior_context},
    )
```

- [ ] **Step 4: 运行测试确认通过**

```bash
cd d:\work\night_diary_v2\server
.venv\Scripts\python.exe -m pytest tests/unit/domain/agents/test_planner_agent.py -v -k completeness
```

Expected: 4 个测试 PASS

- [ ] **Step 5: 编写 PlannerAgent 的测试**

在 `test_planner_agent.py` 末尾追加：

```python
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.domain.agents.planner_agent import PlannerAgent, PlannerInput


@pytest.mark.asyncio
async def test_planner_emits_clarification_when_how_missing():
    """缺 how 时，PlannerAgent 应发 clarification_request 协议块。"""
    from app.shared.streaming_events import StreamingEventType
    from app.shared.trace_event_bus import get_event_bus

    trace_id = "test-planner-clarify"
    bus = get_event_bus()
    queue = await bus.subscribe(trace_id)

    planner = PlannerAgent(llm=MagicMock())
    inp = PlannerInput(
        user_input="我想养成早睡的习惯",
        prior_context="",
        trace_id=trace_id,
        user_id="user-1",
        conversation_id="conv-1",
    )

    with patch(
        "app.domain.agents.planner_agent.CrisisGuard"
    ) as mock_crisis_cls:
        mock_crisis_cls.return_value.detect.return_value = False
        await planner.run(inp)

    events = []
    while not queue.empty():
        events.append(queue.get_nowait())
    await bus.unsubscribe(trace_id, queue)

    blocks = [e for e in events if e.get("type") == StreamingEventType.PROTOCOL_BLOCK]
    assert len(blocks) == 1
    assert blocks[0]["block"]["block_type"] == "clarification_request"
    assert "how" in blocks[0]["block"]["data"]["missing_fields"]


@pytest.mark.asyncio
async def test_planner_emits_proposal_when_complete():
    """what + how 都有，PlannerAgent 应发 plan_proposal。"""
    from app.shared.streaming_events import StreamingEventType
    from app.shared.trace_event_bus import get_event_bus

    trace_id = "test-planner-propose"
    bus = get_event_bus()
    queue = await bus.subscribe(trace_id)

    mock_llm = MagicMock()
    mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content=(
        '{"title":"早睡计划","motivation":"改善睡眠","tasks":[{"title":"11点前睡"}]}'
    )))

    planner = PlannerAgent(llm=mock_llm)
    inp = PlannerInput(
        user_input="11点前睡，睡前不看手机",
        prior_context="我想养成早睡的习惯",
        trace_id=trace_id,
        user_id="user-1",
        conversation_id="conv-1",
    )

    with patch("app.domain.agents.planner_agent.CrisisGuard") as mock_crisis_cls:
        mock_crisis_cls.return_value.detect.return_value = False
        await planner.run(inp)

    events = []
    while not queue.empty():
        events.append(queue.get_nowait())
    await bus.unsubscribe(trace_id, queue)

    blocks = [e for e in events if e.get("type") == StreamingEventType.PROTOCOL_BLOCK]
    assert len(blocks) == 1
    assert blocks[0]["block"]["block_type"] == "plan_proposal"
    assert blocks[0]["block"]["data"]["title"] == "早睡计划"


@pytest.mark.asyncio
async def test_planner_short_circuits_on_crisis():
    """危机信号应短路，不发协议块。"""
    from app.shared.streaming_events import StreamingEventType
    from app.shared.trace_event_bus import get_event_bus

    trace_id = "test-planner-crisis"
    bus = get_event_bus()
    queue = await bus.subscribe(trace_id)

    planner = PlannerAgent(llm=MagicMock())
    inp = PlannerInput(
        user_input="我不想活了，帮我规划",
        prior_context="",
        trace_id=trace_id,
        user_id="user-1",
        conversation_id="conv-1",
    )

    with patch("app.domain.agents.planner_agent.CrisisGuard") as mock_crisis_cls:
        mock_crisis_cls.return_value.detect.return_value = True
        mock_crisis_cls.return_value.safe_response = "安全模板"
        await planner.run(inp)

    events = []
    while not queue.empty():
        events.append(queue.get_nowait())
    await bus.unsubscribe(trace_id, queue)

    # 危机短路：只应有 TEXT_DELTA（安全模板），无 PROTOCOL_BLOCK
    blocks = [e for e in events if e.get("type") == StreamingEventType.PROTOCOL_BLOCK]
    assert len(blocks) == 0
```

- [ ] **Step 6: 运行测试确认失败**

```bash
cd d:\work\night_diary_v2\server
.venv\Scripts\python.exe -m pytest tests/unit/domain/agents/test_planner_agent.py -v
```

Expected: 3 个新 PlannerAgent 测试 FAIL（模块不存在）

- [ ] **Step 7: 创建 planner_agent.py**

创建 `server/app/domain/agents/planner_agent.py`：

```python
"""PlannerAgent — multi-turn plan exploration skill (V3 P2).

Triggered by the ``plan_exploration`` intent in ConversationLoop. Handles:

1. Crisis short-circuit (defense line: never plan around crisis content)
2. Information completeness assessment (what / how)
3. Multi-turn clarification (emit clarification_request protocol block)
4. Plan proposal generation (emit plan_proposal protocol block with source refs)

The agent has ZERO write permissions — it never creates tasks/plans
directly. All writes happen via the user accepting a proposal in the
frontend, which calls the REST API.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any

from app.domain.agents.plan_completeness import assess_plan_completeness
from app.shared.crisis_guard import CrisisGuard
from app.shared.llm import LLMClient, message_text
from app.shared.streaming_events import (
    publish_protocol_block,
    publish_reply_end,
    publish_reply_start,
    publish_text_delta,
)

logger = logging.getLogger(__name__)

#: Prompt for the plan proposal LLM call. Enforces:
#: 1. Must attach source_refs when available
#: 2. Must avoid pressuring language (no 必须/应该/一定要)
#: 3. Max 5 tasks to avoid cognitive overload
#: 4. Output strict JSON for protocol block parsing
_PLAN_PROPOSAL_PROMPT = """你是一个温和的生活规划助手。基于用户的对话，生成一个计划提案。

约束：
1. 最多 5 个 task，避免认知过载
2. 禁止使用"必须""应该""一定要"等施压措辞，用"可以""试试""不妨"
3. motivation 字段：如果有相关历史数据（日记/记忆），附引用；否则诚实说明"基于本次对话的建议"
4. 输出严格 JSON，格式：{"title": str, "motivation": str, "tasks": [{"title": str, "note": str|null, "due_date": str|null}]}

用户目标：{what}
用户方法：{how}
相关历史：{context}

请生成 JSON："""


@dataclass
class PlannerInput:
    """Input to PlannerAgent.run."""

    user_input: str
    prior_context: str  # 上一轮的累积上下文（多轮累积）
    trace_id: str
    user_id: str
    conversation_id: str
    source_refs: list[dict[str, Any]] | None = None  # RAG 检索的相关日记/记忆


class PlannerAgent:
    """Multi-turn plan exploration skill agent.

    Stateless per-invocation — multi-turn state is managed by the caller
    (ConversationLoop passes prior_context accumulated across turns).
    """

    def __init__(self, llm: LLMClient, crisis_guard: CrisisGuard | None = None) -> None:
        self._llm = llm
        self._crisis = crisis_guard or CrisisGuard()

    async def run(self, inp: PlannerInput) -> None:
        """Execute one turn of plan exploration.

        Publishes to TraceEventBus:
        - crisis: TEXT_DELTA(safe_response) only
        - incomplete: clarification_request PROTOCOL_BLOCK
        - complete: plan_proposal PROTOCOL_BLOCK
        Always publishes REPLY_START and REPLY_END.
        """
        await publish_reply_start(inp.trace_id, intent="plan_exploration")

        # Defense: crisis short-circuit
        if self._crisis.detect(inp.user_input) or self._crisis.detect(inp.prior_context):
            await publish_text_delta(inp.trace_id, self._crisis.safe_response)
            await publish_reply_end(inp.trace_id)
            return

        completeness = assess_plan_completeness(inp.user_input, inp.prior_context)

        if not completeness.is_complete:
            # 缺 what —— 反问目标
            question = "你想达成什么目标呢？可以告诉我你想养成什么习惯，或者想完成什么事。"
            await publish_protocol_block(
                inp.trace_id,
                block_type="clarification_request",
                block_id=f"clarify-{inp.trace_id}",
                data={
                    "question": question,
                    "missing_fields": completeness.missing_fields,
                    "context": completeness.context,
                },
            )
            await publish_reply_end(inp.trace_id)
            return

        if "how" in completeness.missing_fields:
            # 有 what 缺 how —— 反问方法
            question = (
                f"{completeness.what} 是个很好的方向！你具体打算怎么做呢？"
                "比如设定固定时间，或者配合什么习惯？"
            )
            await publish_protocol_block(
                inp.trace_id,
                block_type="clarification_request",
                block_id=f"clarify-{inp.trace_id}",
                data={
                    "question": question,
                    "missing_fields": ["how"],
                    "context": {"what": completeness.what},
                },
            )
            await publish_reply_end(inp.trace_id)
            return

        # 信息完整 —— 生成 plan_proposal
        await self._emit_plan_proposal(inp, completeness)

    async def _emit_plan_proposal(self, inp: PlannerInput, completeness: Any) -> None:
        """Generate a plan proposal via LLM and publish it as protocol block."""
        prompt = _PLAN_PROPOSAL_PROMPT.format(
            what=completeness.what or inp.user_input,
            how=completeness.how or "（用户未指定，请提供建议）",
            context=json.dumps(inp.source_refs or [], ensure_ascii=False),
        )

        try:
            response = await self._llm.ainvoke(prompt)
            raw = message_text(response).strip()
            # 尝试解析 JSON（LLM 可能包 markdown code fence）
            cleaned = self._strip_code_fence(raw)
            proposal_data = json.loads(cleaned)
        except (json.JSONDecodeError, Exception) as exc:
            logger.warning("Plan proposal LLM/parse failed: %s", exc)
            # 降级：生成最小 proposal
            proposal_data = {
                "title": completeness.what or "新计划",
                "motivation": "基于本次对话的建议",
                "tasks": [{"title": completeness.what or "开始第一步", "note": None, "due_date": None}],
            }

        # Pre-publish crisis check on generated content
        proposal_text = proposal_data.get("motivation", "") + " ".join(
            t.get("title", "") for t in proposal_data.get("tasks", [])
        )
        if self._crisis.detect(proposal_text):
            await publish_text_delta(inp.trace_id, self._crisis.safe_response)
            await publish_reply_end(inp.trace_id)
            return

        # Attach source_refs if provided by caller (RAG results)
        if inp.source_refs:
            proposal_data["source_refs"] = inp.source_refs
        else:
            proposal_data["source_refs"] = []

        proposal_data["status"] = "awaiting_confirmation"

        await publish_protocol_block(
            inp.trace_id,
            block_type="plan_proposal",
            block_id=f"proposal-{inp.trace_id}",
            data=proposal_data,
        )
        await publish_reply_end(inp.trace_id)

    @staticmethod
    def _strip_code_fence(text: str) -> str:
        """Remove markdown ```json ... ``` fence if present."""
        if text.startswith("```"):
            lines = text.split("\n")
            # 去掉首行 ```json 和末行 ```
            lines = [l for l in lines if not l.strip().startswith("```")]
            return "\n".join(lines).strip()
        return text
```

- [ ] **Step 8: 运行测试确认通过**

```bash
cd d:\work\night_diary_v2\server
.venv\Scripts\python.exe -m pytest tests/unit/domain/agents/test_planner_agent.py -v
```

Expected: 7 个测试全部 PASS

- [ ] **Step 9: lint 检查**

```bash
cd d:\work\night_diary_v2\server
.venv\Scripts\python.exe -m ruff check app/domain/agents/planner_agent.py app/domain/agents/plan_completeness.py tests/unit/domain/agents/test_planner_agent.py
.venv\Scripts\python.exe -m mypy app/domain/agents/planner_agent.py app/domain/agents/plan_completeness.py
```

- [ ] **Step 10: 提交**

```bash
cd d:\work\night_diary_v2
& 'C:\Program Files\Git\cmd\git.exe' add server/app/domain/agents/planner_agent.py server/app/domain/agents/plan_completeness.py server/tests/unit/domain/agents/test_planner_agent.py
& 'C:\Program Files\Git\cmd\git.exe' commit -m "feat(planner): add PlannerAgent with multi-turn clarification + plan proposal

- plan_completeness: rule-based what/how detection (zero LLM cost)
- PlannerAgent: crisis short-circuit -> clarification -> proposal flow
- Zero write permissions: only emits protocol blocks, never writes tasks
- Prompt constraints: max 5 tasks, no pressuring language, attach source_refs"
```

---

## Task 7: ConversationLoop 集成 PlannerAgent

**Files:**
- Modify: `server/app/services/ai/conversation_loop.py`
- Modify: `server/tests/unit/services/ai/test_conversation_loop.py`

- [ ] **Step 1: 阅读现有 ConversationLoop 的 Stage 4 入口**

完整阅读 `server/app/services/ai/conversation_loop.py` 第 270-400 行（`run_conversation_loop` 的 Legacy loop 部分）。理解 Stage 1-3（session、危机、意图分类）结束后，在 Stage 4 Agentic Loop 开始前的位置——这就是插入 PlannerAgent 分支的地方。

- [ ] **Step 2: 在 Legacy loop 的 Stage 4 之前插入 PlannerAgent 分支**

在 `server/app/services/ai/conversation_loop.py` 中，找到 Legacy loop 里 Agentic Loop 开始的位置（大约第 373 行 `# ── Agentic Loop (stage 4) ──`）。在它**之前**插入 PlannerAgent 分支：

```python
        # ── P2: plan_exploration 意图分支 → PlannerAgent ──
        if (
            intent_result is not None
            and intent_result.intent_category == "plan_exploration"
            and not enable_tools  # 避免和工具循环冲突
        ):
            from app.domain.agents.planner_agent import PlannerAgent, PlannerInput

            planner = PlannerAgent(llm=llm, crisis_guard=crisis_guard_obj)
            # 从 session 获取上一轮的累积上下文（多轮澄清）
            prior_context = getattr(session, "plan_exploration_context", "") or ""
            planner_inp = PlannerInput(
                user_input=content,
                prior_context=prior_context,
                trace_id="",  # Legacy loop 无 trace_id（流式版本才有）
                user_id=user_id,
                conversation_id=conversation_id,
            )
            # 非 trace_id 模式：直接 await，不发 SSE（sync 路径）
            # 真正的协议块推送在流式版本（generate_reply_streaming）中
            # 这里只更新 session 上下文
            try:
                await planner.run(planner_inp)
            except Exception as exc:
                logger.warning("PlannerAgent failed: %s", exc)
                return LoopResult(
                    reply_text=FALLBACK_FEEDBACK,
                    token_info={},
                    stop_reason="error",
                )
            # PlannerAgent 已发完事件，session 记录上下文
            session.plan_exploration_context = f"{prior_context}\n{content}".strip()
            return LoopResult(
                reply_text="[plan proposal emitted via protocol block]",
                token_info={},
                stop_reason="completed",
            )
```

注意：
- `crisis_guard_obj` 是 Legacy loop 里已有的 CrisisGuard 实例（查看变量名）
- `session.plan_exploration_context` 是一个新的 session 字段——需要检查 SessionContext 是否支持动态属性，如果不支持，用其他方式存（比如一个模块级 dict 或 session 的 metadata）
- Legacy loop（非流式）走这里只是为了不崩溃；真正的协议块推送在流式路径（`run_conversation_loop_streaming` 和 `generate_reply_streaming`）。P2 的 MVP 可以先只支持流式路径触发 PlannerAgent，Legacy loop 直接返回 fallback。

- [ ] **Step 3: 同步修改 run_conversation_loop_streaming**

在 `run_conversation_loop_streaming` 函数中（P0 加的流式版本），找到意图判断后的位置，添加相同的 PlannerAgent 分支。流式版本的优势是有 `trace_id`，协议块能正确推送：

```python
        # ── P2: plan_exploration 意图分支 → PlannerAgent (streaming) ──
        if (
            intent_result is not None
            and intent_result.intent_category == "plan_exploration"
        ):
            from app.domain.agents.planner_agent import PlannerAgent, PlannerInput

            # RAG 检索相关日记作为 source_refs（可选，提升 proposal 质量）
            source_refs = await self._collect_source_refs_for_planner(
                content, user_id, container
            ) if hasattr(self, "_collect_source_refs_for_planner") else []

            planner = PlannerAgent(llm=llm)
            prior_context = getattr(session, "plan_exploration_context", "") or ""
            planner_inp = PlannerInput(
                user_input=content,
                prior_context=prior_context,
                trace_id=trace_id,
                user_id=user_id,
                conversation_id=conversation_id,
                source_refs=source_refs,
            )
            await planner.run(planner_inp)
            session.plan_exploration_context = f"{prior_context}\n{content}".strip()
            return  # PlannerAgent 已发完所有事件
```

注意：`_collect_source_refs_for_planner` 是一个可选辅助函数，从 RAG 检索结果构造 source_refs。MVP 可以先不实现（传空数组），PlannerAgent 会诚实说明"基于本次对话的建议"。

- [ ] **Step 4: 编写集成测试**

在 `server/tests/unit/services/ai/test_conversation_loop.py` 末尾追加：

```python
@pytest.mark.asyncio
async def test_run_loop_plan_exploration_routes_to_planner(stub_container, db_session):
    """plan_exploration 意图应触发 PlannerAgent，不走工具循环。"""
    from app.domain.agents.types import ChatIntentResult
    from app.services.ai.conversation_loop import run_conversation_loop

    intent = ChatIntentResult(
        intent_category="plan_exploration",
        need_tools=["list_todos"],
        tier="heavy",
        max_iterations=5,
    )
    # Mock PlannerAgent.run 避免真实 LLM 调用
    with patch(
        "app.domain.agents.planner_agent.PlannerAgent.run", new_callable=AsyncMock
    ) as mock_run:
        result = run_conversation_loop(
            db=db_session,
            container=stub_container,
            conversation_id="conv-1",
            content="帮我规划早睡",
            pinned_diaries_text="",
            retrieved_diaries_text="",
            episodic_text="",
            memory_ids=[],
            intent_result=intent,
            user_id="user-1",
            use_graph=False,  # 强制走 Legacy loop
        )
        assert mock_run.called or result.stop_reason == "completed"
```

- [ ] **Step 5: 运行测试确认通过**

```bash
cd d:\work\night_diary_v2\server
.venv\Scripts\python.exe -m pytest tests/unit/services/ai/test_conversation_loop.py -v
```

Expected: 全部 PASS（含新测试 + 现有不退化）

- [ ] **Step 6: lint 检查**

```bash
cd d:\work\night_diary_v2\server
.venv\Scripts\python.exe -m ruff check app/services/ai/conversation_loop.py
.venv\Scripts\python.exe -m mypy app/services/ai/conversation_loop.py
```

- [ ] **Step 7: 提交**

```bash
cd d:\work\night_diary_v2
& 'C:\Program Files\Git\cmd\git.exe' add server/app/services/ai/conversation_loop.py server/tests/unit/services/ai/test_conversation_loop.py
& 'C:\Program Files\Git\cmd\git.exe' commit -m "feat(loop): integrate PlannerAgent for plan_exploration intent

Legacy loop and streaming loop both route plan_exploration to PlannerAgent
before entering the Agentic Loop. Other intents unchanged.
Multi-turn context stored on session.plan_exploration_context."
```

---

## Task 8: 前端 segments 渲染模型

**Files:**
- Modify: `src/shared/composables/useStreamingReply.ts`
- Modify: `src/shared/composables/__tests__/useStreamingReply.spec.ts`

- [ ] **Step 1: 编写 segments 模型的失败测试**

在 `src/shared/composables/__tests__/useStreamingReply.spec.ts` 末尾追加：

```typescript
describe('useStreamingReply protocol blocks', () => {
  beforeEach(() => {
    MockEventSource.instances = []
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('accumulates protocol_block as separate segment from text', async () => {
    const { segments, connect } = useStreamingReply()
    connect('http://localhost/sse')

    const mockES = MockEventSource.instances[0]
    mockES.emit('text_delta', { text: '你好，' })
    mockES.emit('text_delta', { text: '我有个建议：' })
    await vi.runAllTimersAsync()

    mockES.emit('protocol_block', {
      block: {
        block_type: 'plan_proposal',
        block_id: 'p1',
        data: { title: '早睡计划', tasks: [] },
      },
    })
    await vi.runAllTimersAsync()

    // 应该有 2 个段：1 个文本段 + 1 个协议块段
    expect(segments.value.length).toBe(2)
    expect(segments.value[0].kind).toBe('text')
    expect(segments.value[0].content).toContain('你好')
    expect(segments.value[1].kind).toBe('protocol_block')
    expect(segments.value[1].blockType).toBe('plan_proposal')
  })

  it('protocol_block status transitions on accept', async () => {
    const { segments, connect, acceptBlock } = useStreamingReply()
    connect('http://localhost/sse')

    const mockES = MockEventSource.instances[0]
    mockES.emit('protocol_block', {
      block: {
        block_type: 'plan_proposal',
        block_id: 'p1',
        data: { title: '测试', tasks: [] },
      },
    })
    await vi.runAllTimersAsync()

    // 初始 pending
    expect(segments.value[0].status).toBe('pending')

    // 模拟采纳
    await acceptBlock('p1')
    expect(segments.value[0].status).toBe('accepted')
  })

  it('replyText still works for backward compat (history messages)', async () => {
    const { replyText, connect } = useStreamingReply()
    connect('http://localhost/sse')

    const mockES = MockEventSource.instances[0]
    mockES.emit('text_delta', { text: '纯文本回复' })
    await vi.runAllTimersAsync()

    // replyText 仍然累积纯文本（向后兼容历史消息渲染）
    expect(replyText.value).toBe('纯文本回复')
  })
})
```

- [ ] **Step 2: 运行测试确认失败**

```bash
cd d:\work\night_diary_v2
npx vitest run src/shared/composables/__tests__/useStreamingReply.spec.ts
```

Expected: FAIL — `segments` 不存在

- [ ] **Step 3: 修改 useStreamingReply.ts 添加 segments 模型**

在 `src/shared/composables/useStreamingReply.ts` 中：

**添加类型定义**（在文件顶部，interface 之后）：

```typescript
export type RenderSegment =
  | { kind: 'text'; content: string }
  | {
      kind: 'protocol_block'
      blockType: string
      blockId: string
      data: Record<string, unknown>
      status: 'pending' | 'accepted' | 'rejected'
    }
```

**在 useStreamingReply 函数内添加 segments ref**（在 replyText 附近）：

```typescript
const segments = ref<RenderSegment[]>([])
let currentTextBuffer = ''
```

**修改 TEXT_DELTA 处理**（累积到 currentTextBuffer，不再直接写 replyText）：

```typescript
eventSource.addEventListener(TEXT_DELTA_EVENT, (e: MessageEvent) => {
  try {
    const { text } = JSON.parse(e.data) as { text: string }
    currentTextBuffer += text
    // 同步更新 replyText（向后兼容）
    replyText.value += text
    // 不立即创建 segment——等协议块或 reply_end 时 flush
    resetWatchdog()
  } catch {
    // Malformed event data — ignore
  }
})
```

**修改 PROTOCOL_BLOCK 处理**（新增监听器）：

```typescript
eventSource.addEventListener(PROTOCOL_BLOCK_EVENT, (e: MessageEvent) => {
  try {
    const payload = JSON.parse(e.data) as {
      block: { block_type: string; block_id: string; data: Record<string, unknown> }
    }
    // 先 flush 文本 buffer 为一个 text segment
    if (currentTextBuffer) {
      segments.value = [
        ...segments.value,
        { kind: 'text', content: currentTextBuffer },
      ]
      currentTextBuffer = ''
    }
    // 再 push 协议块 segment
    segments.value = [
      ...segments.value,
      {
        kind: 'protocol_block',
        blockType: payload.block.block_type,
        blockId: payload.block.block_id,
        data: payload.block.data,
        status: 'pending',
      },
    ]
    resetWatchdog()
  } catch {
    // Malformed — ignore
  }
})
```

**修改 REPLY_END 处理**（flush 最后的文本 buffer）：

```typescript
eventSource.addEventListener(REPLY_END_EVENT, (e: MessageEvent) => {
  // flush 剩余文本
  if (currentTextBuffer) {
    segments.value = [
      ...segments.value,
      { kind: 'text', content: currentTextBuffer },
    ]
    currentTextBuffer = ''
  }
  // ... 现有 REPLY_END 逻辑 ...
})
```

**添加 acceptBlock / rejectBlock 函数**：

```typescript
async function acceptBlock(blockId: string): Promise<void> {
  // 调用方负责真正的 REST 写入，这里只更新 UI 状态
  segments.value = segments.value.map((s) =>
    s.kind === 'protocol_block' && s.blockId === blockId
      ? { ...s, status: 'accepted' as const }
      : s,
  )
}

function rejectBlock(blockId: string): void {
  segments.value = segments.value.map((s) =>
    s.kind === 'protocol_block' && s.blockId === blockId
      ? { ...s, status: 'rejected' as const }
      : s,
  )
}
```

**在 connect 中重置 segments**：

```typescript
function connect(sseUrl: string): void {
  // ... 现有重置 ...
  segments.value = []
  currentTextBuffer = ''
  // ...
}
```

**添加常量**：

```typescript
const PROTOCOL_BLOCK_EVENT = 'protocol_block'
```

**更新返回对象和接口**，添加 `segments`、`acceptBlock`、`rejectBlock`。

- [ ] **Step 4: 运行测试确认通过**

```bash
cd d:\work\night_diary_v2
npx vitest run src/shared/composables/__tests__/useStreamingReply.spec.ts
```

Expected: 全部 PASS

- [ ] **Step 5: lint 检查**

```bash
cd d:\work\night_diary_v2
npx eslint src/shared/composables/useStreamingReply.ts
```

- [ ] **Step 6: 提交**

```bash
cd d:\work\night_diary_v2
& 'C:\Program Files\Git\cmd\git.exe' add src/shared/composables/useStreamingReply.ts src/shared/composables/__tests__/useStreamingReply.spec.ts
& 'C:\Program Files\Git\cmd\git.exe' commit -m "feat(frontend): add segments render model for protocol blocks

RenderSegment union: text | protocol_block. TEXT_DELTA accumulates into
text buffer, PROTOCOL_BLOCK flushes buffer + pushes block segment.
replyText ref kept for backward compat (history messages).
acceptBlock/rejectBlock update UI status."
```

---

## Task 9: 前端协议块卡片组件 + PlanScene

**Files:**
- Create: `src/features/chat/PlanProposalCard.vue`
- Create: `src/features/chat/ClarificationCard.vue`
- Create: `src/shared/api/plan.ts`
- Create: `src/features/plan/PlanScene.vue`
- Create: `src/stores/plan.ts`
- Modify: `src/router/index.ts`
- Modify: `src/features/chat/ChatMessage.vue`（按 segments 渲染）

> 这个任务较大，拆成多个子步骤。重点是让协议块卡片能渲染、能采纳写回，PlanScene 能查看。

- [ ] **Step 1: 创建 plan API 客户端**

创建 `src/shared/api/plan.ts`：

```typescript
import { getHttpClient } from '@/shared/composables/useBackend'

export interface SourceRef {
  type: 'diary' | 'episodic' | 'memory'
  id: string | number
  date?: string
  snippet?: string
}

export interface TaskItem {
  id: string
  plan_id: string | null
  title: string
  note: string | null
  due_date: string | null
  status: 'pending' | 'done' | 'skipped'
  source: 'manual' | 'agent'
  completed_at: string | null
}

export interface PlanItem {
  id: string
  title: string
  motivation: string | null
  source_refs: SourceRef[]
  status: 'active' | 'archived' | 'completed'
  source: 'manual' | 'agent'
  tasks: TaskItem[]
}

export async function createPlan(payload: {
  title: string
  motivation?: string
  source_refs?: SourceRef[]
  tasks?: Array<{ title: string; note?: string; due_date?: string }>
  source?: 'manual' | 'agent'
  created_from_conversation_id?: string
}): Promise<PlanItem> {
  const client = await getHttpClient()
  const { data } = await client.post<PlanItem>('/api/v1/plans', payload)
  return data
}

export async function listPlans(status?: string): Promise<PlanItem[]> {
  const client = await getHttpClient()
  const params = status ? { status } : {}
  const { data } = await client.get<PlanItem[]>('/api/v1/plans', { params })
  return data
}

export async function getTodayTasks(): Promise<TaskItem[]> {
  const client = await getHttpClient()
  const { data } = await client.get<TaskItem[]>('/api/v1/tasks/today')
  return data
}

export async function updateTaskStatus(
  taskId: string,
  status: 'pending' | 'done' | 'skipped',
): Promise<TaskItem> {
  const client = await getHttpClient()
  const { data } = await client.patch<TaskItem>(`/api/v1/tasks/${taskId}`, { status })
  return data
}

export async function deleteTask(taskId: string): Promise<void> {
  const client = await getHttpClient()
  await client.delete(`/api/v1/tasks/${taskId}`)
}

export async function deletePlan(planId: string): Promise<void> {
  const client = await getHttpClient()
  await client.delete(`/api/v1/plans/${planId}`)
}
```

- [ ] **Step 2: 创建 plan store**

创建 `src/stores/plan.ts`：

```typescript
import { defineStore } from 'pinia'
import { ref } from 'vue'
import * as planApi from '@/shared/api/plan'

export const usePlanStore = defineStore('plan', () => {
  const plans = ref<planApi.PlanItem[]>([])
  const todayTasks = ref<planApi.TaskItem[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function loadPlans() {
    loading.value = true
    error.value = null
    try {
      plans.value = await planApi.listPlans()
    } catch (err) {
      error.value = '加载计划失败'
    } finally {
      loading.value = false
    }
  }

  async function loadTodayTasks() {
    try {
      todayTasks.value = await planApi.getTodayTasks()
    } catch (err) {
      error.value = '加载今日待办失败'
    }
  }

  async function toggleTask(taskId: string, currentStatus: string) {
    const newStatus = currentStatus === 'done' ? 'pending' : 'done'
    try {
      await planApi.updateTaskStatus(taskId, newStatus)
      await loadTodayTasks()
      await loadPlans()
    } catch (err) {
      error.value = '更新任务失败'
    }
  }

  async function removeTask(taskId: string) {
    try {
      await planApi.deleteTask(taskId)
      await loadTodayTasks()
      await loadPlans()
    } catch (err) {
      error.value = '删除任务失败'
    }
  }

  async function removePlan(planId: string) {
    try {
      await planApi.deletePlan(planId)
      await loadPlans()
    } catch (err) {
      error.value = '删除计划失败'
    }
  }

  return {
    plans,
    todayTasks,
    loading,
    error,
    loadPlans,
    loadTodayTasks,
    toggleTask,
    removeTask,
    removePlan,
  }
})
```

- [ ] **Step 3: 创建 PlanProposalCard 组件**

创建 `src/features/chat/PlanProposalCard.vue`：

```vue
<template>
  <div class="plan-proposal-card" :class="{ accepted: status === 'accepted', rejected: status === 'rejected' }">
    <div class="card-header">
      <span class="card-icon">📋</span>
      <span class="card-title">{{ proposal.title }}</span>
    </div>

    <p v-if="proposal.motivation" class="motivation">{{ proposal.motivation }}</p>

    <div v-if="proposal.source_refs?.length" class="source-refs">
      <span class="refs-label">参考来源：</span>
      <span v-for="ref in proposal.source_refs" :key="`${ref.type}-${ref.id}`" class="ref-chip">
        {{ ref.type === 'diary' ? '日记' : ref.type === 'episodic' ? '记忆' : '资料' }}
        <span v-if="ref.date">{{ ref.date }}</span>
      </span>
    </div>

    <ul class="task-list">
      <li v-for="(task, i) in proposal.tasks" :key="i" class="task-item">
        <span class="task-title">{{ task.title }}</span>
        <span v-if="task.due_date" class="task-due">{{ task.due_date }}</span>
      </li>
    </ul>

    <div v-if="status === 'pending'" class="actions">
      <button class="btn-accept" @click="onAccept">采纳</button>
      <button class="btn-reject" @click="onReject">跳过</button>
    </div>
    <div v-else-if="status === 'accepted'" class="status-badge accepted">已添加到计划</div>
    <div v-else class="status-badge rejected">已跳过</div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { createPlan } from '@/shared/api/plan'

interface ProposalData {
  title: string
  motivation?: string
  source_refs?: Array<{ type: string; id: string | number; date?: string }>
  tasks: Array<{ title: string; note?: string; due_date?: string }>
}

const props = defineProps<{
  proposal: ProposalData
  conversationId?: string
}>()

const emit = defineEmits<{ accepted: []; rejected: [] }>()
const status = ref<'pending' | 'accepted' | 'rejected'>('pending')
const error = ref<string | null>(null)

async function onAccept() {
  error.value = null
  try {
    await createPlan({
      title: props.proposal.title,
      motivation: props.proposal.motivation,
      source_refs: props.proposal.source_refs?.map((r) => ({
        type: r.type as 'diary' | 'episodic' | 'memory',
        id: r.id,
        date: r.date,
      })),
      tasks: props.proposal.tasks.map((t) => ({
        title: t.title,
        note: t.note,
        due_date: t.due_date,
      })),
      source: 'agent',
      created_from_conversation_id: props.conversationId,
    })
    status.value = 'accepted'
    emit('accepted')
  } catch (err) {
    error.value = '添加失败，请重试'
  }
}

function onReject() {
  status.value = 'rejected'
  emit('rejected')
}
</script>

<style scoped>
.plan-proposal-card {
  border: 1px solid var(--border-color, #e4e4e7);
  border-radius: 12px;
  padding: 16px;
  margin: 8px 0;
  background: var(--surface-muted, #f9fafb);
}
.card-header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.card-title { font-weight: 600; font-size: 15px; }
.motivation { font-size: 14px; color: #52525b; margin: 8px 0; line-height: 1.5; }
.source-refs { font-size: 12px; color: #71717a; margin: 8px 0; }
.ref-chip { display: inline-block; padding: 2px 8px; background: #ede9fe; color: #6d28d9; border-radius: 999px; margin-right: 4px; }
.task-list { list-style: none; padding: 0; margin: 12px 0; }
.task-item { padding: 6px 0; border-bottom: 1px dashed #e4e4e7; font-size: 14px; }
.task-due { float: right; color: #71717a; font-size: 12px; }
.actions { display: flex; gap: 8px; margin-top: 12px; }
.btn-accept { background: #7c3aed; color: white; border: none; padding: 6px 16px; border-radius: 8px; cursor: pointer; }
.btn-reject { background: transparent; color: #71717a; border: 1px solid #e4e4e7; padding: 6px 16px; border-radius: 8px; cursor: pointer; }
.status-badge { font-size: 13px; padding: 4px 0; }
.status-badge.accepted { color: #10b981; }
.status-badge.rejected { color: #71717a; }
</style>
```

- [ ] **Step 4: 创建 ClarificationCard 组件**

创建 `src/features/chat/ClarificationCard.vue`：

```vue
<template>
  <div class="clarification-card">
    <div class="card-icon">💬</div>
    <p class="question">{{ clarification.question }}</p>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  clarification: {
    question: string
    missing_fields?: string[]
    context?: Record<string, unknown>
  }
}>()
</script>

<style scoped>
.clarification-card {
  border-left: 3px solid #7c3aed;
  padding: 8px 12px;
  margin: 8px 0;
  background: var(--surface-muted, #f9fafb);
  border-radius: 0 8px 8px 0;
}
.card-icon { font-size: 14px; }
.question { font-size: 14px; color: #52525b; margin: 4px 0 0; line-height: 1.5; }
</style>
```

- [ ] **Step 5: 创建 PlanScene**

创建 `src/features/plan/PlanScene.vue`：

```vue
<template>
  <div class="plan-scene">
    <h2>我的计划</h2>

    <section class="today-section">
      <h3>今日待办</h3>
      <div v-if="planStore.todayTasks.length === 0" class="empty">今天没有待办，享受当下吧</div>
      <div v-else>
        <div v-for="task in planStore.todayTasks" :key="task.id" class="task-row">
          <input
            type="checkbox"
            :checked="task.status === 'done'"
            @change="planStore.toggleTask(task.id, task.status)"
          />
          <span :class="{ done: task.status === 'done' }">{{ task.title }}</span>
          <span v-if="task.due_date" class="due">{{ task.due_date }}</span>
          <button class="btn-del" @click="planStore.removeTask(task.id)">×</button>
        </div>
      </div>
    </section>

    <section class="plans-section">
      <h3>计划</h3>
      <div v-if="planStore.plans.length === 0" class="empty">还没有计划，可以在对话中让 AI 帮你规划</div>
      <div v-else class="plan-list">
        <div v-for="plan in planStore.plans" :key="plan.id" class="plan-card">
          <div class="plan-header">
            <span class="plan-title">{{ plan.title }}</span>
            <span v-if="plan.source === 'agent'" class="badge-agent">AI 建议</span>
            <button class="btn-del" @click="planStore.removePlan(plan.id)">删除</button>
          </div>
          <p v-if="plan.motivation" class="plan-motivation">{{ plan.motivation }}</p>
          <div class="plan-progress">
            {{ plan.tasks.filter((t) => t.status === 'done').length }}/{{ plan.tasks.length }}
          </div>
          <ul class="plan-tasks">
            <li v-for="task in plan.tasks" :key="task.id">
              <input
                type="checkbox"
                :checked="task.status === 'done'"
                @change="planStore.toggleTask(task.id, task.status)"
              />
              <span :class="{ done: task.status === 'done' }">{{ task.title }}</span>
            </li>
          </ul>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { usePlanStore } from '@/stores/plan'

const planStore = usePlanStore()

onMounted(() => {
  planStore.loadPlans()
  planStore.loadTodayTasks()
})
</script>

<style scoped>
.plan-scene { padding: 20px; max-width: 800px; margin: 0 auto; }
h2 { margin-bottom: 20px; }
h3 { font-size: 16px; color: #52525b; margin: 20px 0 12px; }
.empty { color: #a1a1aa; font-size: 14px; padding: 16px 0; }
.task-row { display: flex; align-items: center; gap: 8px; padding: 8px 0; border-bottom: 1px solid #f4f4f5; }
.task-row.done span, .done { text-decoration: line-through; color: #a1a1aa; }
.due { font-size: 12px; color: #71717a; margin-left: auto; }
.btn-del { background: none; border: none; color: #d4d4d8; cursor: pointer; font-size: 18px; }
.btn-del:hover { color: #ef4444; }
.plan-card { border: 1px solid #e4e4e7; border-radius: 12px; padding: 16px; margin-bottom: 12px; }
.plan-header { display: flex; align-items: center; gap: 8px; }
.plan-title { font-weight: 600; flex: 1; }
.badge-agent { background: #ede9fe; color: #6d28d9; font-size: 11px; padding: 2px 8px; border-radius: 999px; }
.plan-motivation { font-size: 13px; color: #52525b; margin: 8px 0; }
.plan-progress { font-size: 12px; color: #71717a; }
.plan-tasks { list-style: none; padding: 0; margin: 8px 0 0; }
.plan-tasks li { padding: 4px 0; display: flex; align-items: center; gap: 8px; font-size: 14px; }
</style>
```

- [ ] **Step 6: 在 router 注册 /plan 路由**

在 `src/router/index.ts` 中添加：

```typescript
{
  path: '/plan',
  name: 'plan',
  component: () => import('@/features/plan/PlanScene.vue'),
  meta: { requiresAuth: true },
},
```

- [ ] **Step 7: 修改 ChatMessage 按 segments 渲染**

在 `src/features/chat/ChatMessage.vue` 中，找到消息内容渲染的部分。对于 assistant 角色的流式消息，如果有 segments，按段渲染：

```vue
<template>
  <div class="chat-message">
    <!-- 普通消息（历史或纯文本） -->
    <div v-if="!hasSegments" class="message-text">{{ message.content }}</div>

    <!-- 流式消息（带协议块段） -->
    <template v-else>
      <template v-for="(seg, i) in segments" :key="i">
        <div v-if="seg.kind === 'text'" class="message-text">{{ seg.content }}</div>
        <PlanProposalCard
          v-else-if="seg.kind === 'protocol_block' && seg.blockType === 'plan_proposal'"
          :proposal="seg.data"
          :conversation-id="conversationId"
        />
        <ClarificationCard
          v-else-if="seg.kind === 'protocol_block' && seg.blockType === 'clarification_request'"
          :clarification="seg.data"
        />
      </template>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import PlanProposalCard from './PlanProposalCard.vue'
import ClarificationCard from './ClarificationCard.vue'

const props = defineProps<{
  message: { content: string; role: string }
  segments?: Array<any>
  conversationId?: string
}>()

const hasSegments = computed(() => props.segments && props.segments.length > 0)
</script>
```

注意：具体的 props 传递取决于 chat store 怎么把 streamingReply.segments 传到 ChatMessage。需要在 ChatScene / OutputPanel 里把 `streamingReply.segments` 绑定到正在流式的消息组件上。

- [ ] **Step 8: 运行前端测试**

```bash
cd d:\work\night_diary_v2
npx vitest run
```

Expected: 全部 PASS

- [ ] **Step 9: lint 检查**

```bash
cd d:\work\night_diary_v2
npx eslint src/features/plan/ src/features/chat/PlanProposalCard.vue src/features/chat/ClarificationCard.vue src/shared/api/plan.ts src/stores/plan.ts
```

- [ ] **Step 10: 提交**

```bash
cd d:\work\night_diary_v2
& 'C:\Program Files\Git\cmd\git.exe' add src/features/plan/ src/features/chat/PlanProposalCard.vue src/features/chat/ClarificationCard.vue src/shared/api/plan.ts src/stores/plan.ts src/router/index.ts src/features/chat/ChatMessage.vue
& 'C:\Program Files\Git\cmd\git.exe' commit -m "feat(frontend): add PlanScene + protocol block cards + segments rendering

- PlanScene: today tasks + plan board with progress
- PlanProposalCard: in-chat card with accept/reject, REST write-back
- ClarificationCard: in-chat multi-turn question display
- ChatMessage: renders segments (text + protocol blocks) for streaming msgs
- plan store + plan API client"
```

---

## Task 10: e2e 集成测试 + 最终验证

**Files:**
- Create: `server/tests/e2e/test_plan_skill_flow.py`
- 验证所有测试套件

- [ ] **Step 1: 创建 e2e 多轮规划流测试**

创建 `server/tests/e2e/test_plan_skill_flow.py`：

```python
"""E2E tests for the plan skill multi-turn flow (V3 P2).

Tests the full vertical slice:
- Intent classification (plan_exploration)
- REST CRUD (plan/task creation)
- Today tasks aggregation
- Multi-tenant isolation
"""

import pytest


def test_plan_crud_full_cycle(e2e_client, auth_headers):
    """Plan 的完整 CRUD 周期。"""
    # Create
    create_resp = e2e_client.post(
        "/api/v1/plans",
        json={
            "title": "测试计划",
            "motivation": "e2e 测试",
            "tasks": [{"title": "task1"}, {"title": "task2"}],
        },
        headers=auth_headers,
    )
    assert create_resp.status_code == 201
    plan_id = create_resp.json()["id"]

    # Read
    get_resp = e2e_client.get(f"/api/v1/plans/{plan_id}", headers=auth_headers)
    assert get_resp.status_code == 200
    assert get_resp.json()["title"] == "测试计划"

    # Update
    patch_resp = e2e_client.patch(
        f"/api/v1/plans/{plan_id}",
        json={"status": "archived"},
        headers=auth_headers,
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["status"] == "archived"

    # Delete
    del_resp = e2e_client.delete(f"/api/v1/plans/{plan_id}", headers=auth_headers)
    assert del_resp.status_code == 204


def test_today_tasks_aggregation(e2e_client, auth_headers):
    """今日待办聚合。"""
    from datetime import date
    today = date.today().isoformat()

    e2e_client.post(
        "/api/v1/tasks",
        json={"title": "今日到期", "due_date": today},
        headers=auth_headers,
    )
    e2e_client.post(
        "/api/v1/tasks",
        json={"title": "无截止"},
        headers=auth_headers,
    )

    resp = e2e_client.get("/api/v1/tasks/today", headers=auth_headers)
    assert resp.status_code == 200
    titles = [t["title"] for t in resp.json()]
    assert "今日到期" in titles
    assert "无截止" in titles


def test_agent_sourced_plan_audited(e2e_client, auth_headers):
    """source=agent 的计划应带 created_from_conversation_id 审计字段。"""
    resp = e2e_client.post(
        "/api/v1/plans",
        json={
            "title": "AI 建议",
            "source": "agent",
            "created_from_conversation_id": "conv-abc",
            "tasks": [{"title": "建议 task", "source": "agent"}],
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["source"] == "agent"


def test_cascade_delete(e2e_client, auth_headers):
    """删 plan 应级联删 tasks。"""
    create = e2e_client.post(
        "/api/v1/plans",
        json={"title": "级联测试", "tasks": [{"title": "t1"}, {"title": "t2"}]},
        headers=auth_headers,
    )
    plan_id = create.json()["id"]

    # 确认 tasks 存在
    tasks = e2e_client.get(f"/api/v1/tasks?plan_id={plan_id}", headers=auth_headers)
    assert len(tasks.json()) == 2

    # 删 plan
    e2e_client.delete(f"/api/v1/plans/{plan_id}", headers=auth_headers)

    # tasks 应也没了
    tasks_after = e2e_client.get(f"/api/v1/tasks?plan_id={plan_id}", headers=auth_headers)
    assert len(tasks_after.json()) == 0
```

- [ ] **Step 2: 运行 e2e 测试**

```bash
cd d:\work\night_diary_v2\server
.venv\Scripts\python.exe -m pytest tests/e2e/test_plan_skill_flow.py -v
```

Expected: 4 个测试 PASS

- [ ] **Step 3: 运行完整后端测试套件**

```bash
cd d:\work\night_diary_v2\server
.venv\Scripts\python.exe -m pytest tests/unit/ tests/e2e/ -v --tb=short
```

Expected: 全部 PASS

- [ ] **Step 4: 运行完整前端测试**

```bash
cd d:\work\night_diary_v2
npx vitest run
```

Expected: 全部 PASS

- [ ] **Step 5: 后端 lint**

```bash
cd d:\work\night_diary_v2\server
.venv\Scripts\python.exe -m ruff check app/ tests/
.venv\Scripts\python.exe -m mypy app/
```

- [ ] **Step 6: 前端 lint**

```bash
cd d:\work\night_diary_v2
npx eslint src/ --ext .ts,.vue
```

- [ ] **Step 7: Alembic 迁移验证**

```bash
cd d:\work\night_diary_v2\server
.venv\Scripts\python.exe -m alembic upgrade head
.venv\Scripts\python.exe -m alembic current
```

Expected: 显示 `003_plan_task (head)`

- [ ] **Step 8: 尝试 eval 基线（可选）**

```bash
cd d:\work\night_diary_v2\server
.venv\Scripts\python.exe -m pytest tests/eval/ -v --timeout=300 -x
```

如果需要 LLM API key 而无法运行，记录原因并跳过。

- [ ] **Step 9: 提交 e2e 测试**

```bash
cd d:\work\night_diary_v2
& 'C:\Program Files\Git\cmd\git.exe' add server/tests/e2e/test_plan_skill_flow.py
& 'C:\Program Files\Git\cmd\git.exe' commit -m "test(e2e): add plan skill full vertical slice integration tests

Tests: plan CRUD cycle, today tasks aggregation, agent-sourced audit,
cascade delete. Validates the five-layer P2 slice end to end."
```

- [ ] **Step 10: 汇总验证结果**

在对话中汇报：
- 后端单元测试：X passed / Y failed
- 后端 e2e 测试：X passed / Y failed
- 前端测试：X passed / Y failed
- Ruff / Mypy / ESLint：pass/fail
- Alembic 迁移：是否成功
- Eval 基线：pass/fail/skipped

---

## 验证总结

完成所有 10 个任务后，验证以下端到端场景：

1. **数据层**：Alembic 迁移成功，Plan/Task 表存在，级联删除工作
2. **REST API**：`/api/v1/plans` 和 `/api/v1/tasks` CRUD 全通，多租户隔离
3. **意图分类**："帮我规划" → plan_exploration；"加到待办" → task_command；危机词优先短路
4. **PlannerAgent**：
   - 缺 how → 发 clarification_request
   - 完整 → 发 plan_proposal（带 source_refs）
   - 危机词 → 短路到安全响应
5. **协议块 SSE**：`PROTOCOL_BLOCK` 事件结构正确，前端可接收
6. **前端渲染**：
   - 会话内：PlanProposalCard 显示，采纳按钮调用 REST 写回
   - PlanScene：今日待办 + 计划看板可见，完成/删除工作
7. **现有 eval 基线不退化**
