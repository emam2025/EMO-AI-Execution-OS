"""Phase H1 — Computer Use Runtime.

Browser automation, desktop interaction, vision grounding, and session
journaling, all sandboxed through Phase 4 IsolationRuntime.

Ref: Canon LAW 10, LAW 12, LAW 24, RULE 1-4
Ref: artifacts/design/h1/
"""

from core.runtime.computer_use.browser_runtime import BrowserRuntime
from core.runtime.computer_use.desktop_worker import DesktopWorker
from core.runtime.computer_use.vision_grounding import VisionGrounding
from core.runtime.computer_use.session_journal import SessionJournal
from core.runtime.computer_use.session_state_machine import (
    ComputerUseSessionStateMachine,
    SessionState,
    InteractionGuardResult,
)
from core.runtime.computer_use.trace_correlator import ComputerUseTraceCorrelator

__all__ = [
    "BrowserRuntime",
    "DesktopWorker",
    "VisionGrounding",
    "SessionJournal",
    "ComputerUseSessionStateMachine",
    "ComputerUseTraceCorrelator",
    "SessionState",
    "InteractionGuardResult",
]
