"""SkillDocLoader — 加载并解析 SKILL.md 文档，用于提示词注入。

每个 SKILL.md 文件遵循以下结构::

    ---
    name: skill_name
    triggers: [word1, word2]
    priority: 1.5
    category: retrieval
    token_cost_estimate: 200
    ---

    # Skill Title

    ## 一句话摘要
    <one-line summary>

    ## 触发条件
    ...

    ## 能力详述
    ...

    ## 调用方式
    ...

    ## 输出示例
    ...

加载器解析 YAML front matter（使用轻量级内置解析器，无需 PyYAML 依赖），
并将 Markdown 正文拆分为：

- ``summary`` — front matter + ``## 一句话摘要`` 部分（精简且 token 高效的概览）
- ``body``    — 其余部分（触发条件/能力详述/调用方式/输出示例）
- ``full_text``— 完整的原始文件内容
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 包含 SKILL.md 文件的默认目录（相对于本模块）。
DEFAULT_SKILL_DOCS_DIR = Path(__file__).resolve().parent / "skill_docs"

# 一句话摘要的章节标记。
_SUMMARY_HEADER = "## 一句话摘要"


@dataclass(frozen=True)
class SkillDoc:
    """单个 SKILL.md 文件的解析表示。

    Attributes:
        name: 技能标识符（来自 front matter 的 ``name`` 字段）。
        summary: front matter + ``## 一句话摘要`` 部分 — 精简概览，
                 适用于渐进式披露。
        body: 其余 Markdown 部分（触发条件/能力详述/调用方式/输出示例）。
        full_text: 完整的原始文件内容（front matter + body）。
    """

    name: str
    summary: str
    body: str
    full_text: str


# ---------------------------------------------------------------------------
# YAML front matter 解析（最小实现，无外部依赖）
# ---------------------------------------------------------------------------

def _split_front_matter(text: str) -> tuple[str, str]:
    """将原始文件文本拆分为 ``(front_matter_text, markdown_body)``。

    front matter 以首行的 ``---`` 起始，以另一个 ``---`` 结束。
    若未找到有效的 front matter，则返回 ``("", text)``。
    """
    stripped = text.lstrip()
    if not stripped.startswith("---"):
        return "", text

    lines = text.splitlines(keepends=True)
    # 查找结束的 ``---``（跳过起始行）。
    end_idx: int | None = None
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            end_idx = i
            break

    if end_idx is None:
        return "", text

    front_matter = "".join(lines[1:end_idx])
    body = "".join(lines[end_idx + 1 :])
    return front_matter, body


def _parse_scalar(value: str) -> Any:
    """将单个 YAML 标量值解析为 Python 类型。"""
    value = value.strip()
    # 内联列表：  [a, b, c]
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1]
        if not inner.strip():
            return []
        return [
            item.strip().strip("'\"")
            for item in inner.split(",")
            if item.strip()
        ]
    # 引号字符串
    if (value.startswith("'") and value.endswith("'")) or (
        value.startswith('"') and value.endswith('"')
    ):
        return value[1:-1]
    # 整数
    try:
        return int(value)
    except ValueError:
        pass
    # 浮点数
    try:
        return float(value)
    except ValueError:
        pass
    return value


def _parse_front_matter(front_matter_text: str) -> dict[str, Any]:
    """将最小化的 YAML front matter 块解析为字典。

    支持 ``key: value`` 和 ``key: [item, item]`` 内联列表。
    注释（``#``）和空行会被忽略。
    """
    result: dict[str, Any] = {}
    for line in front_matter_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if ":" not in stripped:
            continue
        key, _, raw_value = stripped.partition(":")
        key = key.strip()
        if not key:
            continue
        result[key] = _parse_scalar(raw_value)
    return result


# ---------------------------------------------------------------------------
# Markdown 章节拆分
# ---------------------------------------------------------------------------

def _extract_summary_section(markdown: str) -> tuple[str, str]:
    """将 markdown 正文拆分为 ``(summary_section, remaining_body)``。

    ``summary_section`` 包含 ``## 一句话摘要`` 标题及其内容。
    ``remaining_body`` 包含其余所有内容（标题 + 其他章节）。
    """
    idx = markdown.find(_SUMMARY_HEADER)
    if idx == -1:
        # 无摘要章节 — 将整个正文视为剩余部分。
        return "", markdown.strip()

    after_header = idx + len(_SUMMARY_HEADER)

    # 查找摘要之后的下一个顶级章节标题（## ）。
    next_match = re.search(r"\n## ", markdown[after_header:])
    if next_match is None:
        # 摘要是文件中的最后一个章节。
        summary_section = markdown[idx:].strip()
        before = markdown[:idx].strip()
        remaining = before
    else:
        absolute_end = after_header + next_match.start()
        summary_section = markdown[idx:absolute_end].strip()
        before = markdown[:idx]
        after = markdown[absolute_end:]
        remaining = (before + after).strip()

    return summary_section, remaining


def parse_skill_doc(raw_text: str, fallback_name: str = "") -> SkillDoc:
    """将原始 SKILL.md 文本解析为 :class:`SkillDoc`。

    Args:
        raw_text: SKILL.md 文件的完整内容。
        fallback_name: 当 front matter 中没有 ``name`` 字段时使用
                       （通常取自文件名主干）。
    """
    front_matter_text, markdown = _split_front_matter(raw_text)
    meta = _parse_front_matter(front_matter_text)
    name = str(meta.get("name", fallback_name))

    summary_section, remaining_body = _extract_summary_section(markdown)

    # summary = front matter 块 + 一句话摘要 部分
    front_block = f"---\n{front_matter_text.strip()}\n---\n\n" if front_matter_text else ""
    summary = front_block + summary_section if summary_section else front_block + remaining_body

    return SkillDoc(
        name=name,
        summary=summary.strip(),
        body=remaining_body.strip(),
        full_text=raw_text.strip(),
    )


# ---------------------------------------------------------------------------
# SkillDocLoader
# ---------------------------------------------------------------------------

class SkillDocLoader:
    """从目录加载 SKILL.md 文档，支持优雅降级。

    用法::

        loader = SkillDocLoader()
        all_docs = loader.load_all()          # dict[str, SkillDoc]
        one_doc = loader.load("crisis_detector")  # SkillDoc | None
    """

    def __init__(self, skill_docs_dir: Path | str | None = None) -> None:
        self._docs_dir = Path(skill_docs_dir) if skill_docs_dir else DEFAULT_SKILL_DOCS_DIR

    @property
    def docs_dir(self) -> Path:
        return self._docs_dir

    def load(self, name: str) -> SkillDoc | None:
        """按技能名称加载单个 SKILL.md。

        若文件缺失或无法解析，则返回 ``None``（并记录警告）—
        调用方应将其视为优雅降级处理。
        """
        path = self._docs_dir / f"{name}.md"
        if not path.is_file():
            logger.warning("SKILL.md not found for skill '%s' at %s", name, path)
            return None
        try:
            raw_text = path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.warning("Failed to read SKILL.md for skill '%s': %s", name, exc)
            return None
        try:
            return parse_skill_doc(raw_text, fallback_name=name)
        except Exception as exc:
            logger.warning("Failed to parse SKILL.md for skill '%s': %s", name, exc)
            return None

    def load_all(self) -> dict[str, SkillDoc]:
        """加载技能文档目录中的所有 ``*.md`` 文件。

        解析失败的文件会被跳过（优雅降级）；返回的字典将技能名映射到
        :class:`SkillDoc`。
        """
        if not self._docs_dir.is_dir():
            logger.warning("Skill docs directory not found: %s", self._docs_dir)
            return {}

        docs: dict[str, SkillDoc] = {}
        for path in sorted(self._docs_dir.glob("*.md")):
            try:
                raw_text = path.read_text(encoding="utf-8")
                doc = parse_skill_doc(raw_text, fallback_name=path.stem)
            except Exception as exc:
                logger.warning("Failed to parse SKILL.md '%s': %s", path, exc)
                continue
            if doc.name:
                docs[doc.name] = doc
            else:
                logger.warning("SKILL.md '%s' has no name; skipping", path)
        return docs
