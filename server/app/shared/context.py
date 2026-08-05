"""用于多租户数据隔离的请求级用户上下文。

``UserContext`` 将数据库会话、字符串形式的 ``user_id``（与用户作用域表上的
``VARCHAR(64)`` 列匹配）以及 ``UserRow`` ORM 对象打包在一起。在需要同时进行
数据库访问和用户作用域过滤的路由签名中，通过 ``UserContextDep`` 注入它。
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.infrastructure.models.user import UserRow


@dataclass
class UserContext:
    """为服务层调用打包数据库会话 + 已认证用户。"""

    db: Session
    user_id: str
    user: UserRow
