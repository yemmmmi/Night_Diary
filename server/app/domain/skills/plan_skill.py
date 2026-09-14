"""Plan skill — turn a user request into a plan under one of three templates.

Templates (PR8):
- ``checkin_total`` — cumulative check-ins over N days (e.g. 坚持减肥30天)
- ``timer_daily``   — daily time goal in hours (e.g. 每天学习4小时)
- ``milestones``    — learning path whose nodes carry reference links
  (e.g. 学剪辑). Node links come **only** from web-search results — the LLM
  never fabricates URLs — and ``multi_source`` only records that one search
  returned candidates from at least two distinct domains.

The whole generation is capped at ``_MAX_SEARCH_QUERIES`` web queries; when
search is unavailable the nodes are still created from LLM knowledge with
``multi_source=false`` and no links.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any
from urllib.parse import urlparse

from sqlalchemy.orm import Session

from app.domain.skills.record_skill import SkillRunOutcome
from app.services import plan_service
from app.services.web_search_service import WebSearchResult, search_web
from app.shared.llm import LLMClient, message_text

logger = logging.getLogger(__name__)

_MAX_SEARCH_QUERIES = 5
_MAX_NODES = 12
_MIN_NODES = 3
_MAX_TITLE_LEN = 100
_MAX_NOTE_LEN = 200

_EXTRACT_PROMPT = """从用户输入中抽取计划参数，并判定属于哪种模板：

- checkin_total：有明确总天数目标的坚持类计划（如"坚持减肥30天""连续早起21天"）
- timer_daily：有每日时长目标的计划（如"每天学习4小时"）
- milestones：完成一个由浅入深的目标或课题（如"学习视频剪辑""准备秋招""备考考研""做个项目"），凡是要分阶段推进的事都算
- none：用户其实不是想做计划

只输出一个 JSON 对象，不要任何其他文字：
{{"template": "checkin_total|timer_daily|milestones|none", "title": "简短计划名，20字以内", "motivation": "用户动机一句话，没有就留空", "days": 30, "daily_hours": 4, "topic": "要推进的目标主题"}}

字段说明：days 仅 checkin_total 需要；daily_hours 仅 timer_daily 需要；topic 仅 milestones 需要。

用户输入：{content}
"""

_MILESTONE_PROMPT = """为「{topic}」设计一个由浅入深、分阶段推进的计划。只输出一个 JSON 对象，不要任何其他文字：
{{"tasks": [{{"title": "节点名，15字以内", "note": "这个节点做什么、达成什么，40字以内"}}]}}

要求：{min_nodes} 到 {max_nodes} 个节点，从起步到能独立完成目标；每个节点独立、可检验、顺序递进。
"""


def _parse_json_dict(text: str) -> dict[str, Any]:
    """Parse a JSON object from an LLM reply, tolerating markdown fences."""
    text = text.strip()
    if text.startswith("```"):
        lines = text.split("\n")
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    try:
        parsed = json.loads(text)
        if isinstance(parsed, dict):
            return parsed
    except json.JSONDecodeError:
        pass
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            parsed = json.loads(match.group(0))
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    return {}


def _clamp_number(value: Any, low: float, high: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return low
    return max(low, min(high, number))


def _find_multi_source_link(results: list[WebSearchResult]) -> tuple[str | None, bool]:
    """Select a primary result and report whether multiple domains appeared.

    ``multi_source`` is a provenance signal only. It does not assert that the
    candidates agree or that any claim has been established as fact.
    """
    ranked = _rank_sources(results, "")
    if not ranked:
        return None, False
    primary = ranked[0]
    return primary["url"], primary["multi_source"]


def _rank_sources(
    results: list[WebSearchResult], topic: str
) -> list[dict[str, Any]]:
    """Deduplicate + rank web results for a node into a provenance list.

    - One entry per distinct registered domain (first-URL wins per domain).
    - ``multi_source`` is True when the same query returned candidates from
      ≥2 distinct domains; ``is_primary`` marks the single main reference
      that becomes ``tasks.link``.
    - Ordering: multi-source-first, then by relevance hints (topic term presence
      in title, then title length) for a deterministic, auditable ranking.
    """
    by_domain: dict[str, WebSearchResult] = {}
    for r in results:
        domain = urlparse(r.url).netloc.lower().removeprefix("www.")
        if domain and domain not in by_domain:
            by_domain[domain] = r

    itemized: list[dict[str, Any]] = []
    for domain, r in by_domain.items():
        title_terms = sum(1 for t in topic.split() if t and t in r.title)
        itemized.append(
            {
                "url": r.url,
                "title": r.title,
                "snippet": r.snippet,
                "domain": domain,
                "multi_source": False,
                "is_primary": False,
                "_relevance": (title_terms, -len(r.title)),
            }
        )

    # Provenance only: multiple domains appeared in the same result set.
    has_multi_domain = len(by_domain) >= 2
    if has_multi_domain:
        for item in itemized:
            item["multi_source"] = True
    itemized.sort(key=lambda i: (not i["multi_source"], i["_relevance"]))

    for item in itemized:
        item.pop("_relevance", None)
    if itemized:
        itemized[0]["is_primary"] = True
    return itemized


def _attach_node_links(
    topic: str, nodes: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Search reference links for nodes under the query budget.

    Attaches ``search_query`` and the full ranked ``source_links`` provenance
    list to each node, so the frontend can surface *how* the plan was built.
    """
    from app.services import web_search_service

    queries_left = _MAX_SEARCH_QUERIES
    for node in nodes:
        if queries_left <= 0 or not web_search_service.web_search_available():
            break
        query = f"{topic} {node['title']} 教程 入门"
        results = search_web(query, max_results=5)
        queries_left -= 1
        ranked = _rank_sources(results, topic)
        node["search_query"] = query
        if ranked:
            node["source_links"] = ranked
            node["link"] = ranked[0]["url"]
            node["multi_source"] = ranked[0]["multi_source"]
    return nodes


def research_node(topic: str, title: str) -> dict[str, Any]:
    """Search again for a single milestone node and return its provenance.

    Used by PR D ("补充依据") to backfill source_links on legacy nodes that
    were created without web evidence. Respects one search per call (the
    caller bounds how many nodes it drills within a single operation).
    """
    from app.services import web_search_service

    query = f"{topic} {title} 教程 入门"
    if not web_search_service.web_search_available():
        return {"search_query": query, "source_links": []}
    results = search_web(query, max_results=5)
    ranked = _rank_sources(results, topic)
    provenance: dict[str, Any] = {"search_query": query, "source_links": ranked}
    if ranked:
        provenance["link"] = ranked[0]["url"]
        provenance["multi_source"] = ranked[0]["multi_source"]
    return provenance


def _generate_milestone_nodes(
    llm: LLMClient, topic: str
) -> list[dict[str, Any]]:
    response = llm.invoke(
        _MILESTONE_PROMPT.format(
            topic=topic, min_nodes=_MIN_NODES, max_nodes=_MAX_NODES
        )
    )
    parsed = _parse_json_dict(message_text(response))
    raw_tasks = parsed.get("tasks")
    if not isinstance(raw_tasks, list):
        return []
    nodes: list[dict[str, Any]] = []
    for item in raw_tasks[:_MAX_NODES]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title", "")).strip()[:_MAX_TITLE_LEN]
        note = str(item.get("note", "")).strip()[:_MAX_NOTE_LEN]
        if title:
            nodes.append({"title": title, "note": note})
    return nodes


def run(
    db: Session,
    *,
    llm: LLMClient | None,
    content: str,
    user_id: str,
    conversation_id: str = "",
) -> SkillRunOutcome | None:
    """Create a plan from *content*; None → fall back to normal chat."""
    if llm is None:
        return None

    try:
        response = llm.invoke(_EXTRACT_PROMPT.format(content=content[:1000]))
        params = _parse_json_dict(message_text(response))
    except Exception as exc:
        logger.warning("plan skill extraction failed: %s", exc)
        return None

    template = params.get("template")
    title = str(params.get("title", "")).strip()[:_MAX_TITLE_LEN]
    motivation = str(params.get("motivation", "")).strip() or None
    if template not in ("checkin_total", "timer_daily", "milestones") or not title:
        return None

    target_value: float | None = None
    target_unit: str | None = None
    target_period: str | None = None
    nodes: list[dict[str, Any]] = []

    if template == "checkin_total":
        target_value = _clamp_number(params.get("days"), 1, 365)
        target_unit = "天"
        target_period = "total"
    elif template == "timer_daily":
        target_value = _clamp_number(params.get("daily_hours"), 0.5, 16)
        target_unit = "小时"
        target_period = "daily"
    else:
        topic = str(params.get("topic", "")).strip() or title
        nodes = _generate_milestone_nodes(llm, topic)
        if len(nodes) < _MIN_NODES:
            logger.warning("plan skill: too few milestone nodes (%d), abort", len(nodes))
            return None
        nodes = _attach_node_links(topic, nodes)

    plan = plan_service.create_plan(
        db,
        user_id=user_id,
        title=title,
        motivation=motivation,
        source="agent",
        created_from_conversation_id=conversation_id or None,
        target_value=target_value,
        target_unit=target_unit,
        target_period=target_period,
        template=template,
    )

    task_results: list[dict[str, Any]] = []
    for node in nodes:
        task = plan_service.create_task(
            db,
            user_id=user_id,
            plan_id=plan.id,
            title=node["title"],
            note=node.get("note") or None,
            link=node.get("link"),
            source_links=node.get("source_links"),
            source="agent",
            created_from_conversation_id=conversation_id or None,
        )
        task_results.append(
            {
                "id": task.id,
                "title": task.title,
                "note": task.note or "",
                "link": task.link,
                "multi_source": bool(node.get("multi_source")),
            }
        )

    logger.info(
        "plan skill: plan_id=%s template=%s nodes=%d user=%s",
        plan.id,
        template,
        len(task_results),
        user_id,
    )

    if template == "checkin_total":
        days = int(target_value or 0)
        reply_text = f"已为你创建计划「{title}」：坚持 {days} 天，每天打卡一次即可累计进度。"
    elif template == "timer_daily":
        hours = float(target_value or 0)
        formatted = int(hours) if hours == int(hours) else hours
        reply_text = (
            f"已为你创建计划「{title}」：每天累计 {formatted} 小时，"
            "点击打卡开始计时，达到目标会自动提示完成。"
        )
    else:
        multi_source_count = sum(1 for t in task_results if t["multi_source"])
        reply_text = (
            f"已为你创建学习计划「{title}」，共 {len(task_results)} 个节点，"
            f"其中 {multi_source_count} 个节点附有多来源候选，"
            "进入计划页即可按节点推进。"
        )

    return SkillRunOutcome(
        skill="plan",
        reply_text=reply_text,
        skill_result={
            "skill": "plan",
            "plan_id": plan.id,
            "template": template,
            "title": title,
            "target_value": target_value,
            "target_unit": target_unit,
            "tasks": task_results,
        },
    )
