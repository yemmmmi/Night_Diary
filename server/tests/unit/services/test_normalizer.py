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
