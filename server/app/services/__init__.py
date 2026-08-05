"""Service layer — business orchestration between API routes and domain.

Modules are imported lazily on first use.  Do NOT add eager imports here —
the previous ``from app.services import (analysis_service, ...)`` pattern
pulled in the entire AI stack (langchain, torch) at startup, adding ~15s
before ``/ready`` was available.  Each consumer should import only the
specific submodule it needs (``from app.services import diary_service``)
so that heavy transitive deps load on demand.
"""
