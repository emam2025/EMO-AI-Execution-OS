"""Rollback Engine Protocol.

Defines the interface for rollback and containment operations.

Ref: P8.3 — Rollback & Containment
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Awaitable, Callable, List, Protocol

if TYPE_CHECKING:
    from core.models.rollback import RollbackAction, RollbackScope


class IRollbackEngine(Protocol):
    """Protocol for rollback and containment engine."""

    def register_handler(
        self,
        scope: RollbackScope,
        handler: Callable[[str, str], Awaitable[bool]],
    ) -> None: ...

    async def trigger_rollback(
        self, scope: RollbackScope, target_id: str, reason: str
    ) -> RollbackAction: ...

    def get_audit_log(self, target_id: str) -> List[RollbackAction]: ...
