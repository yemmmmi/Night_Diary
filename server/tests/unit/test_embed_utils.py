"""Unit tests for BgeEmbedder (V3 P4)."""

from __future__ import annotations

import math


def test_stub_embedder_returns_deterministic_vector() -> None:
    """StubEmbedder 应返回确定性向量(无模型下载,用于测试)。"""
    from app.shared.embed_utils import StubEmbedder

    embedder = StubEmbedder()
    vec1 = embedder.embed("失眠")
    vec2 = embedder.embed("失眠")
    assert vec1 == vec2  # 相同输入相同输出
    assert isinstance(vec1, list)
    assert len(vec1) > 0


def test_stub_embedder_different_inputs_different_vectors() -> None:
    """不同输入应产生不同向量。"""
    from app.shared.embed_utils import StubEmbedder

    embedder = StubEmbedder()
    vec1 = embedder.embed("失眠")
    vec2 = embedder.embed("吃饭")
    assert vec1 != vec2


def test_stub_embedder_deterministic_across_instances() -> None:
    """StubEmbedder 应跨实例确定性(基于 hashlib,而非受 PYTHONHASHSEED 影响)。"""
    from app.shared.embed_utils import StubEmbedder

    vec1 = StubEmbedder().embed("睡不着觉")
    vec2 = StubEmbedder().embed("睡不着觉")
    assert vec1 == vec2


def test_bge_embedder_returns_normalized_vector() -> None:
    """BgeEmbedder.embed 应返回归一化向量(模长接近 1)。

    注意:首次加载模型可能需要下载(几秒到几分钟)。这个测试标记 slow,
    如果模型已缓存则快速通过。
    """
    try:
        from app.shared.embed_utils import BgeEmbedder
    except ImportError:
        import pytest

        pytest.skip("BgeEmbedder not available")

    try:
        embedder = BgeEmbedder()
        vec = embedder.embed("失眠")
    except Exception as e:
        import pytest

        pytest.skip(f"Model not available in test env: {e}")

    assert isinstance(vec, list)
    assert len(vec) > 0  # 维度取决于模型(512 或 384)
    magnitude = math.sqrt(sum(v * v for v in vec))
    assert 0.9 <= magnitude <= 1.1  # normalize_embeddings=True


def test_bge_embedder_lazy_loads_on_first_embed() -> None:
    """BgeEmbedder 不应在 __init__ 时加载模型,仅在首次 embed 时加载。"""
    from app.shared.embed_utils import BgeEmbedder

    embedder = BgeEmbedder()
    # __init__ 后模型应未加载
    assert embedder._model is None


def test_embedder_protocol_interface() -> None:
    """Embedder 基类应定义 embed 接口。"""
    from app.shared.embed_utils import Embedder

    # Embedder 应该是可继承的基类(或 Protocol)
    class CustomEmbedder(Embedder):
        def embed(self, text: str) -> list[float]:
            return [0.0]

    custom = CustomEmbedder()
    assert custom.embed("test") == [0.0]


def test_api_embedder_returns_first_vector_from_api() -> None:
    """ApiEmbedder.embed 应调用 OpenAI 兼容端点并返回首条向量。"""
    from unittest.mock import MagicMock, patch

    from app.shared.embed_utils import ApiEmbedder

    fake_client = MagicMock()
    fake_client.embeddings.create.return_value = MagicMock(
        data=[MagicMock(embedding=[0.1, 0.2, 0.3])]
    )

    with patch("openai.OpenAI", return_value=fake_client) as mock_openai:
        embedder = ApiEmbedder(
            api_key="sk-test", base_url="https://api.example.com/v1", model="text-embedding-v3"
        )
        vec = embedder.embed("失眠")

    assert vec == [0.1, 0.2, 0.3]
    mock_openai.assert_called_once_with(
        api_key="sk-test", base_url="https://api.example.com/v1"
    )
    fake_client.embeddings.create.assert_called_once_with(
        model="text-embedding-v3", input=["失眠"]
    )


def test_api_embedder_lazy_loads_client_once() -> None:
    """ApiEmbedder 不应在 __init__ 时构造客户端,且两次 embed 复用同一客户端。"""
    from unittest.mock import MagicMock, patch

    from app.shared.embed_utils import ApiEmbedder

    fake_client = MagicMock()
    fake_client.embeddings.create.return_value = MagicMock(
        data=[MagicMock(embedding=[0.5])]
    )

    with patch("openai.OpenAI", return_value=fake_client) as mock_openai:
        embedder = ApiEmbedder(
            api_key="sk-test", base_url="https://api.example.com/v1", model="m"
        )
        assert embedder._client is None  # 未构造
        embedder.embed("第一次")
        embedder.embed("第二次")

    assert mock_openai.call_count == 1
    assert fake_client.embeddings.create.call_count == 2
