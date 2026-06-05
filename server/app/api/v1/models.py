"""LLM model provider API routes."""

from __future__ import annotations

from fastapi import APIRouter, Response, status

from app.api.deps import DbDep
from app.api.mappers import model_to_response
from app.api.schemas import ModelCreateRequest, ModelResponse, ModelUpdateRequest
from app.services import model_service

router = APIRouter(prefix="/models", tags=["models"])


@router.get("", response_model=list[ModelResponse])
def list_models(db: DbDep) -> list[ModelResponse]:
    rows = model_service.list_models(db)
    return [model_to_response(row) for row in rows]


@router.post("", response_model=ModelResponse, status_code=status.HTTP_201_CREATED)
def create_model(body: ModelCreateRequest, db: DbDep) -> ModelResponse:
    row = model_service.create_model(
        db,
        model_name=body.model_name,
        api_key=body.api_key,
        base_url=body.base_url,
        tier=body.tier,
        is_active=body.is_active,
    )
    return model_to_response(row)


@router.put("/{model_id}", response_model=ModelResponse)
def update_model(model_id: int, body: ModelUpdateRequest, db: DbDep) -> ModelResponse:
    row = model_service.update_model(
        db,
        model_id,
        model_name=body.model_name,
        api_key=body.api_key,
        base_url=body.base_url,
        tier=body.tier,
        is_active=body.is_active,
    )
    return model_to_response(row)


@router.delete("/{model_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_model(model_id: int, db: DbDep) -> Response:
    model_service.delete_model(db, model_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
