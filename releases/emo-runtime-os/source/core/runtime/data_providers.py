"""Data providers for router access to core.db and core.state.

Routers MUST NOT import from core.db or core.state directly (enforced by
router_isolation_check.py AST gate).  Instead they import from this module:

    from core.runtime.data_providers import get_db, get_state

LAW 13: All cross-boundary access flows through core.runtime.*.
"""

from __future__ import annotations

from typing import Any

from core.db import Database, db as _db
from core.state import AppState, state as _state


def get_db() -> Database:
    """Return the singleton Database instance (core.db.db)."""
    return _db


def get_state() -> AppState:
    """Return the singleton AppState instance (core.state.state)."""
    return _state
