"""LLM-as-Judge: score an AI reply against a rubric using a configured LLM.

The judge is the automated grader for generation quality. It is injected with an
LLM (DI — same as the production agents) so the eval can swap in DeepSeek, a
local model, or a deterministic stub in CI. Given ``(diary, ai_response,
rubric)`` it asks the judge model for a 1-5 score per dimension plus a rationale,
parses the JSON, and returns a :class:`JudgeResult`.

Two modes tune the prompt, not the parsing:

* ``strict`` — the judge must quote evidence from the original text for each
  score (used for the committed baseline so scores are defensible).
* ``lenient`` — a quick holistic scan (used for fast local iteration).

Latency and token usage of the *judge* call are captured so ``make eval`` can
report the eval's own cost and flag regressions.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Protocol

from app.domain.agents.state import extract_token_usage

from .rubric import EvalRubric

_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)
# Fallback score-field regex is built per-judge from ``rubric.keys`` (see
# ``_parse_scores_fallback``) so the malformed-JSON recovery honors whatever
# rubric is configured — including non-default ones (e.g. the plan rubric's
# ``actionability`` / ``gentleness`` dimensions).


class JudgeLLM(Protocol):
    """Minimal LLM port: ``invoke(prompt)`` returns a message or string."""

    def invoke(self, prompt: str) -> Any: ...


@dataclass(frozen=True, slots=True)
class JudgeResult:
    """Parsed judge output for one (diary, response) pair."""

    scores: dict[str, float]
    overall: float
    rationale: str
    latency_ms: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    raw: str = ""

    def passed(self, threshold: float) -> bool:
        """Whether the weighted overall score meets ``threshold`` (e.g. 3.5)."""
        return self.overall >= threshold


class JudgeParseError(ValueError):
    """Raised when the judge response cannot be parsed into scores."""


class LLMJudge:
    """Score AI replies against an :class:`EvalRubric` via a judge LLM."""

    def __init__(
        self,
        llm: JudgeLLM,
        rubric: EvalRubric | None = None,
        *,
        mode: str = "strict",
    ) -> None:
        if mode not in ("strict", "lenient"):
            raise ValueError(f"mode must be 'strict' or 'lenient', got {mode!r}")
        self._llm = llm
        self._rubric = rubric or EvalRubric.default()
        self._mode = mode

    @property
    def rubric(self) -> EvalRubric:
        return self._rubric

    def score(self, diary: str, response: str, *, history: str = "") -> JudgeResult:
        """Grade one reply; raises :class:`JudgeParseError` on unparseable output."""
        prompt = self._build_prompt(diary, response, history)

        started = perf_counter()
        raw_response = self._llm.invoke(prompt)
        latency_ms = (perf_counter() - started) * 1000

        content = getattr(raw_response, "content", raw_response)
        usage = extract_token_usage(raw_response)
        scores, rationale = self._parse(str(content))
        overall = self._rubric.weighted_overall(scores)

        return JudgeResult(
            scores=scores,
            overall=overall,
            rationale=rationale,
            latency_ms=latency_ms,
            tokens_in=usage["cache_hit_tokens"] + usage["cache_miss_tokens"],
            tokens_out=usage["output_tokens"],
            raw=str(content),
        )

    def _build_prompt(self, diary: str, response: str, history: str) -> str:
        evidence_rule = (
            "对每个维度，必须在 rationale 中引用日记原文中的具体词句作为评分依据。"
            if self._mode == "strict"
            else "快速整体判断即可，rationale 可简短。"
        )
        keys_schema = ", ".join(f'"{k}": <1-5 整数>' for k in self._rubric.keys)
        history_block = f"\n【历史上下文】\n{history}\n" if history else ""

        return (
            "你是一名严谨的中文生活助手回复质量评审（覆盖记录/规划/洞察复盘与情绪回应）。请根据评分量表，对 AI 回复在每个维度"
            "上打 1-5 的整数分（1=完全不符合，5=完美符合）。\n\n"
            "【评分量表】\n"
            f"{self._rubric.render()}\n\n"
            f"【评分要求】\n{evidence_rule}\n\n"
            f"【日记原文】\n{diary}\n{history_block}\n"
            f"【待评 AI 回复】\n{response}\n\n"
            "【输出格式】严格输出一个 JSON 对象，不要包含其他文字：\n"
            f'{{{keys_schema}, "rationale": "<评分理由>"}}'
        )

    def _parse(self, content: str) -> tuple[dict[str, float], str]:
        match = _JSON_BLOCK.search(content)
        if match is None:
            # Truncated output (the judge hit max_tokens mid-JSON, so there is no
            # closing brace). Recover whatever dimension scores are visible rather
            # than failing the whole eval run on one verbose case.
            scores = self._parse_scores_fallback(content)
            if scores:
                return scores, ""
            raise JudgeParseError(f"no JSON object in judge output: {content!r}")
        blob = match.group(0)
        data: dict[str, Any] | None = None
        try:
            data = json.loads(blob)
        except json.JSONDecodeError:
            scores = self._parse_scores_fallback(blob)
            if not scores:
                raise JudgeParseError(f"invalid JSON in judge output: {blob[:200]!r}...") from None
            return scores, ""

        scores: dict[str, float] = {}
        for key in self._rubric.keys:
            if key in data:
                scores[key] = _clamp_score(data[key])
        if not scores:
            scores = self._parse_scores_fallback(blob)
        if not scores:
            raise JudgeParseError(
                f"judge output had none of the rubric dimensions {self._rubric.keys}: {data}"
            )

        rationale = str(data.get("rationale", ""))
        return scores, rationale

    def _parse_scores_fallback(self, content: str) -> dict[str, float]:
        """Recover numeric dimension scores when the judge JSON is slightly malformed."""
        # Build the alternation from this judge's rubric keys so the fallback
        # works for any configured rubric (default companion rubric *and* the
        # plan rubric). Keys are regex-escaped to stay safe if one ever
        # contained meta-characters.
        keys_pattern = "|".join(re.escape(k) for k in self._rubric.keys)
        score_field = re.compile(rf'"(?P<key>{keys_pattern})"\s*:\s*(?P<val>\d+(?:\.\d+)?)')
        scores: dict[str, float] = {}
        for found in score_field.finditer(content):
            key = found.group("key")
            if key in self._rubric.keys:
                scores[key] = _clamp_score(found.group("val"))
        return scores


def _clamp_score(value: Any) -> float:
    try:
        score = float(value)
    except (TypeError, ValueError) as exc:
        raise JudgeParseError(f"non-numeric score: {value!r}") from exc
    return max(1.0, min(5.0, score))
