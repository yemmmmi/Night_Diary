"""Memory card API routes.

Cards are lightweight structured memory atoms. They bridge the gap
between "nothing" and a full diary entry. See :mod:`card_service` for
the business logic, including Card->Episodic and Card->Diary flows.
"""

from __future__ import annotations

import contextlib
from typing import Any

from fastapi import APIRouter, Query, Response, status

from app.api.deps import ContainerDep, CurrentUserDep, DbDep
from app.api.mappers import card_to_response
from app.api.schemas import (
    CardCreateRequest,
    CardExpandRequest,
    CardResponse,
    CardUpdateRequest,
)
from app.services import card_prompt_service, card_service

router = APIRouter(prefix="/cards", tags=["cards"])


# -- helpers ----------------------------------------------------------------


def _sync_card_to_chroma(
    row: Any,
    container: ContainerDep,
) -> None:
    if container.card_collection is not None:
        search_text = f"{row.emotion} {row.event_summary or ''}".strip()
        container.card_collection.upsert_card(
            row.card_id,
            search_text,
            emotion=row.emotion,
            tags=row.tags_json or "",
        )


# -- CRUD -------------------------------------------------------------------


@router.get("", response_model=list[CardResponse])
def list_cards(
    db: DbDep,
    user: CurrentUserDep,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    emotion: str | None = Query(None),
    card_type: str | None = Query(None),
    has_diary: bool | None = Query(None),
) -> list[dict[str, Any]]:
    rows = card_service.list_cards(
        db,
        user_id=str(user.id),
        skip=skip,
        limit=limit,
        emotion=emotion,
        card_type=card_type,
        has_diary=has_diary,
    )
    return [card_to_response(row) for row in rows]


@router.post("", response_model=CardResponse, status_code=status.HTTP_201_CREATED)
def create_card(
    body: CardCreateRequest,
    db: DbDep,
    user: CurrentUserDep,
    container: ContainerDep,
) -> dict[str, Any]:
    row = card_service.create_card(
        db,
        user_id=str(user.id),
        emotion=body.emotion,
        emotions=body.emotions,
        event_summary=body.event_summary,
        mood_score=body.mood_score,
        tags=body.tags,
        importance=body.importance,
        card_type=body.card_type,
    )
    # Ensure memory layers + card collection are ready (lazy on cold start)
    container.ensure_memory(user_id=str(user.id))
    # Sync to episodic memory pipeline (best-effort)
    card_service.sync_card_to_episodic(row, container.episodic_memory)
    # Sync to Chroma for semantic search (best-effort)
    _sync_card_to_chroma(row, container)
    return card_to_response(row)


@router.get("/{card_id}", response_model=CardResponse)
def get_card(card_id: str, db: DbDep, user: CurrentUserDep) -> dict[str, Any]:
    row = card_service.get_card(db, card_id, user_id=str(user.id))
    return card_to_response(row)


@router.put("/{card_id}", response_model=CardResponse)
def update_card(
    card_id: str,
    body: CardUpdateRequest,
    db: DbDep,
    user: CurrentUserDep,
    container: ContainerDep,
) -> dict[str, Any]:
    row = card_service.update_card(
        db,
        card_id,
        user_id=str(user.id),
        emotion=body.emotion,
        emotions=body.emotions,
        event_summary=body.event_summary,
        mood_score=body.mood_score,
        tags=body.tags,
        importance=body.importance,
    )
    container.ensure_memory(user_id=str(user.id))
    card_service.sync_card_to_episodic(row, container.episodic_memory)
    _sync_card_to_chroma(row, container)
    return card_to_response(row)


@router.delete(
    "/{card_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def delete_card(
    card_id: str,
    db: DbDep,
    user: CurrentUserDep,
    container: ContainerDep,
) -> Response:
    card_service.delete_card(db, card_id, user_id=str(user.id))
    container.ensure_memory(user_id=str(user.id))
    if container.card_collection is not None:
        container.card_collection.delete_card(card_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# -- Expand -----------------------------------------------------------------


@router.post("/{card_id}/expand", response_model=dict[str, Any])
def expand_card_to_diary(
    card_id: str,
    _body: CardExpandRequest,
    db: DbDep,
    user: CurrentUserDep,
    container: ContainerDep,
) -> dict[str, Any]:
    diary, analysis = card_service.expand_to_diary(
        db, card_id, user_id=str(user.id), container=container
    )

    if container.diary_collection is not None:
        with contextlib.suppress(Exception):
            container.diary_collection.update_diary(
                str(diary.id),
                diary.content or "",
                date=diary.date.isoformat() if diary.date else "",
                tags="",
            )

    result: dict[str, Any] = {
        "card_id": card_id,
        "diary_id": diary.id,
        "message": f"已展开为日记 #{diary.id}",
    }
    if analysis is not None:
        result["analysis_id"] = analysis.id
        result["auto_analyzed"] = True
    return result


# -- Stats ------------------------------------------------------------------


@router.get("/stats/summary", response_model=dict[str, Any])
def card_stats(db: DbDep, user: CurrentUserDep) -> dict[str, Any]:
    return card_service.get_card_stats(db, user_id=str(user.id))


@router.get("/stats/mood-trends", response_model=list[dict[str, Any]])
def mood_trends(
    db: DbDep,
    user: CurrentUserDep,
    days: int = Query(30, ge=7, le=365),
) -> list[dict[str, Any]]:
    return card_service.get_mood_trends(db, user_id=str(user.id), days=days)


# -- Guided prompt ----------------------------------------------------------


@router.post("/prompt", response_model=dict[str, Any])
def generate_prompt(
    db: DbDep,
    user: CurrentUserDep,
    container: ContainerDep,
) -> dict[str, Any]:
    """Generate 3 personalised guided questions for the card guided mode."""
    user_id = str(user.id)
    # Build context from recent data
    recent_cards = card_service.list_cards(db, user_id=user_id, skip=0, limit=10)
    cards_summary = "; ".join(
        f"{c.emotion}: {c.event_summary}" for c in recent_cards if c.event_summary
    )[:500]

    from app.services import diary_service

    recent_diaries = diary_service.get_recent_entries(db, user_id=user_id, days=7, limit=5)
    diary_summary = "; ".join((d.content or "")[:80] for d in recent_diaries)[:500]

    # Resolve LLM
    from app.services.ai.router import resolve_llm_clients_by_tier

    llm_map = resolve_llm_clients_by_tier(
        db,
        llm_factory=container.llm_factory,
        tracer=container.llm_tracer,
        prefer_active=True,
        user_id=user_id,
    )
    llm = llm_map.get("light") or llm_map.get("default")
    if llm is None:
        questions = card_prompt_service._fallback_questions()
    else:
        questions = card_prompt_service.generate_card_questions(
            llm,
            recent_cards_summary=cards_summary,
            recent_diary_summary=diary_summary,
            model=getattr(llm, "model", ""),
        )

    return {"questions": questions}


# -- Semantic search --------------------------------------------------------


@router.get("/search", response_model=dict[str, Any])
def search_cards(
    db: DbDep,
    user: CurrentUserDep,
    container: ContainerDep,
    q: str = Query(..., min_length=1, max_length=200),
    limit: int = Query(10, ge=1, le=50),
) -> dict[str, Any]:
    """Semantic search across memory cards using ChromaDB vector index."""
    container.ensure_memory(user_id=str(user.id))
    if container.card_collection is None:
        return {"results": [], "query": q}

    hits = container.card_collection.search(q, top_k=limit)
    results: list[dict[str, Any]] = []
    for hit in hits:
        card_id = hit.get("card_id", "")
        if not card_id:
            continue
        try:
            row = card_service.get_card(db, card_id, user_id=str(user.id))
            results.append(
                {
                    **card_to_response(row),
                    "_distance": round(hit.get("distance", 1.0), 4),
                }
            )
        except Exception:
            continue

    return {"query": q, "results": results}
