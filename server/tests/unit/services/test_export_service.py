"""Unit tests for export/import service."""

from __future__ import annotations

import pytest

from app.services import diary_service, export_service


class TestExportImport:
    """Tests for export_all and import_all round-trip."""

    def test_export_empty_db(self, db_session):
        """Export of empty database returns valid structure with empty lists."""
        result = export_service.export_all(db_session)

        assert result["version"] == 1
        assert "exported_at" in result
        assert result["diaries"] == []
        assert result["tags"] == []
        assert result["analyses"] == []
        assert result["memory_cards"] == []
        assert result["episodic_memories"] == []
        assert result["long_term_profile"] is None

    def test_export_with_diary_and_tags(self, db_session):
        """Export includes diary content and tag associations."""
        from app.infrastructure.models.tag import TagRow

        tag1 = TagRow(name="开心", color="#FF0000")
        tag2 = TagRow(name="工作", color="#00FF00")
        db_session.add_all([tag1, tag2])
        db_session.flush()

        entry = diary_service.create_entry(
            db_session,
            content="今天工作很顺利",
            tag_ids=[tag1.id, tag2.id],
        )

        result = export_service.export_all(db_session)
        assert len(result["diaries"]) == 1
        assert result["diaries"][0]["content"] == "今天工作很顺利"
        assert set(result["diaries"][0]["tag_ids"]) == {tag1.id, tag2.id}
        assert len(result["tags"]) == 2

    def test_import_round_trip(self, db_session):
        """Import of exported data preserves diary content."""
        diary_service.create_entry(db_session, content="测试日记内容A")
        diary_service.create_entry(db_session, content="测试日记内容B")

        exported = export_service.export_all(db_session)
        assert len(exported["diaries"]) == 2

        summary = export_service.import_all(db_session, exported)
        assert summary["diaries"] == 2

        # Verify data was imported
        re_exported = export_service.export_all(db_session)
        contents = [d["content"] for d in re_exported["diaries"]]
        assert "测试日记内容A" in contents
        assert "测试日记内容B" in contents

    def test_import_clears_existing(self, db_session):
        """Import replaces existing data."""
        diary_service.create_entry(db_session, content="旧数据")
        exported = export_service.export_all(db_session)

        # Add more data after export
        diary_service.create_entry(db_session, content="新数据")
        assert len(export_service.export_all(db_session)["diaries"]) == 2

        # Import the earlier export (only 1 diary)
        export_service.import_all(db_session, exported)

        result = export_service.export_all(db_session)
        assert len(result["diaries"]) == 1
        assert result["diaries"][0]["content"] == "旧数据"

    def test_import_rejects_wrong_version(self, db_session):
        """Import raises ValueError for unsupported version."""
        with pytest.raises(ValueError, match="Unsupported export version"):
            export_service.import_all(db_session, {"version": 999})

    def test_import_preserves_tag_associations(self, db_session):
        """Tag-diary associations are preserved through export/import."""
        from app.infrastructure.models.tag import TagRow

        tag = TagRow(name="重要", color="#FF6600")
        db_session.add(tag)
        db_session.flush()

        diary_service.create_entry(
            db_session,
            content="重要的事情",
            tag_ids=[tag.id],
        )

        exported = export_service.export_all(db_session)
        export_service.import_all(db_session, exported)

        re_exported = export_service.export_all(db_session)
        assert len(re_exported["tags"]) == 1
        assert re_exported["tags"][0]["name"] == "重要"
        assert len(re_exported["diaries"]) == 1
        assert len(re_exported["diaries"][0]["tag_ids"]) == 1
