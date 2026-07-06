"""Fixtures for the skill-call accuracy eval (progressive disclosure A/B).

Two injection strategies are exercised against the same 30-case annotated
dataset:

* **Full** — ``FullInjectionStrategy`` injects every skill's ``full_text`` in
  one shot. The LLM sees complete skill docs and declares which skills to use
  via ``<use_skill>name</use_skill>`` tags.

* **Progressive** — ``ProgressiveDisclosureStrategy`` injects only the compact
  ``summary`` of each skill. The LLM declares skills from summaries; the system
  loads the full ``body`` on demand (one disclosure round per declared skill).

Both paths parse ``<use_skill>`` tags from the LLM response via
``parse_use_skill_tags`` and compare the declared set against the annotated
``expected_skills``.

* Stub mode: ``ProgrammableStubLLM`` returns preset ``<use_skill>`` tags
  (oracle input) so the parsing pipeline + metric wiring can be verified
  deterministically in CI (no API key needed).
* Real mode: ``HttpLLM`` makes a real call; the LLM must select skills from the
  injected docs — this is the accuracy signal worth tracking for regression.

Set ``EVAL_UPDATE_BASELINE=1`` to (re)write ``baseline.json``.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from app.domain.skills.injection import (
    FullInjectionStrategy,
    ProgressiveDisclosureStrategy,
)
from app.domain.skills.skill_loader import SkillDoc, SkillDocLoader
from tests.eval._http_llm import MODEL, REAL_MODE, HttpLLM, is_auth_error
from tests.eval._stub_llm import ProgrammableStubLLM

DATA_DIR = Path(__file__).parent

#: Regex to parse ``<use_skill>name</use_skill>`` declarations from LLM output.
USE_SKILL_PATTERN = re.compile(r"<use_skill>\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*</use_skill>")


# --------------------------------------------------------------------------- #
# use_skill tag parser (shared by both paths)
# --------------------------------------------------------------------------- #
def parse_use_skill_tags(text: str) -> list[str]:
    """Parse ``<use_skill>name</use_skill>`` declarations from LLM response.

    Returns a list of skill names in order of appearance (duplicates removed
    after first occurrence to avoid double-counting).
    """
    seen: list[str] = []
    for match in USE_SKILL_PATTERN.finditer(text):
        name = match.group(1)
        if name not in seen:
            seen.append(name)
    return seen


# --------------------------------------------------------------------------- #
# Stub response builder
# --------------------------------------------------------------------------- #
def build_stub_response(case: dict[str, Any]) -> str:
    """Build the preset ``<use_skill>`` response for a case (oracle).

    For no-skill cases returns a plain empathetic reply (no tags). For skill
    cases returns one ``<use_skill>name</use_skill>`` block per expected skill.
    """
    skills = case.get("expected_skills", [])
    if not skills:
        return "好的，我理解你的感受，我会一直陪着你。"
    return " ".join(f"<use_skill>{s}</use_skill>" for s in skills)


def _stub_key(case_id: str) -> str:
    """Substring matched inside the stub prompt — bracketed for uniqueness."""
    return f"[{case_id}]"


# --------------------------------------------------------------------------- #
# Prompt builders
# --------------------------------------------------------------------------- #
_FULL_INSTRUCTION = (
    "以下是可用的技能完整文档。请根据用户消息判断需要使用哪些技能，"
    "在回复中用 <use_skill>技能名</use_skill> 声明。"
    "如果不需要任何技能，直接回复即可，不要声明任何技能。"
)

_PROG_INSTRUCTION = (
    "用户消息如下，请根据你的判断决定是否需要使用技能。"
)


def build_full_prompt(
    case: dict[str, Any],
    skills: list[SkillDoc],
    injector: FullInjectionStrategy,
    *,
    real_mode: bool,
) -> str:
    """Build the full-injection prompt for a case.

    The base prompt carries the user message + selection instruction; the
    injector appends all skills' ``full_text``. In stub mode the case_id is
    prefixed so the stub LLM can match the preset response.
    """
    base = f"{_PROG_INSTRUCTION}\n\n用户消息：{case['user_message']}\n\n{_FULL_INSTRUCTION}"
    prompt = injector.inject_prompt(skills, base)
    if not real_mode:
        prompt = f"{_stub_key(case['case_id'])}\n{prompt}"
    return prompt


def build_progressive_prompt(
    case: dict[str, Any],
    skills: list[SkillDoc],
    injector: ProgressiveDisclosureStrategy,
    *,
    real_mode: bool,
) -> str:
    """Build the progressive-disclosure prompt for a case.

    The base prompt carries the user message; the injector appends only skill
    ``summary`` blocks plus the ``<use_skill>`` instruction. In stub mode the
    case_id is prefixed for stub matching.
    """
    base = f"{_PROG_INSTRUCTION}\n\n用户消息：{case['user_message']}"
    prompt = injector.inject_prompt(skills, base)
    if not real_mode:
        prompt = f"{_stub_key(case['case_id'])}\n{prompt}"
    return prompt


# --------------------------------------------------------------------------- #
# Auth preflight (real mode only): skip the suite on a dead key
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="session", autouse=True)
def _auth_preflight() -> None:
    if not REAL_MODE:
        return
    try:
        HttpLLM(max_tokens=1, max_retries=1).invoke("ping")
    except Exception as exc:
        if is_auth_error(exc):
            pytest.skip(f"LLM auth failed (check LLM_API_KEY in server/.env): {exc}")


# --------------------------------------------------------------------------- #
# Mode + dataset fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="session")
def real_mode() -> bool:
    return REAL_MODE


@pytest.fixture(scope="session")
def model_name() -> str:
    return MODEL if REAL_MODE else "stub"


@pytest.fixture(scope="session")
def eval_cases() -> list[dict[str, Any]]:
    return json.loads((DATA_DIR / "test_cases.json").read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# Skill docs + injectors
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="session")
def skill_docs() -> dict[str, SkillDoc]:
    """Load all 4 SKILL.md documents via SkillDocLoader."""
    return SkillDocLoader().load_all()


@pytest.fixture(scope="session")
def skills_list(skill_docs: dict[str, SkillDoc]) -> list[SkillDoc]:
    """Ordered list of SkillDoc objects (sorted by name for determinism)."""
    return [skill_docs[name] for name in sorted(skill_docs)]


@pytest.fixture(scope="session")
def full_injector() -> FullInjectionStrategy:
    return FullInjectionStrategy()


@pytest.fixture(scope="session")
def progressive_injector() -> ProgressiveDisclosureStrategy:
    return ProgressiveDisclosureStrategy()


# --------------------------------------------------------------------------- #
# LLM fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture(scope="session")
def stub_responses(eval_cases: list[dict[str, Any]]) -> dict[str, str]:
    """Map ``case_id`` -> preset ``<use_skill>`` response text."""
    return {c["case_id"]: build_stub_response(c) for c in eval_cases}


@pytest.fixture(scope="session")
def stub_llm(stub_responses: dict[str, str]) -> ProgrammableStubLLM:
    """Always-stub LLM matching by ``[case_id]`` substring."""
    responses = [(_stub_key(cid), text) for cid, text in stub_responses.items()]
    return ProgrammableStubLLM(responses, default_response="好的，我理解你。")


@pytest.fixture(scope="session")
def real_llm(real_mode: bool) -> HttpLLM | None:
    """Real HTTP LLM (only when LLM_API_KEY is configured)."""
    if real_mode:
        return HttpLLM(temperature=0.0, max_tokens=800)
    return None


__all__ = [
    "USE_SKILL_PATTERN",
    "build_full_prompt",
    "build_progressive_prompt",
    "build_stub_response",
    "full_injector",
    "parse_use_skill_tags",
    "progressive_injector",
    "real_llm",
    "skills_list",
    "stub_llm",
    "stub_responses",
]
