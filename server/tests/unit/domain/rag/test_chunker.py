"""Unit tests for ChunkSplitter."""

from __future__ import annotations

from app.domain.rag.chunker import ChunkSplitter


def test_short_text_returns_single_chunk() -> None:
    splitter = ChunkSplitter(chunk_size=512, chunk_overlap=50, min_chunk_size=128)
    text = "今天心情不错，工作顺利完成。"
    assert splitter.split(text) == [text]


def test_long_text_respects_chunk_size_bound() -> None:
    splitter = ChunkSplitter(chunk_size=256, chunk_overlap=30, min_chunk_size=64)
    text = "今天。" * 200
    chunks = splitter.split(text)
    assert len(chunks) > 1
    for chunk in chunks:
        assert len(chunk) <= 256


def test_split_chunks_metadata_integrity() -> None:
    splitter = ChunkSplitter(chunk_size=512, chunk_overlap=50)
    text = "今天心情不错。" * 40
    chunks = splitter.split_chunks(text, diary_id="d-1", date="2025-01-15", tags="#工作")

    assert len(chunks) >= 1
    for index, chunk in enumerate(chunks):
        assert chunk.diary_id == "d-1"
        assert chunk.date == "2025-01-15"
        assert chunk.tags == "#工作"
        assert chunk.chunk_index == index
        assert chunk.chunk_total == len(chunks)
        assert chunk.doc_id == f"diary_d-1_chunk_{index}"
        assert chunk.doc_type == "chunk"


def test_parent_child_mode_produces_parent_and_children() -> None:
    splitter = ChunkSplitter(parent_child=True, child_chunk_size=80, child_overlap=10)
    text = "今天心情很好。" * 30
    parent, children = splitter.split_parent_child(text, diary_id="42")

    assert parent.doc_type == "parent"
    assert parent.doc_id == "parent_42"
    assert parent.content == text
    assert len(children) >= 1
    assert all(child.doc_type == "child" for child in children)
    assert all(child.parent_id == "parent_42" for child in children)


def test_extract_parent_id_from_child_doc_id() -> None:
    assert ChunkSplitter.extract_parent_id("child_42_3") == "parent_42"
    assert ChunkSplitter.extract_parent_id("parent_1") is None
    assert ChunkSplitter.extract_parent_id("") is None
