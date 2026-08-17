"""Unit tests for ContentNormalizer (from_diary / from_card / from_conversation / from_task)."""

from __future__ import annotations


def test_from_task_creates_atom_with_correct_fields():
    """from_task should build a source=task atom with importance>=0.6."""
    from app.services.normalizer import ContentNormalizer

    atom = ContentNormalizer.from_task(
        task_title="睡前不看手机",
        task_note="从今晚开始",
        plan_title="早睡挑战",
        status="done",
        user_id="user-1",
    )
    assert atom.source == "task"
    assert atom.importance >= 0.6
    assert atom.mood_score == 0.5
    assert "完成了" in atom.event_summary or "跳过了" in atom.event_summary
    assert "task" in atom.tags
    assert "done" in atom.tags
    assert "早睡挑战" in atom.tags


def test_from_task_without_plan():
    """A missing plan_title should still produce a valid atom."""
    from app.services.normalizer import ContentNormalizer

    atom = ContentNormalizer.from_task(
        task_title="买菜",
        task_note=None,
        plan_title=None,
        status="done",
        user_id="user-1",
    )
    assert atom.source == "task"
    assert atom.importance >= 0.6
    assert "买菜" in atom.event_summary


def test_from_task_skipped_status():
    """status=skipped should put '跳过了' into event_summary."""
    from app.services.normalizer import ContentNormalizer

    atom = ContentNormalizer.from_task(
        task_title="跑步",
        task_note=None,
        plan_title="运动计划",
        status="skipped",
        user_id="user-1",
    )
    assert "跳过了" in atom.event_summary


# ── V3 tree-hole: from_diary digest alignment ───────────────────────────


def test_from_diary_with_digest_uses_summary_and_topics():
    """提供 digest 时 event_summary 用摘要、tags 并入话题。"""
    from app.services.normalizer import ContentNormalizer
    from app.shared.digest import DiaryDigest, DiaryDigestPart

    entry = type(
        "Entry",
        (),
        {
            "id": 1,
            "content": "今天很焦虑，加班到很晚，项目延期了。",
            "tags": [],
            "date": None,
            "created_at": None,
        },
    )()
    digest = DiaryDigest(
        digest_type="complex",
        diary=DiaryDigestPart(
            intent="emotional_support",
            emotion="焦虑",
            topics=["加班", "项目延期"],
            summary="加班到很晚，项目延期，整体焦虑。",
        ),
    )
    atom = ContentNormalizer.from_diary(entry, user_id="u1", digest=digest)

    assert "加班到很晚" in atom.event_summary
    assert "项目延期" in atom.event_summary
    assert "加班" in atom.tags and "项目延期" in atom.tags  # 话题并入 tags
    assert atom.source == "diary"


def test_from_diary_without_digest_falls_back_to_truncation():
    """无 digest 时保持原行为：event_summary=正文截断。"""
    from app.services.normalizer import ContentNormalizer

    entry = type(
        "Entry",
        (),
        {"id": 1, "content": "今天吃了火锅。", "tags": [], "date": None, "created_at": None},
    )()
    atom = ContentNormalizer.from_diary(entry, user_id="u1")
    assert atom.event_summary == "今天吃了火锅。"
