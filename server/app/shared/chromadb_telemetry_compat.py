"""chromadb 0.5.x × posthog 7.x 兼容性补丁.

背景
----
两个问题:

1. **API 不兼容**: chromadb 0.5.x 的 ``_direct_capture`` 调用
   ``posthog.capture(distinct_id, event, properties)`` (3 位置参数),
   但 posthog 7.x 改为 ``capture(event, *, distinct_id=None, properties=None)``.

2. **消费者线程崩溃**: posthog 7.x 后台消费者线程在 Windows 上
   触发 access violation (segfault) 导致整个进程崩溃.

此补丁:
- 在 import chromadb 前设置 ``posthog.disabled = True``, 阻止 posthog
  创建默认客户端和消费者线程
- 将 ``Posthog._direct_capture`` 替换为空操作, 防止任何
  ``posthog.capture()`` 调用触发客户端创建
- 保留原始 ``Posthog.__init__`` 不变, 确保 chromadb 组件系统正确初始化

不影响 chromadb 的向量检索、集合管理等任何业务功能。
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

_patched = False


def apply_telemetry_compat_patch() -> None:
    """禁用 chromadb 的 posthog 遥测, 修复 Windows 崩溃问题.

    若 chromadb 未安装或已自行修复此问题，则静默跳过。
    """
    global _patched
    if _patched:
        return

    # ── 步骤 1: 在 chromadb import 前禁用 posthog 模块 ──
    try:
        import posthog as _posthog

        _posthog.disabled = True
        # 静默 posthog 日志
        _posthog_logger = logging.getLogger("posthog")
        _posthog_logger.disabled = True
    except ImportError:
        pass

    # ── 步骤 2: 猴补丁 chromadb 的 Posthog._direct_capture ──
    try:
        from chromadb.telemetry.product.posthog import Posthog
    except ImportError:
        # chromadb 未安装，无需补丁
        return

    original_direct_capture = Posthog._direct_capture

    import inspect

    # 检查是否已经修复
    src = inspect.getsource(original_direct_capture)
    if "disabled" in src and "return" in src:
        logger.debug("chromadb _direct_capture already compatible, skipping patch")
        return

    def _compat_direct_capture(self: Posthog, event: object) -> None:
        """空操作 — posthog 已在模块级别禁用.

        原始实现调用 posthog.capture(distinct_id, event, properties),
        这在 posthog 7.x 中会触发 TypeError (API 签名变更) 和
        消费者线程崩溃 (Windows access violation).
        """
        return

    Posthog._direct_capture = _compat_direct_capture
    _patched = True
    logger.info(
        "Applied chromadb×posthog telemetry compat patch "
        "(posthog.disabled=True + _direct_capture no-op)"
    )
