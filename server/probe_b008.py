from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import Query


def p_annotated(p: Annotated[date | None, Query()] = None) -> None: ...
