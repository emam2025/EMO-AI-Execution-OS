"""Phase H1 — Computer Use Runtime Session & Action Models.  # LAW-10 LAW-12 LAW-24 RULE-1 RULE-2 RULE-3

Shared dataclasses and enums for all H1 components: BrowserRuntime,
DesktopWorker, VisionGrounding, and SessionJournal.

Ref: Canon LAW 10 (Unreliable Workers — isolation)
Ref: Canon LAW 12 (Traceability — session_trace_id)
Ref: Canon LAW 24 (Dispatcher Ownership — all actions dispatched)
Ref: Canon RULE 1 (Determinism), RULE 2 (No Uncontrolled IO)
Ref: Canon RULE 3 (Safety Guards), RULE 4 (Isolation)
Ref: ROADMAP Phase H — Computer Use Runtime
Ref: DEVELOPER.md §15.2, §15.15b
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional


# ── Enums ────────────────────────────────────────────────────────────────────


class WorkerType(str, Enum):
    BROWSER = "browser"
    DESKTOP = "desktop"
    VISION = "vision"


class SessionState(str, Enum):  # LAW-10 RULE-4
    INIT = "init"
    READY = "ready"
    INTERACTING = "interacting"
    PAUSED = "paused"
    CHECKPOINTED = "checkpointed"
    TERMINATED = "terminated"


class ActionType(str, Enum):  # LAW-24
    NAVIGATE = "navigate"
    CLICK = "click"
    TYPE_TEXT = "type_text"
    EXECUTE_SCRIPT = "execute_script"
    SCREENSHOT = "screenshot"
    DETECT_ELEMENT = "detect_element"
    EXTRACT_TEXT = "extract_text"
    CHECKPOINT = "checkpoint"
    REPLAY = "replay"
    ROLLBACK = "rollback"


class InteractionGuardStatus(str, Enum):  # RULE-3
    PASSED = "passed"
    BLOCKED_SELECTOR = "blocked_selector"
    BLOCKED_SPATIAL = "blocked_spatial"
    BLOCKED_CAPABILITY = "blocked_capability"
    BLOCKED_SANDBOX = "blocked_sandbox"


class JournalEntryType(str, Enum):  # RULE-1
    ACTION = "action"
    CHECKPOINT = "checkpoint"
    REPLAY = "replay"
    ROLLBACK = "rollback"
    DEVIATION = "deviation"


class VisualGroundingMethod(str, Enum):
    OCR = "ocr"
    TEMPLATE_MATCH = "template_match"
    A11Y_TREE = "a11y_tree"
    DOM_SELECTOR = "dom_selector"
    HYBRID = "hybrid"


class CapabilityFlag(str, Enum):  # LAW-10 RULE-2
    NAVIGATE = "navigate"
    DOM_READ = "dom_read"
    SCRIPT_EXEC = "script_exec"
    POINTER_INPUT = "pointer_input"
    KEYBOARD_INPUT = "keyboard_input"
    SCREENSHOT = "screenshot"
    OCR = "ocr"
    TEMPLATE_MATCH = "template_match"
    FILE_DIALOG = "file_dialog"
    CLIPBOARD = "clipboard"


# ── Dataclasses ──────────────────────────────────────────────────────────────


@dataclass
class ComputerSession:  # LAW-10 LAW-12 RULE-4
    """Represents an isolated computer use session.

    Every session carries a session_trace_id (LAW 12) for observability
    and an isolation_context (LAW 10) for sandbox boundaries.
    """

    session_id: str = ""
    session_trace_id: str = ""  # LAW 12: traceability across all layers
    worker_type: WorkerType = WorkerType.BROWSER
    isolation_context: Dict[str, Any] = field(default_factory=lambda: {
        "sandbox_id": "",
        "network_policy": {"allowlist": [], "blocklist": []},
        "filesystem_policy": {"read_paths": [], "write_paths": []},
        "capability_guard_token": "",
    })  # LAW 10: every session has isolation context
    capabilities: List[str] = field(default_factory=list)  # RULE 2: declared capabilities
    resource_limits: Dict[str, float] = field(default_factory=lambda: {
        "max_cpu_sec": 120.0,
        "max_memory_mb": 512.0,
        "max_session_sec": 3600.0,
        "max_actions": 1000,
    })
    state: SessionState = SessionState.INIT
    state_hash: str = ""  # RULE 1: deterministic state hash
    worker_pid: int = 0
    sandbox_token: str = ""
    parent_mission_id: str = ""  # Link to G5 Swarm mission
    created_at_ns: int = 0
    last_active_ns: int = 0
    action_count: int = 0


@dataclass
class ActionPayload:  # LAW-24 RULE-1 RULE-2
    """Complete record of a single user/agent action.

    Every action carries all context needed for deterministic replay,
    capability verification, and audit.
    """

    action_type: str = ""
    target_selector: str = ""  # CSS/XPath/A11y selector
    input_data: str = ""  # Typed text, script code, etc.
    coordinates: Optional[Dict[str, int]] = None  # [x, y] for clicks
    modifiers: List[str] = field(default_factory=list)  # Key modifiers
    timestamp: int = 0  # Epoch nanosecond
    visual_context_hash: str = ""  # Hash of pre-action screenshot region
    session_id: str = ""
    session_trace_id: str = ""
    sandbox_token: str = ""  # RULE 2: capability gate
    sequence_number: int = 0
    guard_status: InteractionGuardStatus = InteractionGuardStatus.PASSED  # RULE 3
    duration_ms: float = 0.0
    error: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class VisualGroundingReport:  # RULE-1 RULE-3
    """Result of a visual grounding operation.

    Carries the detected element, spatial context, and any state changes
    observed in the grounded region.
    """

    detected_element: Optional[Dict[str, Any]] = None  # selector, bbox, role, text
    confidence_score: float = 0.0  # [0.0, 1.0]
    bounding_box: Optional[List[float]] = None  # [x, y, w, h]
    ocr_text: str = ""
    method: VisualGroundingMethod = VisualGroundingMethod.HYBRID  # RULE 1
    state_changes: List[Dict[str, Any]] = field(default_factory=list)
    grounding_hash: str = ""  # RULE 1: deterministic hash
    session_trace_id: str = ""
    is_safe: bool = True  # RULE 3: safety check
    blocked_reason: str = ""


@dataclass
class JournalEntry:  # LAW-24 RULE-1
    """A single entry in the session journal."""

    entry_id: str = ""
    session_id: str = ""
    entry_type: JournalEntryType = JournalEntryType.ACTION
    sequence_number: int = 0
    action_payload: Optional[ActionPayload] = None
    checkpoint_snapshot: Optional[Dict[str, Any]] = None
    state_hash: str = ""  # Cumulative state hash
    previous_entry_hash: str = ""  # Chain link for integrity
    recorded_at_ns: int = 0
    session_trace_id: str = ""
    deviation: Optional[Dict[str, Any]] = None


@dataclass
class SandboxProfile:  # Phase 4 Sandbox integration
    sandbox_id: str = ""
    network_policy: Dict[str, Any] = field(default_factory=lambda: {
        "allowed_domains": [],
        "blocked_domains": [],
        "allow_websocket": False,
        "max_connections": 4,
    })
    filesystem_policy: Dict[str, Any] = field(default_factory=lambda: {
        "allowed_read_paths": [],
        "allowed_write_paths": [],
        "blocked_paths": ["/etc", "/proc", "/sys"],
        "max_disk_bytes": 104857600,
    })
    capability_guard: Dict[str, bool] = field(default_factory=lambda: {
        "can_navigate": True,
        "can_execute_script": False,
        "can_access_clipboard": False,
        "can_open_file_dialog": False,
        "can_screenshot": True,
        "can_input_text": True,
        "can_click": True,
    })
    resource_quota: Dict[str, float] = field(default_factory=lambda: {
        "max_cpu_sec": 120.0,
        "max_memory_mb": 512.0,
        "max_network_mb": 50.0,
        "max_session_sec": 3600.0,
    })
    isolation_token: str = ""


@dataclass
class SessionReplayManifest:  # RULE-1
    """Manifest describing a replay operation from the journal."""

    manifest_id: str = ""
    session_id: str = ""
    source_checkpoint_id: str = ""
    target_state_hash: str = ""
    actions_to_replay: List[str] = field(default_factory=list)  # entry_ids
    expected_state_chain: List[str] = field(default_factory=list)  # hashes
    determinism_threshold: float = 0.95  # RULE 1: allowed deviation
    started_at_ns: int = 0
    completed_at_ns: int = 0
    deviation_found: bool = False
    deviation_detail: str = ""


@dataclass
class CapabilityViolationReport:  # RULE-2 RULE-3
    """Report generated when a capability guard blocks an action."""

    violation_id: str = ""
    session_id: str = ""
    action_type: str = ""
    missing_capability: str = ""
    attempted_operation: str = ""
    sandbox_token_provided: str = ""
    sandbox_token_required: str = ""
    blocked_at_ns: int = 0
    severity: str = "medium"  # low, medium, high, critical
    resolution: str = ""  # "retry_with_capability", "escalate", "terminate"
