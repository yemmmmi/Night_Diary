"""用于完整用户数据迁移的导出/导入 API 路由。

本模块处理两种不同的资源（``/export`` 和 ``/import``），
因此有意省略了路由器级别的 ``prefix`` —— 完整子路径在每个
路由装饰器中声明。其余所有 v1 模块都只管理单一资源并使用
``prefix="/resource"``；导出/导入是唯一的例外，因为为两个路由
拆分出两个路由器属于过度设计。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from app.api.deps import ContainerDep, CurrentUserDep, DbDep
from app.services import export_service

router = APIRouter(tags=["export"])


@router.get("/export/all")
def export_all(db: DbDep, user: CurrentUserDep) -> dict[str, Any]:
    """将所有用户数据导出为 JSON dict。

    返回日记条目（含标签 + 分析）、记忆卡片、情景记忆以及长期画像。
    """
    return export_service.export_all(db, user_id=str(user.id))


class ImportRequest(BaseModel):
    """JSON 导入的请求体。接受与 export_all 输出相同的格式。"""

    data: dict[str, Any]


@router.post("/import/json")
def import_json(
    body: ImportRequest, db: DbDep, container: ContainerDep, user: CurrentUserDep
) -> dict[str, Any]:
    """从 JSON 导入用户数据，替换所有现有数据。

    清除现有的日记、标签、分析、记忆卡片和记忆，
    然后根据提供的 JSON 重建。ChromaDB 向量索引会为每个导入的
    日记条目重新构建。
    """
    summary = export_service.import_all(
        db,
        body.data,
        collection_manager=container.diary_collection,
        user_id=str(user.id),
    )
    return {"status": "ok", "imported": summary}
