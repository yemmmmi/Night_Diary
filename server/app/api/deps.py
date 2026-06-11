"""FastAPI dependencies for the API layer."""

from __future__ import annotations

from collections.abc import Generator
from typing import Annotated, cast

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.services.container import ServiceContainer
from app.shared.errors import BootstrapNotReadyError


def get_container(request: Request) -> ServiceContainer:
    if not getattr(request.app.state, "bootstrap_done", False):
        raise BootstrapNotReadyError()
    container = request.app.state.container
    if container is None:
        raise BootstrapNotReadyError()
    return cast(ServiceContainer, container)


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
