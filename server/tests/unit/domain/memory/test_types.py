"""Unit tests for EpisodicEntry embedding field (V3 P4)."""
import json
import time

from app.domain.memory.types import EpisodicEntry


def test_episodic_entry_has_embedding_field_default_none():
    """EpisodicEntry.embedding 默认应为 None(懒计算)。"""
    entry = EpisodicEntry(
        event_summary="测试",
        emotion="neutral",
        timestamp=time.time(),
        importance=0.6,
    )
    assert entry.embedding is None


def test_episodic_entry_embedding_assignable():
    """embedding 字段可赋值为 list[float]。"""
    entry = EpisodicEntry(
        event_summary="测试",
        emotion="neutral",
        timestamp=time.time(),
        importance=0.6,
    )
    entry.embedding = [0.1, 0.2, 0.3, 0.4]
    assert entry.embedding == [0.1, 0.2, 0.3, 0.4]


def test_episodic_entry_embedding_in_model_dump():
    """embedding 应出现在 model_dump / model_dump_json 中(用于 payload_json 序列化)。"""
    entry = EpisodicEntry(
        event_summary="测试",
        emotion="neutral",
        timestamp=time.time(),
        importance=0.6,
        embedding=[0.5, 0.6],
    )
    dumped = entry.model_dump()
    assert "embedding" in dumped
    assert dumped["embedding"] == [0.5, 0.6]

    # JSON 序列化也应包含 embedding(SqliteEpisodicMemoryStore 用 payload_json)
    json_str = entry.model_dump_json()
    data = json.loads(json_str)
    assert data["embedding"] == [0.5, 0.6]


def test_episodic_entry_backward_compatible_no_embedding_in_dict():
    """从 dict 构造时,缺 embedding 字段应自动填 None(历史数据兼容)。"""
    # 模拟历史 payload_json(无 embedding 字段)
    entry = EpisodicEntry(
        event_summary="历史",
        emotion="neutral",
        timestamp=time.time(),
        importance=0.6,
        # 不传 embedding
    )
    assert entry.embedding is None
