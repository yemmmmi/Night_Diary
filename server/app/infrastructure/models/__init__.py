"""ORM 模型包 — 重新导出以便便捷访问。

``env.py`` Alembic 环境从此包导入 ``*``，使所有模型在
自动生成运行前注册到 ``Base.metadata`` 中。各模块也在
``database.init_db`` 和 ``alembic/env.py`` 中被显式导入以增强健壮性。
"""

from app.infrastructure.models.pipeline_trace import PipelineTraceRow

__all__ = ["PipelineTraceRow"]
