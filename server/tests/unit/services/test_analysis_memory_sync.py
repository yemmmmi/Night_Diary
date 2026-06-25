"""Unit tests for diary-to-memory sync in analysis_service.

Validates the P0 fix: diary analyses now write episodic entries and trigger
long-term profile promotion, closing the data-flow gap where analyses were
read by the multi-agent system but never written back.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.domain.memory.types import EpisodicEntry
from app.services.analysis_service import _sync_diary_to_memory


class _FakeDiaryEntry:
    """Minimal stand-in for DiaryEntryRow."""

    def __init__(self, entry_id: int = 1, content: str = "今天心情不错，很开心") -> None:
        self.id = entry_id
        self.content = content


class _FakeEpisodic:
    """Minimal episodic memory mock."""

    def __init__(self, *, store_result: bool = True) -> None:
        self._user_id = "default"
        self._entries: list[EpisodicEntry] = []
        self.store_result = store_result
        self.stored_entries: list[EpisodicEntry] = []

    def store(self, entry: EpisodicEntry) -> bool:
        if not self.store_result:
            return False
        self.stored_entries.append(entry)
        self._entries.append(entry)
        return True


class _FakeLongTerm:
    """Minimal long-term memory mock."""

    def __init__(self) -> None:
        self.promote_calls: list[tuple[str, list[EpisodicEntry]]] = []

    def promote_from_episodic(self, user_id: str, episodic_entries: list[EpisodicEntry]) -> None:
        self.promote_calls.append((user_id, episodic_entries))


class _FakeContainer:
    """Container with episodic + long_term memory."""

    def __init__(self, episodic, long_term) -> None:
        self.episodic_memory = episodic
        self.long_term_memory = long_term


class TestSyncDiaryToMemory:
    """Tests for _sync_diary_to_memory."""

    def test_stores_episodic_entry_with_correct_fields(self):
        """Diary content is converted to an EpisodicEntry and stored."""
        episodic = _FakeEpisodic()
        long_term = _FakeLongTerm()
        container = _FakeContainer(episodic, long_term)

        entry = _FakeDiaryEntry(content="今天加班很晚，感到焦虑和疲惫")
        _sync_diary_to_memory(entry, "AI建议好好休息", container)

        assert len(episodic.stored_entries) == 1
        stored = episodic.stored_entries[0]
        assert "加班" in stored.event
        assert stored.emotion in ("negative", "neutral", "positive", "crisis")
        assert stored.diary_ids == ["1"]
        assert stored.importance == pytest.approx(0.6)
        assert stored.ai_suggestion == "AI建议好好休息"

    def test_triggers_profile_promotion_after_store(self):
        """Long-term profile promotion is triggered after a successful store."""
        episodic = _FakeEpisodic()
        long_term = _FakeLongTerm()
        container = _FakeContainer(episodic, long_term)

        _sync_diary_to_memory(_FakeDiaryEntry(), "ai reply", container)

        assert len(long_term.promote_calls) == 1
        user_id, entries = long_term.promote_calls[0]
        assert user_id == "default"
        assert len(entries) == 1

    def test_skips_promotion_when_store_returns_false(self):
        """If episodic.store returns False, promotion is not triggered."""
        episodic = _FakeEpisodic(store_result=False)
        long_term = _FakeLongTerm()
        container = _FakeContainer(episodic, long_term)

        _sync_diary_to_memory(_FakeDiaryEntry(), "ai reply", container)

        assert len(episodic.stored_entries) == 0
        assert len(long_term.promote_calls) == 0

    def test_skips_when_episodic_memory_is_none(self):
        """No-op when container has no episodic_memory."""
        long_term = _FakeLongTerm()
        container = _FakeContainer(None, long_term)

        # Should not raise
        _sync_diary_to_memory(_FakeDiaryEntry(), "ai reply", container)

        assert len(long_term.promote_calls) == 0

    def test_truncates_long_event_summary(self):
        """Event summary is truncated to 120 chars + ellipsis."""
        episodic = _FakeEpisodic()
        long_term = _FakeLongTerm()
        container = _FakeContainer(episodic, long_term)

        long_content = "今天发生了很多事情，" * 50  # > 120 chars
        _sync_diary_to_memory(_FakeDiaryEntry(content=long_content), "ai", container)

        stored = episodic.stored_entries[0]
        assert len(stored.event) <= 124  # 120 + "…"
        assert stored.event.endswith("…")

    def test_store_exception_does_not_propagate(self):
        """If episodic.store raises, the exception is swallowed (best-effort)."""
        episodic = MagicMock()
        episodic.store.side_effect = RuntimeError("DB locked")
        long_term = _FakeLongTerm()
        container = _FakeContainer(episodic, long_term)

        # Should not raise
        _sync_diary_to_memory(_FakeDiaryEntry(), "ai", container)

        assert len(long_term.promote_calls) == 0

    def test_promotion_exception_does_not_propagate(self):
        """If promote_from_episodic raises, the exception is swallowed."""
        episodic = _FakeEpisodic()
        long_term = MagicMock()
        long_term.promote_from_episodic.side_effect = RuntimeError("Profile corrupt")
        container = _FakeContainer(episodic, long_term)

        # Should not raise
        _sync_diary_to_memory(_FakeDiaryEntry(), "ai", container)

        # Entry was still stored before promotion failed
        assert len(episodic.stored_entries) == 1
