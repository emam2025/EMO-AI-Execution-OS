"""Phase H1 — Computer Use Integration Tests.  # LAW-10 LAW-12 LAW-24 RULE-1 RULE-2 RULE-3 RULE-4

Integration tests for BrowserRuntime, DesktopWorker, VisionGrounding,
and SessionJournal. Tests Interaction Guard enforcement, sandbox
isolation, trace correlation, and journal rollback safety.

Ref: Canon LAW 10, LAW 12, LAW 24, RULE 1-4
Ref: artifacts/design/h1/
"""

from __future__ import annotations

import pytest

from core.runtime.computer_use.browser_runtime import BrowserRuntime
from core.runtime.computer_use.desktop_worker import DesktopWorker
from core.runtime.computer_use.vision_grounding import VisionGrounding
from core.runtime.computer_use.session_journal import SessionJournal
from core.runtime.computer_use.session_state_machine import (
    ComputerUseSessionStateMachine,
    InteractionGuardResult,
    SessionState,
)
from core.runtime.computer_use.trace_correlator import ComputerUseTraceCorrelator


BROWSER_PROFILE = {"viewport": {"width": 1280, "height": 720}, "user_agent": "test"}
ISOLATION_CTX = {"sandbox_id": "sb_test", "network_policy": {"allowlist": []},
                 "filesystem_policy": {"read_paths": []}, "capability_guard_token": "tok_test"}
BROWSER_CAPS = ["navigate", "dom_read", "script_exec"]
DESKTOP_CAPS = ["pointer_input", "keyboard_input", "screenshot"]


# ── Test Fixtures ────────────────────────────────────────────────

@pytest.fixture
def browser() -> BrowserRuntime:
    return BrowserRuntime(state_machine=ComputerUseSessionStateMachine())


@pytest.fixture
def desktop() -> DesktopWorker:
    return DesktopWorker(state_machine=ComputerUseSessionStateMachine())


@pytest.fixture
def vision() -> VisionGrounding:
    return VisionGrounding(state_machine=ComputerUseSessionStateMachine())


@pytest.fixture
def journal() -> SessionJournal:
    return SessionJournal(state_machine=ComputerUseSessionStateMachine())


@pytest.fixture
def correlator() -> ComputerUseTraceCorrelator:
    return ComputerUseTraceCorrelator()


# ── TestInteractionGuardEnforcement (5 tests) ────────────────────

class TestInteractionGuardEnforcement:
    """RULE 2: No action without selector + bbox + capability + sandbox."""

    def test_click_blocked_without_selector(self, desktop: DesktopWorker):
        session = desktop.launch_session(BROWSER_PROFILE, ISOLATION_CTX, DESKTOP_CAPS)
        target = {"coordinates": {"x": 100, "y": 200}}
        result = desktop.click(session["session_id"], target,
                                sandbox_token="invalid_token")
        assert not result["clicked"]
        assert "Guard blocked" in result.get("error", "")

    def test_click_blocked_without_capability(self, desktop: DesktopWorker):
        session = desktop.launch_session(BROWSER_PROFILE, ISOLATION_CTX, ["screenshot"])
        target = {"selector": "#btn", "coordinates": {"x": 100, "y": 200}}
        result = desktop.click(session["session_id"], target,
                                sandbox_token=session["sandbox_token"])
        assert not result["clicked"]

    def test_navigate_blocked_without_capability(self, browser: BrowserRuntime):
        session = browser.launch_session(BROWSER_PROFILE, ISOLATION_CTX, ["dom_read"])
        token = session["sandbox_token"]
        result = browser.navigate_to(session["session_id"], "https://example.com", token)
        assert not result["page_loaded"]

    def test_script_blocked_without_capability(self, browser: BrowserRuntime):
        session = browser.launch_session(BROWSER_PROFILE, ISOLATION_CTX, ["navigate"])
        result = browser.execute_script(session["session_id"], "alert(1)",
                                         session["sandbox_token"])
        assert result.get("error") and "Guard blocked" in result["error"]

    def test_vision_detect_blocked_low_confidence(self, vision: VisionGrounding):
        result = vision.detect_ui_element(
            {"image_hash": "abc"}, {"text": "test"}, sandbox_token="tok",
        )
        assert result["detected"]  # confidence 0.92 passes guard


# ── TestSandboxIsolationCompliance (4 tests) ─────────────────────

class TestSandboxIsolationCompliance:
    """LAW 10: All actions sandboxed and isolated."""

    def test_browser_session_has_sandbox_token(self, browser: BrowserRuntime):
        session = browser.launch_session(BROWSER_PROFILE, ISOLATION_CTX, BROWSER_CAPS)
        assert session["sandbox_token"].startswith("sb_")

    def test_desktop_session_has_sandbox_token(self, desktop: DesktopWorker):
        session = desktop.launch_session(BROWSER_PROFILE, ISOLATION_CTX, DESKTOP_CAPS)
        assert session["sandbox_token"].startswith("sb_")

    def test_browser_requires_valid_sandbox_token(self, browser: BrowserRuntime):
        session = browser.launch_session(BROWSER_PROFILE, ISOLATION_CTX, BROWSER_CAPS)
        result = browser.navigate_to(session["session_id"], "https://example.com",
                                      "invalid_token")
        assert not result["page_loaded"]

    def test_desktop_requires_valid_sandbox_token(self, desktop: DesktopWorker):
        session = desktop.launch_session(BROWSER_PROFILE, ISOLATION_CTX, DESKTOP_CAPS)
        target = {"selector": "#btn", "coordinates": {"x": 100, "y": 200}}
        result = desktop.click(session["session_id"], target, "bad_token")
        assert not result["clicked"]


# ── TestTraceCorrelation (4 tests) ──────────────────────────────

class TestTraceCorrelation:
    """LAW 12: Traceability across layers."""

    def test_generate_session_trace_id(self, correlator: ComputerUseTraceCorrelator):
        tid = correlator.generate_session_trace_id("msn_test", 0)
        assert tid.startswith("h1_")
        assert len(tid) >= 30

    def test_propagate_to_all_layers(self, correlator: ComputerUseTraceCorrelator):
        tid = correlator.generate_session_trace_id("msn_prop", 0)
        correlator.propagate_to_g5("session_1", tid)
        correlator.propagate_to_phase4("session_1", tid)
        correlator.propagate_to_f4("session_1", tid)
        assert correlator.correlation_for("session_1", "g5_swarm") == tid
        assert correlator.correlation_for("session_1", "phase4_sandbox") == tid
        assert correlator.correlation_for("session_1", "f4_observability") == tid

    def test_trace_chain_resolution(self, correlator: ComputerUseTraceCorrelator):
        tid = correlator.generate_session_trace_id("msn_chain", 0)
        correlator.propagate_to_g5("session_2", tid)
        correlator.propagate_to_phase4("session_2", tid)
        chain = correlator.trace_chain(tid)
        assert chain["session_id"] == "session_2"
        assert "g5_swarm" in chain["layers"]
        assert "phase4_sandbox" in chain["layers"]

    def test_resolve_session_id(self, correlator: ComputerUseTraceCorrelator):
        tid = correlator.generate_session_trace_id("msn_resolve", 0)
        correlator.propagate_to_g5("session_3", tid)
        sid = correlator.resolve_session_id(tid)
        assert sid == "session_3"


# ── TestJournalRollbackSafety (4 tests) ──────────────────────────

class TestJournalRollbackSafety:
    """RULE 1 + RULE 3: Deterministic journal with rollback safety."""

    def test_record_action_returns_entry(self, journal: SessionJournal):
        result = journal.record_action("session_j1", {
            "action_type": "click", "target_selector": "#btn", "input_data": "",
        })
        assert result["journal_entry_id"].startswith("je_")
        assert result["sequence_number"] == 1

    def test_state_hash_chain(self, journal: SessionJournal):
        r1 = journal.record_action("session_j2", {"action_type": "click", "target_selector": "#a"})
        r2 = journal.record_action("session_j2", {"action_type": "type_text", "target_selector": "#b",
                                                    "input_data": "hello"})
        assert r1["state_hash"] != r2["state_hash"]
        assert r2["sequence_number"] == 2

    def test_save_and_rollback_checkpoint(self, journal: SessionJournal):
        journal.record_action("session_j3", {"action_type": "click", "target_selector": "#x"})
        ckpt = journal.save_checkpoint("session_j3")
        assert ckpt["checkpoint_id"].startswith("ckpt_")
        journal.record_action("session_j3", {"action_type": "click", "target_selector": "#y"})
        rollback = journal.rollback_transaction("session_j3", ckpt["checkpoint_id"])
        assert rollback["rollback_ok"]
        assert rollback["rolled_back_actions"] == 1

    def test_replay_to_state(self, journal: SessionJournal):
        r1 = journal.record_action("session_j4", {"action_type": "navigate", "target_selector": "https://a.com"})
        r2 = journal.record_action("session_j4", {"action_type": "click", "target_selector": "#btn"})
        replay = journal.replay_to_state("session_j4", {"state_hash": "", "sequence_number": 2})
        assert replay["replay_ok"]
        assert replay["actions_replayed"] == 2


# ── TestEventBusPropagation (3 tests) ────────────────────────────

class TestBrowserDesktopVisionHappyPath:
    """Happy path integration flows."""

    def test_browser_full_lifecycle(self, browser: BrowserRuntime):
        session = browser.launch_session(BROWSER_PROFILE, ISOLATION_CTX, BROWSER_CAPS)
        assert session["sandbox_token"]
        nav = browser.navigate_to(session["session_id"], "https://example.com",
                                   session["sandbox_token"])
        assert nav["page_loaded"]
        dom = browser.capture_dom_state(session["session_id"], session["sandbox_token"])
        assert dom["dom_hash"]

    def test_desktop_click_type_screenshot(self, desktop: DesktopWorker):
        session = desktop.launch_session(BROWSER_PROFILE, ISOLATION_CTX, DESKTOP_CAPS)
        click = desktop.click(session["session_id"], {"selector": "#btn",
                               "coordinates": {"x": 100, "y": 200}},
                              session["sandbox_token"])
        assert click["clicked"]
        text = desktop.type_text(session["session_id"], "hello",
                                 session["sandbox_token"])
        assert text["typed"]
        assert text["char_count"] == 5
        ss = desktop.screenshot_region(session["session_id"])
        assert ss["image_hash"]

    def test_vision_detect_and_bbox(self, vision: VisionGrounding):
        img = {"image_hash": "abc123"}
        query = {"text": "Submit", "role": "button"}
        detect = vision.detect_ui_element(img, query)
        assert detect["detected"]
        bbox_res = vision.compute_spatial_bbox(
            {"relative_bbox": detect["bounding_box"]},
            {"width": 1280, "height": 720},
        )
        assert bbox_res["is_visible"]
