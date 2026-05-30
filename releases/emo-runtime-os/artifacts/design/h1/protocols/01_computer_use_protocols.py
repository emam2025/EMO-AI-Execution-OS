"""Phase H1 — Computer Use Runtime Protocols.  # LAW-2 LAW-10 LAW-14 LAW-24 RULE-1 RULE-2 RULE-3 RULE-4

Formal typing.Protocols for Browser, Desktop, Vision, and Session Journal
runtimes. Every interface conforms to Interface Authority (LAW 2) and
enforces isolation guarantees (LAW 10, RULE 2).

Ref: Canon LAW 2 (Interface Authority)
Ref: Canon LAW 10 (Unreliable Workers — sandbox isolation)
Ref: Canon LAW 14 (Topology integrity — DOM state is a DAG)
Ref: Canon LAW 24 (Dispatcher Ownership — all actions through execution bus)
Ref: Canon RULE 1 (Determinism), RULE 2 (No Uncontrolled IO)
Ref: Canon RULE 3 (Safety Guards), RULE 4 (Isolation)
Ref: ROADMAP Phase H — Computer Use Runtime
Ref: DEVELOPER.md §15.2, §15.15b
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Protocol, Tuple, runtime_checkable


@runtime_checkable
class IBrowserRuntime(Protocol):  # LAW-2 LAW-10 LAW-14 RULE-2 RULE-4
    """Browser automation runtime — sandboxed, session-scoped.

    Every Browser Worker runs in an isolated browser context (Phase 4 Sandbox).
    DOM state is treated as a DAG (LAW 14) for topology integrity checks.
    All navigation and script execution flows through the Dispatcher (LAW 24).
    """

    def launch_session(  # LAW-10 RULE-4
        self,
        profile: Dict[str, Any],
        isolation_context: Dict[str, Any],
        capabilities: List[str],
    ) -> Dict[str, Any]:
        """Launch a new browser session inside a sandboxed context.

        Args:
            profile:        Browser profile (viewport, user-agent, extensions).
            isolation_context: Phase 4 sandbox parameters (network policy,
                              filesystem access, capability guard token).
            capabilities:   Declared capabilities (e.g. ["navigate", "dom_read",
                            "script_exec"]).

        Returns:
            session_id:     Unique session identifier.
            worker_pid:     Sandboxed process PID (for health monitoring).
            sandbox_token:  Capability guard token (RULE 2 enforcement).
            launched_at_ns: Epoch nanosecond timestamp.

        LAW 10: Every session MUST have an isolation_context.
        RULE 2: No uncontrolled IO — sandbox_token gates all operations.
        RULE 4: Session runs in isolated browser context.
        """

    def navigate_to(  # LAW-10 RULE-2
        self,
        session_id: str,
        url: str,
        sandbox_token: str,
        timeout_sec: float = 30.0,
    ) -> Dict[str, Any]:
        """Navigate the browser session to a URL.

        Args:
            session_id:     Target session.
            url:            Fully qualified URL to navigate to.
            sandbox_token:  Capability guard token (RULE 2 enforcement).
            timeout_sec:    Navigation timeout in seconds.

        Returns:
            page_loaded:    True if page fully loaded.
            final_url:      Resolved URL (after redirects).
            dom_hash:       DAG integrity hash of loaded DOM (LAW 14).
            load_time_ms:   Page load duration.
            error:          Error description if navigation failed.

        LAW 10: URL access governed by sandbox network policy.
        LAW 14: dom_hash captures DOM topology for integrity checks.
        """

    def execute_script(  # LAW-10 RULE-2
        self,
        session_id: str,
        code: str,
        sandbox_token: str,
        timeout_sec: float = 10.0,
    ) -> Dict[str, Any]:
        """Execute JavaScript inside the sandboxed browser context.

        Args:
            session_id:     Target session.
            code:           JavaScript source to execute.
            sandbox_token:  Capability guard token (RULE 2 enforcement).
            timeout_sec:    Execution timeout in seconds.

        Returns:
            result:         JSON-serialisable execution result.
            execution_ms:   Wall-clock execution time.
            error:          Error message if execution failed or was blocked.

        LAW 10: Script execution is sandboxed — no filesystem or network
                access unless explicitly permitted in isolation_context.
        RULE 2: All script execution requires valid sandbox_token.
        """

    def capture_dom_state(  # LAW-14 RULE-1
        self,
        session_id: str,
        sandbox_token: str,
    ) -> Dict[str, Any]:
        """Capture the current DOM state as a DAG topology.

        Args:
            session_id:     Target session.
            sandbox_token:  Capability guard token (RULE 2 enforcement).

        Returns:
            dom_dag:        DOM DAG topology (nodes, edges, attributes).
            dom_hash:       Deterministic hash of DOM structure (RULE 1).
            viewport_info:  Current viewport dimensions and scroll position.
            accessibility_tree: Simplified A11y tree for element grounding.

        LAW 14: DOM is represented as a directed acyclic graph (DAG).
        RULE 1: Same DOM structure → same dom_hash (deterministic).
        """


@runtime_checkable
class IDesktopWorker(Protocol):  # LAW-2 LAW-10 RULE-2 RULE-4
    """Desktop automation worker — sandboxed UI interaction.

    Every Desktop Worker interacts with the OS-level UI via the Phase 4
    Sandbox. All pointer/text input is gated by capability guards.
    No direct OS/Display access is permitted outside the sandbox.
    """

    def click(  # LAW-10 RULE-2
        self,
        session_id: str,
        target: Dict[str, Any],
        sandbox_token: str,
        button: str = "left",
        modifiers: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Perform a click action at a target coordinate or element selector.

        Args:
            session_id:     Target desktop session.
            target:         Click target — {"selector": str, "coordinates": [x,y]}
                            OR {"element_id": str, "bounding_box": [x,y,w,h]}.
            sandbox_token:  Capability guard token (RULE 2 enforcement).
            button:         Mouse button: "left", "right", "middle".
            modifiers:      Key modifiers: ["ctrl"], ["shift", "alt"], etc.

        Returns:
            clicked:        True if click was performed.
            actual_position: [x, y] coordinates where click landed.
            pre_screenshot:  Screenshot hash before click (for diff).
            error:          Error description if click failed or was blocked.

        LAW 10: Click is sandboxed — no uncontrolled input injection.
        RULE 2: target must have valid_selector OR spatial_bbox_verified.
        """

    def type_text(  # LAW-10 RULE-2
        self,
        session_id: str,
        input: str,
        sandbox_token: str,
        target: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Type text into a UI element or the current focus.

        Args:
            session_id:     Target desktop session.
            input:          Text to type.
            sandbox_token:  Capability guard token (RULE 2 enforcement).
            target:         Optional target element (selector or coordinates).
                            If None, types into currently focused element.

        Returns:
            typed:          True if text was typed.
            char_count:     Number of characters typed.
            error:          Error if typing was blocked or failed.

        LAW 10: Text input is isolated — no keystroke injection outside sandbox.
        RULE 2: Requires valid sandbox_token and optional target verification.
        """

    def screenshot_region(  # LAW-10 RULE-1
        self,
        session_id: str,
        region: Optional[Dict[str, int]] = None,
        sandbox_token: str = "",
    ) -> Dict[str, Any]:
        """Capture a screenshot of the full screen or a region.

        Args:
            session_id:     Target desktop session.
            region:         Optional — {"x": int, "y": int, "width": int,
                            "height": int}. Full screen if None.
            sandbox_token:  Capability guard token.

        Returns:
            image_hash:     SHA-256 hash of captured pixels (RULE 1).
            width:          Image width in pixels.
            height:         Image height in pixels.
            format:         Image encoding format (e.g. "png").
            captured_at_ns: Epoch nanosecond timestamp.

        RULE 1: Same region + same display → same image_hash (deterministic).
        """

    def get_foreground_window(  # LAW-10
        self,
        session_id: str,
        sandbox_token: str = "",
    ) -> Dict[str, Any]:
        """Get information about the currently focused window.

        Args:
            session_id:     Target desktop session.
            sandbox_token:  Capability guard token.

        Returns:
            window_title:   Title of the foreground window.
            process_name:   Name of the owning process.
            bounding_box:   [x, y, width, height] of window geometry.
            is_responsive:  True if the window is responding to events.
        """


@runtime_checkable
class IVisionGrounding(Protocol):  # LAW-2 LAW-10 RULE-1 RULE-3
    """Vision grounding — UI element detection, OCR, spatial grounding.

    All vision operations run inside the sandboxed context. No raw pixel
    data escapes without capability guard verification.
    """

    def detect_ui_element(  # RULE-1 RULE-3
        self,
        image: Dict[str, Any],
        query: Dict[str, Any],
        sandbox_token: str = "",
    ) -> Dict[str, Any]:
        """Detect a UI element in a screenshot matching a query.

        Args:
            image:       Input image — {"image_hash": str, "data": bytes}
                         OR {"image_hash": str, "path": str}.
            query:       Detection query — {"text": str, "type": str,
                         "role": str, "attributes": dict}.
            sandbox_token: Capability guard token.

        Returns:
            detected:        True if element was found.
            bounding_box:    [x, y, width, height] of detected element.
            confidence:      Detection confidence score [0.0, 1.0].
            selector:        Best CSS/XPath/accessibility selector.
            visual_context_hash: Hash of the region around the element.

        RULE 1: Deterministic detection — same image + query → same bbox.
        RULE 3: Low-confidence (< 0.7) results are flagged for review.
        """

    def extract_text_ocr(  # LAW-10 RULE-1
        self,
        image: Dict[str, Any],
        region: Optional[Dict[str, int]] = None,
        sandbox_token: str = "",
    ) -> Dict[str, Any]:
        """Extract text from an image using OCR.

        Args:
            image:      Input image — {"image_hash": str, "data": bytes}
                        OR {"image_hash": str, "path": str}.
            region:     Optional bounding box to restrict OCR.
            sandbox_token: Capability guard token.

        Returns:
            text:              Extracted text content.
            confidence:        OCR confidence score [0.0, 1.0].
            text_regions:      List of {"text": str, "bbox": [x,y,w,h],
                               "confidence": float} for each text region.
            character_count:   Total characters extracted.
            language:          Detected language code.

        RULE 1: Same image → same OCR output (deterministic).
        """

    def compute_spatial_bbox(  # RULE-1
        self,
        element: Dict[str, Any],
        viewport: Dict[str, int],
        sandbox_token: str = "",
    ) -> Dict[str, Any]:
        """Compute the absolute bounding box of a grounded element.

        Args:
            element:    Grounded element — {"selector": str, "relative_bbox":
                        [x,y,w,h], "dom_path": str}.
            viewport:   Viewport dimensions — {"width": int, "height": int}.
            sandbox_token: Capability guard token.

        Returns:
            absolute_bbox:  [x, y, width, height] in screen coordinates.
            is_visible:     True if element is within viewport.
            covered_pct:    Percentage of element covered by other elements.
            z_index:        Stacking context z-index.

        RULE 1: Same element + viewport → same spatial bbox.
        """

    def match_template(  # RULE-1 RULE-3
        self,
        screenshot: Dict[str, Any],
        template: Dict[str, Any],
        threshold: float = 0.8,
        sandbox_token: str = "",
    ) -> Dict[str, Any]:
        """Match a visual template in a screenshot.

        Args:
            screenshot:  Screenshot image — {"image_hash": str, "data": bytes}.
            template:    Template image — {"image_hash": str, "data": bytes}.
            threshold:   Minimum match confidence [0.0, 1.0].
            sandbox_token: Capability guard token.

        Returns:
            matched:        True if template was found above threshold.
            bounding_box:   [x, y, width, height] of best match location.
            confidence:     Match confidence score [0.0, 1.0].
            matches:        List of all matches above threshold.

        RULE 1: Same screenshot + template → same match result.
        RULE 3: Sub-threshold matches (< threshold) are not returned.
        """


@runtime_checkable
class ISessionJournal(Protocol):  # LAW-2 LAW-10 LAW-24 RULE-1 RULE-3
    """Session action journal — recording, checkpoint, replay, rollback.

    Every user/agent action is journaled for replay, audit, and rollback.
    The journal is the single source of truth for session history.
    """

    def record_action(  # LAW-24 RULE-1
        self,
        session_id: str,
        action_payload: Dict[str, Any],
        sandbox_token: str = "",
    ) -> Dict[str, Any]:
        """Record an action in the session journal.

        Args:
            session_id:     Target session.
            action_payload: Complete action payload with all context.
            sandbox_token:  Capability guard token.

        Returns:
            journal_entry_id:  Unique journal entry ID.
            sequence_number:   Monotonically increasing sequence number.
            recorded_at_ns:    Epoch nanosecond timestamp.
            state_hash:        Cumulative state hash after this action.

        LAW 24: All actions flow through Dispatcher — journal is the audit trail.
        RULE 1: Same action sequence → same state_hash chain (deterministic).
        """

    def save_checkpoint(  # LAW-10 RULE-3
        self,
        session_id: str,
        sandbox_token: str = "",
    ) -> Dict[str, Any]:
        """Save a checkpoint of the current session state.

        Args:
            session_id:     Target session.
            sandbox_token:  Capability guard token.

        Returns:
            checkpoint_id:   Unique checkpoint identifier.
            state_snapshot:  Serialised session state at checkpoint.
            checkpoint_hash: Cryptographic hash of the checkpoint.
            action_count:    Number of journaled actions included.

        RULE 3: Checkpoint requires capability_match and valid session state.
        """

    def replay_to_state(  # RULE-1 RULE-3
        self,
        session_id: str,
        target_state: Dict[str, Any],
        sandbox_token: str = "",
    ) -> Dict[str, Any]:
        """Replay journaled actions to reach a target state.

        Args:
            session_id:     Target session.
            target_state:   Target state descriptor — {"state_hash": str,
                            "sequence_number": int, "checkpoint_id": str}.
            sandbox_token:  Capability guard token.

        Returns:
            replay_ok:          True if replay completed successfully.
            actions_replayed:   Number of actions replayed.
            final_state_hash:   State hash after replay.
            deviations:         List of deviations from expected state.
            replay_duration_ms: Total replay wall-clock time.

        RULE 1: Deterministic replay — same journal → same state sequence.
        RULE 3: Replay aborts if deviation exceeds tolerance threshold.
        """

    def rollback_transaction(  # RULE-3
        self,
        session_id: str,
        to_checkpoint_id: str,
        sandbox_token: str = "",
    ) -> Dict[str, Any]:
        """Rollback the session to a previous checkpoint.

        Args:
            session_id:        Target session.
            to_checkpoint_id:  Target checkpoint to rollback to.
            sandbox_token:     Capability guard token.

        Returns:
            rollback_ok:         True if rollback completed.
            rolled_back_actions: Number of actions undone.
            restored_checkpoint: Checkpoint ID that was restored.
            current_state_hash:  State hash after rollback.

        RULE 3: Rollback is guarded — requires valid checkpoint and
                no in-flight actions that would be orphaned.
        """
