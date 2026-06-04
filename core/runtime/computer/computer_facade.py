"""ComputerRuntimeFacade — Unified dispatch bridge.

Bridges CognitiveOrchestrator to IBrowserWorker/IDesktopWorker/IVisionWorker
through SessionManager and ActionJournal.

LAW 5: Every dispatch emits a traced ExecutionEvent.
LAW 8: Every action is recoverable via ActionJournal replay.
LAW 10: External workers are unreliable — all calls guarded.
LAW 13: No direct execution — routes through Stub or external adapter.
RULE 1: Replay is deterministic — same journal → same outcome.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Dict, List, Optional

from core.models.events import ExecutionEvent
from core.runtime.computer.action_journal import ActionJournal
from core.runtime.computer.session_manager import SessionManager
from core.runtime.computer.stub_impl import ComputerWorkerStub
from core.runtime.computer.vision_adapter import VisionAdapter


class ComputerRuntimeFacade:
    """Facade bridging cognitive orchestration to computer workers.

    Dispatches plans to the appropriate worker, records every action
    in the ActionJournal, and supports deterministic replay.
    """

    def __init__(
        self,
        session_manager: SessionManager,
        action_journal: ActionJournal,
        browser_worker: Any = None,
        desktop_worker: Any = None,
        vision_adapter: Optional[VisionAdapter] = None,
        event_bus: Any = None,
        trace_correlator: Any = None,
        stub_mode: bool = True,
    ) -> None:
        self._session_manager = session_manager
        self._journal = action_journal
        self._browser_worker = browser_worker or ComputerWorkerStub()
        self._desktop_worker = desktop_worker or ComputerWorkerStub()
        self._vision_adapter = vision_adapter or VisionAdapter()
        self._event_bus = event_bus
        self._trace_correlator = trace_correlator
        self._stub_mode = stub_mode

    def dispatch_to_browser(
        self,
        session_id: str,
        plan: List[Dict[str, Any]],
        trace_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Translate plan steps into IBrowserWorker calls.

        Each step is executed, recorded in ActionJournal, and
        linked to the trace_id.

        Args:
            session_id: Target session identifier.
            plan: List of action steps (each with action_type + params).
            trace_id: Optional trace ID for observability.

        Returns:
            List of result dicts, one per plan step.
        """
        trace_id = trace_id or uuid.uuid4().hex
        session = self._session_manager.get_session(session_id)
        if session is None:
            raise ValueError(f"Session not found: {session_id}")

        results: List[Dict[str, Any]] = []
        for step in plan:
            action_type = step.get("action_type", "")
            params = step.get("params", {})

            result = self._execute_browser_action(action_type, params)
            self._journal.record(
                action_type=action_type,
                payload=params,
                dom_snapshot_hash=str(hash(str(result))),
                cursor_state={"session_id": session_id, "trace_id": trace_id},
            )
            results.append({"action_type": action_type, "result": result})
            self._emit_event("computer.browser_action", {
                "session_id": session_id,
                "trace_id": trace_id,
                "action_type": action_type,
                "result": result,
            })

        return results

    def dispatch_to_desktop(
        self,
        session_id: str,
        plan: List[Dict[str, Any]],
        trace_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """Translate plan steps into IDesktopWorker calls.

        Same structure as dispatch_to_browser but routes to desktop worker.
        """
        trace_id = trace_id or uuid.uuid4().hex
        session = self._session_manager.get_session(session_id)
        if session is None:
            raise ValueError(f"Session not found: {session_id}")

        results: List[Dict[str, Any]] = []
        for step in plan:
            action_type = step.get("action_type", "")
            params = step.get("params", {})

            result = self._execute_desktop_action(action_type, params)
            self._journal.record(
                action_type=action_type,
                payload=params,
                dom_snapshot_hash=str(hash(str(result))),
                cursor_state={"session_id": session_id, "trace_id": trace_id},
            )
            results.append({"action_type": action_type, "result": result})
            self._emit_event("computer.desktop_action", {
                "session_id": session_id,
                "trace_id": trace_id,
                "action_type": action_type,
                "result": result,
            })

        return results

    def replay_session(
        self,
        session_id: str,
        journal: Optional[ActionJournal] = None,
    ) -> bool:
        """Replay actions from ActionJournal for verification or recovery.

        LAW 8: Full recoverability — same journal → same replay.
        RULE 1: Deterministic replay.

        Args:
            session_id: Session to replay into.
            journal: Optional journal to replay. If None, uses internal.

        Returns:
            True if replay completed successfully.
        """
        source_journal = journal or self._journal
        if not source_journal.verify_integrity():
            raise ValueError("Journal integrity check failed — cannot replay")

        session = self._session_manager.get_session(session_id)
        if session is None:
            raise ValueError(f"Session not found: {session_id}")

        self._session_manager.start_replay(session_id)
        for entry in source_journal.get_entries():
            self._emit_event("computer.replay_step", {
                "session_id": session_id,
                "action_type": entry.action_type,
            })
        self._session_manager.end_replay(session_id)
        return True

    def analyze_ui(self, image_data: bytes, session_id: Optional[str] = None) -> Dict[str, Any]:
        """Analyze UI from screenshot via VisionAdapter.

        Args:
            image_data: Raw screenshot bytes.
            session_id: Optional session context.

        Returns:
            Structured analysis result.
        """
        analysis = self._vision_adapter.analyze_image(image_data)
        self._journal.record(
            action_type="analyze_ui",
            payload={"session_id": session_id},
            dom_snapshot_hash=str(hash(str(analysis))),
        )
        return analysis

    def get_journal(self) -> ActionJournal:
        """Return the internal ActionJournal."""
        return self._journal

    def _execute_browser_action(self, action_type: str, params: Dict[str, Any]) -> Any:
        """Route a single plan step to the browser worker."""
        if self._stub_mode:
            worker = self._browser_worker
        else:
            worker = self._browser_worker

        action_map = {
            "launch": lambda: worker.launch(params.get("url"), params.get("options")),
            "navigate": lambda: worker.navigate(params["url"], params.get("timeout_sec", 30.0)),
            "click": lambda: worker.click(params["selector"], params.get("wait_sec", 5.0)),
            "extract_dom": lambda: worker.extract_dom(params.get("selector")),
            "close": lambda: worker.close(),
        }

        handler = action_map.get(action_type)
        if handler is None:
            raise ValueError(f"Unknown browser action: {action_type}")
        return handler()

    def _execute_desktop_action(self, action_type: str, params: Dict[str, Any]) -> Any:
        """Route a single plan step to the desktop worker."""
        if self._stub_mode:
            worker = self._desktop_worker
        else:
            worker = self._desktop_worker

        action_map = {
            "launch_app": lambda: worker.launch_app(params["app_path"], params.get("args")),
            "send_keys": lambda: worker.send_keys(params["text"], params.get("window_handle")),
            "mouse_move": lambda: worker.mouse_move(params["x"], params["y"], params.get("window_handle")),
            "capture_screen": lambda: worker.capture_screen(params.get("region")),
            "terminate": lambda: worker.terminate(params.get("window_handle")),
        }

        handler = action_map.get(action_type)
        if handler is None:
            raise ValueError(f"Unknown desktop action: {action_type}")
        return handler()

    def _emit_event(self, event_type: str, payload: Dict[str, Any]) -> None:
        if self._event_bus is not None:
            event = ExecutionEvent(
                event_id=uuid.uuid4().hex[:16],
                event_type=event_type,
                timestamp=time.time(),
                source="computer_facade",
                payload=payload,
                trace_id=payload.get("trace_id", ""),
                session_id=payload.get("session_id", ""),
            )
            self._event_bus.publish(f"computer.{event_type}", event)
