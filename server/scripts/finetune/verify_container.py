"""通过项目的 app 初始化路径验证 container.py 修改。

直接调用 create_container（项目启动时用的工厂函数），
然后检查 AI stack 的各个组件。
"""
import logging
import os
import sys

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("verify")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import Settings  # noqa: E402
from app.infrastructure.database import create_db_engine, create_session_factory  # noqa: E402
from app.shared.llm_factory import LLMFactory  # noqa: E402


def main():
    settings = Settings()
    logger.info("Settings: data_dir=%s models_dir=%s", settings.data_dir, settings.models_dir)

    # 检查微调模型是否存在
    ft_path = os.path.join(settings.models_dir, "reranker-night-diary")
    if os.path.exists(ft_path):
        logger.info("微调模型存在: %s", ft_path)
        has_safetensors = os.path.exists(os.path.join(ft_path, "model.safetensors"))
        has_config = os.path.exists(os.path.join(ft_path, "config.json"))
        logger.info("  model.safetensors: %s | config.json: %s", has_safetensors, has_config)
    else:
        logger.info("微调模型不存在，将使用基座 BAAI/bge-reranker-base")

    # 构造最小依赖
    engine = create_db_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    llm_factory = LLMFactory(settings)
    
    from app.infrastructure.feedback_repository import SqliteStylePreferenceStore
    from app.shared.tracing import NoOpAgentDecisionLogger, NoOpLLMCallTracer

    tracer = NoOpLLMCallTracer()
    decision_logger = NoOpAgentDecisionLogger()
    style_store = SqliteStylePreferenceStore(session_factory)

    from app.services.container import ServiceContainer
    container = ServiceContainer(
        settings=settings,
        engine=engine,
        session_factory=session_factory,
        llm_factory=llm_factory,
        llm_tracer=tracer,
        decision_logger=decision_logger,
        style_preference_store=style_store,
    )

    logger.info("=== 触发 ensure_ai_stack ===")
    try:
        container.ensure_ai_stack()
        logger.info("[OK] AI stack 初始化完成")
    except Exception as e:
        logger.error("[FAIL] AI stack 初始化失败: %s", e, exc_info=True)
        return 1

    # 检查 retriever 和 reranker
    if container.retriever is not None:
        r = container.retriever
        has_reranker = getattr(r, "_reranker", None)
        if has_reranker is not None:
            logger.info("[OK] HybridRetriever 已挂载 reranker: %s", type(has_reranker).__name__)
        else:
            logger.warning("[WARN] HybridRetriever._reranker 为 None（优雅降级）")

    # 检查 diary_collection 的 embedding
    if container.diary_collection is not None:
        logger.info("[OK] diary_collection 已创建: %s", type(container.diary_collection).__name__)

    logger.info("=== 验证完成 ===")
    return 0

if __name__ == "__main__":
    sys.exit(main())
