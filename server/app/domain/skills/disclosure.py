"""Progressive skill disclosure — Level 0 metadata + Level 1 SKILL.md body.

Promotes ``skill_docs`` from passive documentation to a runtime disclosure
source, in the same spirit as Hermes' two-level skill loading:

- **Level 0** — a compact catalog (id / label / description / token cost) built
  from :class:`UserSkillSpec`. Cheap enough to inject into every
  intent-classification prompt so the router knows what skills exist.
- **Level 1** — the full SKILL.md body (triggers / capability / usage / example),
  loaded lazily via :class:`SkillDocLoader` only once a skill is actually hit,
  then injected into that skill's generation prompt.

Every failure degrades to an empty string, so disclosure can never break a reply.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from app.domain.skills.skill_loader import (
    USER_SKILL_DOCS_DIR,
    SkillDoc,
    SkillDocLoader,
)
from app.domain.skills.user_skill_registry import (
    UserSkillRegistry,
    get_user_skill_registry,
)
from app.shared.token_utils import estimate_tokens

logger = logging.getLogger(__name__)

#: Header used when a skill's Level-1 body is appended to its generation prompt.
SKILL_DOC_HEADER = "## 技能契约参考（仅供理解技能定位与边界，不改变上述输出规则）"


def format_skill_doc_reference(body: str) -> str:
    """Wrap a Level-1 SKILL.md body for prompt injection ("" when empty)."""
    text = (body or "").strip()
    if not text:
        return ""
    return f"\n\n{SKILL_DOC_HEADER}\n{text}"


@dataclass(frozen=True, slots=True)
class SkillLevel0:
    """Compact per-skill metadata injected at Level 0."""

    id: str
    label: str
    description: str
    token_cost: int


class SkillDisclosure:
    """Two-stage skill disclosure over the user-skill registry + SKILL.md docs."""

    def __init__(
        self,
        registry: UserSkillRegistry | None = None,
        *,
        docs_dir: Path | str | None = None,
    ) -> None:
        self._registry = registry if registry is not None else get_user_skill_registry()
        self._loader = SkillDocLoader(docs_dir if docs_dir is not None else USER_SKILL_DOCS_DIR)
        self._docs: dict[str, SkillDoc | None] = {}

    # ── Level 0: compact catalog ─────────────────────────────────────────
    def level0_items(self) -> list[SkillLevel0]:
        return [
            SkillLevel0(
                id=spec.id,
                label=spec.label,
                description=spec.description,
                token_cost=spec.token_cost,
            )
            for spec in self._registry.specs()
        ]

    def level0_catalog(self) -> str:
        """Render the Level-0 metadata block ("" when no skills registered)."""
        items = self.level0_items()
        if not items:
            return ""
        lines = ["可用技能（Level 0 元数据，命中后系统会自动加载完整技能文档）："]
        for item in items:
            cost = f"（≈{item.token_cost} tokens）" if item.token_cost else ""
            lines.append(f"- {item.id}（{item.label}）：{item.description}{cost}")
        return "\n".join(lines)

    def estimate_level0_tokens(self) -> int:
        return estimate_tokens(self.level0_catalog())

    # ── Level 1: full SKILL.md body ──────────────────────────────────────
    def load_doc(self, skill_id: str) -> SkillDoc | None:
        """Load (and cache) a skill's SKILL.md, or ``None`` if unavailable."""
        if skill_id in self._docs:
            return self._docs[skill_id]

        doc: SkillDoc | None = None
        spec = self._registry.spec(skill_id)
        if spec is not None and spec.doc_path:
            doc = self._loader.load(Path(spec.doc_path).stem)
            if doc is None:
                logger.warning(
                    "Level-1 doc missing for skill '%s' (doc_path=%s)",
                    skill_id,
                    spec.doc_path,
                )
        self._docs[skill_id] = doc
        return doc

    def level1_body(self, skill_id: str) -> str:
        """Return the skill's Level-1 disclosure body ("" when unavailable)."""
        doc = self.load_doc(skill_id)
        return doc.body if doc is not None else ""

    def estimate_level1_tokens(self, skill_id: str) -> int:
        return estimate_tokens(self.level1_body(skill_id))


_disclosure: SkillDisclosure | None = None


def get_skill_disclosure() -> SkillDisclosure:
    """Process-wide singleton (registry contents are static after startup)."""
    global _disclosure
    if _disclosure is None:
        _disclosure = SkillDisclosure()
    return _disclosure