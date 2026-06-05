"""Chain mode — direct LLM generation without tools."""

from __future__ import annotations

from app.services.ai.prompts import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE
from app.services.ai.utils import extract_token_usage
from app.shared.llm import LLMClient, message_text


def run_chain(llm: LLMClient, context: dict[str, str]) -> tuple[str, dict[str, int], str]:
    prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        + USER_PROMPT_TEMPLATE.format(
            current_content=context["current_content"],
            tags_context=context["tags_context"],
            history_summary=context["history_summary"],
            weather_info=context["weather_info"],
        )
    )
    response = llm.invoke(prompt)
    token_info = extract_token_usage(response)
    result_text = message_text(response)
    thk_log = (
        f"[Chain] tokens={token_info['total_tokens']} "
        f"(cache_hit={token_info['cache_hit_tokens']}, "
        f"miss={token_info['cache_miss_tokens']}, "
        f"output={token_info['output_tokens']})"
    )
    return result_text, token_info, thk_log
