"""API Compliance Checker — enforces frozen public method contracts.

Usage:
    from .api_compliance import verify_frozen_methods, APIViolationError

    class MyEngine:
        API_VERSION = "2.0.0"
        FROZEN_PUBLIC_METHODS = frozenset({"run", "stop"})

    verify_frozen_methods(MyEngine)  # raises if any frozen method is missing
"""

from __future__ import annotations

import inspect
from typing import Set, Type


class APIViolationError(RuntimeError):
    """Raised when a frozen public method is missing from a class."""


def verify_frozen_methods(
    cls: Type,
    frozen_set: Set[str],
    version: str,
) -> None:
    """Verify that every name in *frozen_set* is a public method on *cls*.

    Raises ``APIViolationError`` if any frozen method is missing or has
    been removed.  This is meant to be called during import / startup so
    that violations are caught immediately.

    The check is intentionally strict — it does *not* inspect the method
    signature, only its existence.
    """
    missing = frozen_set - {
        name for name, _ in inspect.getmembers(cls, inspect.isfunction)
    }
    if missing:
        raise APIViolationError(
            f"[{cls.__name__}] API v{version} frozen methods missing: "
            f"{sorted(missing)}. "
            f"Either restore them or bump API_VERSION."
        )


def check_extra_public_methods(
    cls: Type,
    frozen_set: Set[str],
    version: str,
) -> None:
    """Warn about public methods that exist but are NOT in the frozen set.

    This is a softer check than *verify_frozen_methods* — it logs a
    warning rather than raising.  Every public method should eventually
    be accounted for in the frozen set or explicitly documented as
    unstable.
    """
    public = {
        name for name, _ in inspect.getmembers(cls, inspect.isfunction)
        if not name.startswith("_")
    }
    extra = public - frozen_set
    if extra:
        import logging
        logging.getLogger("emo_ai.api_compliance").warning(
            "[%s] API v%s — public methods not in frozen set: %s. "
            "Consider adding them or marking them private (prefix '_').",
            cls.__name__, version, sorted(extra),
        )
