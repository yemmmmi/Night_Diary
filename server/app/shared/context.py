"""Request-scoped user context for multi-tenant data isolation.

``UserContext`` bundles the DB session, the string-form ``user_id`` (matching
the ``VARCHAR(64)`` column on user-scoped tables), and the ``UserRow`` ORM
object.  Inject it via ``UserContextDep`` in route signatures that need both
database access and user-scoped filtering.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.infrastructure.models.user import UserRow


@dataclass
class UserContext:
    """Bundles DB session + authenticated user for service-layer calls."""

    db: Session
    user_id: str
    user: UserRow
