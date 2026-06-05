"""FastAPI dependencies for the API layer."""

from __future__ import annotations

from collections.abc import Generator
from typing import Annotated, cast

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.services.container import ServiceContainer


def get_container(request: Request) -> ServiceContainer:
    return cast(ServiceContainer, request.app.state.container)


def get_db(
    container: Annotated[ServiceContainer, Depends(get_container)],
) -> Generator[Session, None, None]:
    session = container.session()
    try:
        yield session
    finally:
        session.close()


ContainerDep = Annotated[ServiceContainer, Depends(get_container)]
DbDep = Annotated[Session, Depends(get_db)]
