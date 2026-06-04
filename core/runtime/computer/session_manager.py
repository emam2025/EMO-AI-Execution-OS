"""SessionManager — Computer session lifecycle + resource isolation.

State machine: IDLE → ACTIVE → PAUSED → REPLAYING → PAUSED → TERMINATED
Each transition is guarded and recorded via EventStore.

LAW 3: Lease-aware — every session acquires a lease before activation.
LAW 5: All transitions are observable via EventStore.
LAW 8: Every session is recoverable (paused → active or replay).
LAW 10: External workers are unreliable — sessions run in isolation.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class SessionState(Enum):
    IDLE = "IDLE"
    ACTIVE = "ACTIVE"
    PAUSED = "PAUSED"
    REPLAYING = "REPLAYING"
    TERMINATED = "TERMINATED"


_VALID_TRANSITIONS: Dict[SessionState, set[SessionState]] = {
    SessionState.IDLE: {SessionState.ACTIVE, SessionState.TERMINATED},
    SessionState.ACTIVE: {SessionState.PAUSED, SessionState.TERMINATED},
    SessionState.PAUSED: {SessionState.ACTIVE, SessionState.REPLAYING, SessionState.TERMINATED},
    SessionState.REPLAYING: {SessionState.PAUSED, SessionState.TERMINATED},
    SessionState.TERMINATED: set(),
}


@dataclass
class ComputerSession:
    """A single computer interaction session."""

    session_id: str
    state: SessionState = SessionState.IDLE
    lease_id: Optional[str] = None
    worker_type: Optional[str] = None
    resource_handle: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    metadata: Dict[str, Any] = field(default_factory=dict)


class SessionManager:
    """Manages the lifecycle of computer interaction sessions.

    Each session is isolated, lease-protected, and fully state-machine
    guarded. No resource leaks between sessions.
    """

    def __init__(self, event_bus: Any = None, lease_manager: Any = None) -> None:
        self._event_bus = event_bus
        self._lease_manager = lease_manager
        self._sessions: Dict[str, ComputerSession] = {}

    def create_session(self, worker_type: str = "browser", metadata: Optional[Dict[str, Any]] = None) -> ComputerSession:
        """Create a new computer session in IDLE state.

        Args:
            worker_type: Type of worker ('browser', 'desktop', 'vision').
            metadata: Optional session metadata.

        Returns:
            A new ComputerSession in IDLE state.
        """
        session = ComputerSession(
            session_id=uuid.uuid4().hex[:16],
            worker_type=worker_type,
            metadata=metadata or {},
        )
        self._sessions[session.session_id] = session
        self._emit_event("session.created", {"session_id": session.session_id, "worker_type": worker_type})
        return session

    def activate_session(self, session_id: str) -> ComputerSession:
        """Transition session from IDLE to ACTIVE.

        Acquires a lease before activation (LAW 3).
        """
        session = self._get_session(session_id)
        self._guard_transition(session, SessionState.ACTIVE)

        if self._lease_manager is not None:
            lease = self._lease_manager.acquire_lease(
                resource_type=f"computer.{session.worker_type}",
                owner=f"session.{session_id}",
            )
            session.lease_id = getattr(lease, "lease_id", None) or str(uuid.uuid4())

        session.state = SessionState.ACTIVE
        self._emit_event("session.activated", {"session_id": session_id})
        return session

    def pause_session(self, session_id: str) -> ComputerSession:
        """Transition session from ACTIVE to PAUSED.

        Safe suspension — session can be resumed or replayed.
        """
        session = self._get_session(session_id)
        self._guard_transition(session, SessionState.PAUSED)
        session.state = SessionState.PAUSED
        self._emit_event("session.paused", {"session_id": session_id})
        return session

    def resume_session(self, session_id: str) -> ComputerSession:
        """Transition session from PAUSED to ACTIVE.

        Restores the session to active state without replay.
        """
        session = self._get_session(session_id)
        self._guard_transition(session, SessionState.ACTIVE)
        session.state = SessionState.ACTIVE
        self._emit_event("session.resumed", {"session_id": session_id})
        return session

    def start_replay(self, session_id: str) -> ComputerSession:
        """Transition session from PAUSED to REPLAYING.

        Replay mode replays actions from an ActionJournal.
        """
        session = self._get_session(session_id)
        self._guard_transition(session, SessionState.REPLAYING)
        session.state = SessionState.REPLAYING
        self._emit_event("session.replay_started", {"session_id": session_id})
        return session

    def end_replay(self, session_id: str) -> ComputerSession:
        """Transition session from REPLAYING to PAUSED.

        Replay complete — return to paused for inspection.
        """
        session = self._get_session(session_id)
        self._guard_transition(session, SessionState.PAUSED)
        session.state = SessionState.PAUSED
        self._emit_event("session.replay_ended", {"session_id": session_id})
        return session

    def terminate_session(self, session_id: str) -> None:
        """Terminate session from any non-terminal state.

        Releases lease and cleans up resources.
        """
        session = self._get_session(session_id)
        self._guard_transition(session, SessionState.TERMINATED)

        if self._lease_manager is not None and session.lease_id:
            self._lease_manager.release_lease(session.lease_id)

        session.state = SessionState.TERMINATED
        session.resource_handle = None
        self._emit_event("session.terminated", {"session_id": session_id})

    def get_session(self, session_id: str) -> Optional[ComputerSession]:
        """Get a session by ID, or None."""
        return self._sessions.get(session_id)

    def list_sessions(self, state: Optional[SessionState] = None) -> List[ComputerSession]:
        """List all sessions, optionally filtered by state."""
        if state is None:
            return list(self._sessions.values())
        return [s for s in self._sessions.values() if s.state == state]

    def active_session_count(self) -> int:
        """Number of currently active sessions."""
        return len([s for s in self._sessions.values() if s.state == SessionState.ACTIVE])

    def _get_session(self, session_id: str) -> ComputerSession:
        if session_id not in self._sessions:
            raise ValueError(f"Session not found: {session_id}")
        return self._sessions[session_id]

    def _guard_transition(self, session: ComputerSession, target: SessionState) -> None:
        allowed = _VALID_TRANSITIONS.get(session.state, set())
        if target not in allowed:
            raise ValueError(
                f"Invalid transition: {session.state.value} → {target.value} "
                f"(session={session.session_id})"
            )

    def _emit_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        if self._event_bus is not None:
            self._event_bus.publish(f"computer.{event_type}", payload)
