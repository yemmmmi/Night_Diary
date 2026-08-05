"""SkillDocLoader — load and parse SKILL.md documents for prompt injection.

Each SKILL.md file follows this structure::

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

The loader parses the YAML front matter (using a lightweight built-in parser
so no PyYAML dependency is required) and splits the Markdown body into:

- ``summary`` — front matter + the ``## 一句话摘要`` section (compact token-efficient overview)
- ``body``    — the remaining sections (触发条件/能力详述/调用方式/输出示例)
- ``full_text``— the complete original file content
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Default directory containing SKILL.md files (relative to this module).
DEFAULT_SKILL_DOCS_DIR = Path(__file__).resolve().parent / "skill_docs"

# Section marker for the one-line summary.
_SUMMARY_HEADER = "## 一句话摘要"


@dataclass(frozen=True)
class SkillDoc:
    """Parsed representation of a single SKILL.md file.

    Attributes:
        name: skill identifier (from front matter ``name`` field).
        summary: front matter + ``## 一句话摘要`` section — compact overview
                 suitable for progressive disclosure.
        body: remaining Markdown sections (触发条件/能力详述/调用方式/输出示例).
        full_text: the complete original file content (front matter + body).
    """

    name: str
    summary: str
    body: str
    full_text: str


# ---------------------------------------------------------------------------
# YAML front-matter parsing (minimal, no external dependency)
# ---------------------------------------------------------------------------

def _split_front_matter(text: str) -> tuple[str, str]:
    """Split raw file text into ``(front_matter_text, markdown_body)``.

    Front matter is delimited by ``---`` on the first line and a closing
    ``---``.  If no valid front matter is found, returns ``("", text)``.
    """
    stripped = text.lstrip()
    if not stripped.startswith("---"):
        return "", text

    lines = text.splitlines(keepends=True)
    # Find the closing ``---`` (skip the opening line).
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
    """Parse a single YAML scalar value into a Python type."""
    value = value.strip()
    # Inline list:  [a, b, c]
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1]
        if not inner.strip():
            return []
        return [
            item.strip().strip("'\"")
            for item in inner.split(",")
            if item.strip()
        ]
    # Quoted string
    if (value.startswith("'") and value.endswith("'")) or (
        value.startswith('"') and value.endswith('"')
    ):
        return value[1:-1]
    # Integer
    try:
        return int(value)
    except ValueError:
        pass
    # Float
    try:
        return float(value)
    except ValueError:
        pass
    return value


def _parse_front_matter(front_matter_text: str) -> dict[str, Any]:
    """Parse a minimal YAML front-matter block into a dict.

    Supports ``key: value`` and ``key: [item, item]`` inline lists.
    Comments (``#``) and blank lines are ignored.
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
# Markdown section splitting
# ---------------------------------------------------------------------------

def _extract_summary_section(markdown: str) -> tuple[str, str]:
    """Split markdown body into ``(summary_section, remaining_body)``.

    ``summary_section`` contains the ``## 一句话摘要`` header and its content.
    ``remaining_body`` contains everything else (title + other sections).
    """
    idx = markdown.find(_SUMMARY_HEADER)
    if idx == -1:
        # No summary section — treat entire body as remaining.
        return "", markdown.strip()

    after_header = idx + len(_SUMMARY_HEADER)

    # Find the next top-level section header (## ) after the summary.
    next_match = re.search(r"\n## ", markdown[after_header:])
    if next_match is None:
        # Summary is the last section in the file.
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
    """Parse raw SKILL.md text into a :class:`SkillDoc`.

    Args:
        raw_text: the complete contents of a SKILL.md file.
        fallback_name: used when front matter has no ``name`` field
                       (typically derived from the file stem).
    """
    front_matter_text, markdown = _split_front_matter(raw_text)
    meta = _parse_front_matter(front_matter_text)
    name = str(meta.get("name", fallback_name))

    summary_section, remaining_body = _extract_summary_section(markdown)

    # summary = front matter block + 一句话摘要 section
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
    """Load SKILL.md documents from a directory, with graceful degradation.

    Usage::

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
        """Load a single SKILL.md by skill name.

        Returns ``None`` (and logs a warning) if the file is missing or
        cannot be parsed — callers should treat this as graceful degradation.
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
        """Load every ``*.md`` file in the skill docs directory.

        Files that fail to parse are skipped (graceful degradation); the
        returned dict maps skill name -> :class:`SkillDoc`.
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
