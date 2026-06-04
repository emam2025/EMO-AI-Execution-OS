"""Phase H — Computer Use Runtime Foundation: 30 tests.

Groups:
  - TestProtocolCompliance:      6 tests — 3 protocols conformed + runtime_checkable
  - TestSessionLifecycle:        6 tests — create, activate, pause, resume, replay, terminate
  - TestActionJournalIntegrity:  6 tests — record, export, import, verify_integrity
  - TestFacadeRouting:           6 tests — dispatch, replay, stub isolation, error handling
  - TestZeroAutomationDeps:      6 tests — zero playwright/selenium/opencv/PIL in core/

Ref: Canon LAW 3, LAW 5, LAW 8, LAW 10, LAW 13, RULE 1
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict

import pytest

from core.interfaces.computer import IBrowserWorker, IDesktopWorker, IVisionWorker
from core.runtime.computer import (
    ActionJournal,
    ComputerRuntimeFacade,
    ComputerWorkerStub,
    SessionManager,
    VisionAdapter,
)
from core.runtime.computer.action_journal import JournalEntry
from core.runtime.computer.session_manager import SessionState


# ═══════════════════════════════════════════════════════════════════
# Group 1 — ProtocolCompliance
# ═══════════════════════════════════════════════════════════════════

class TestProtocolCompliance:
    """Verify all 3 protocols are properly implemented."""

    def test_ibrowser_worker_is_protocol(self):
        assert isinstance(IBrowserWorker, type)
        assert IBrowserWorker is not IBrowserWorker.__class__

    def test_idesktop_worker_is_protocol(self):
        assert isinstance(IDesktopWorker, type)
        assert IDesktopWorker is not IDesktopWorker.__class__

    def test_ivision_worker_is_protocol(self):
        assert isinstance(IVisionWorker, type)
        assert IVisionWorker is not IVisionWorker.__class__

    def test_stub_conforms_browser(self):
        stub = ComputerWorkerStub()
        assert isinstance(stub, IBrowserWorker)

    def test_stub_conforms_desktop(self):
        stub = ComputerWorkerStub()
        assert isinstance(stub, IDesktopWorker)

    def test_stub_conforms_vision(self):
        stub = ComputerWorkerStub()
        assert isinstance(stub, IVisionWorker)


# ═══════════════════════════════════════════════════════════════════
# Group 2 — SessionLifecycle
# ═══════════════════════════════════════════════════════════════════

class TestSessionLifecycle:
    """Verify SessionManager state machine transitions."""

    def test_create_session_returns_idle(self):
        sm = SessionManager()
        session = sm.create_session("browser")
        assert session.state == SessionState.IDLE

    def test_activate_transitions_to_active(self):
        sm = SessionManager()
        session = sm.create_session("browser")
        sm.activate_session(session.session_id)
        assert sm.get_session(session.session_id).state == SessionState.ACTIVE

    def test_pause_transitions_to_paused(self):
        sm = SessionManager()
        session = sm.create_session("browser")
        sm.activate_session(session.session_id)
        sm.pause_session(session.session_id)
        assert sm.get_session(session.session_id).state == SessionState.PAUSED

    def test_resume_returns_to_active(self):
        sm = SessionManager()
        session = sm.create_session("browser")
        sm.activate_session(session.session_id)
        sm.pause_session(session.session_id)
        sm.resume_session(session.session_id)
        assert sm.get_session(session.session_id).state == SessionState.ACTIVE

    def test_terminate_cleans_up(self):
        sm = SessionManager()
        session = sm.create_session("desktop")
        sm.activate_session(session.session_id)
        sm.terminate_session(session.session_id)
        assert sm.get_session(session.session_id).state == SessionState.TERMINATED

    def test_invalid_transition_raises(self):
        sm = SessionManager()
        session = sm.create_session("browser")
        with pytest.raises(ValueError, match="Invalid transition"):
            sm.pause_session(session.session_id)  # IDLE → PAUSED is invalid


# ═══════════════════════════════════════════════════════════════════
# Group 3 — ActionJournalIntegrity
# ═══════════════════════════════════════════════════════════════════

class TestActionJournalIntegrity:
    """Verify ActionJournal recording, export, import, integrity."""

    def test_record_returns_entry(self):
        journal = ActionJournal()
        entry = journal.record("navigate", {"url": "https://example.com"})
        assert isinstance(entry, JournalEntry)
        assert entry.action_type == "navigate"

    def test_export_returns_all_entries(self):
        journal = ActionJournal()
        journal.record("click", {"selector": "#btn"})
        journal.record("navigate", {"url": "https://example.com"})
        exported = journal.export()
        assert exported["entry_count"] == 2
        assert len(exported["entries"]) == 2

    def test_import_appends_correctly(self):
        journal = ActionJournal()
        journal.record("click", {"selector": "#btn"})
        exported = journal.export()

        journal2 = ActionJournal()
        journal2.import_journal(exported)
        assert journal2.entry_count() == 1
        assert journal2.get_entries()[0].action_type == "click"

    def test_verify_integrity_returns_true_for_valid(self):
        journal = ActionJournal()
        journal.record("navigate", {"url": "https://example.com"})
        assert journal.verify_integrity() is True

    def test_verify_integrity_returns_false_for_tampered(self):
        journal = ActionJournal()
        journal.record("navigate", {"url": "https://example.com"})
        # Tamper with internal state
        journal._entries[0].action_type = "click"
        assert journal.verify_integrity() is False

    def test_root_hash_deterministic(self):
        entry1 = JournalEntry(
            timestamp="2026-01-01T00:00:00+00:00",
            action_type="navigate",
            payload={"url": "https://example.com"},
        )
        entry2 = JournalEntry(
            timestamp="2026-01-01T00:00:00+00:00",
            action_type="navigate",
            payload={"url": "https://example.com"},
        )
        assert entry1.integrity_hash() == entry2.integrity_hash()

        journal = ActionJournal()
        journal._entries.append(entry1)
        journal._entry_hashes[0] = entry1.integrity_hash()
        hash1 = journal.root_hash()

        journal2 = ActionJournal()
        journal2._entries.append(entry2)
        journal2._entry_hashes[0] = entry2.integrity_hash()
        hash2 = journal2.root_hash()

        assert hash1 == hash2  # Same entries → same hash


# ═══════════════════════════════════════════════════════════════════
# Group 4 — FacadeRouting
# ═══════════════════════════════════════════════════════════════════

class TestFacadeRouting:
    """Verify ComputerRuntimeFacade dispatch, replay, and isolation."""

    @pytest.fixture
    def facade(self) -> ComputerRuntimeFacade:
        sm = SessionManager()
        aj = ActionJournal()
        stub = ComputerWorkerStub()
        return ComputerRuntimeFacade(
            session_manager=sm,
            action_journal=aj,
            browser_worker=stub,
            desktop_worker=stub,
            stub_mode=True,
        )

    def test_dispatch_to_browser_returns_results(self, facade):
        sm = facade._session_manager
        session = sm.create_session("browser")
        sm.activate_session(session.session_id)
        plan = [{"action_type": "launch", "params": {"url": "about:blank"}}]
        results = facade.dispatch_to_browser(session.session_id, plan)
        assert len(results) == 1
        assert results[0]["action_type"] == "launch"

    def test_dispatch_to_desktop_returns_results(self, facade):
        sm = facade._session_manager
        session = sm.create_session("desktop")
        sm.activate_session(session.session_id)
        plan = [{"action_type": "launch_app", "params": {"app_path": "/usr/bin/echo"}}]
        results = facade.dispatch_to_desktop(session.session_id, plan)
        assert len(results) == 1

    def test_replay_session_succeeds(self, facade):
        sm = facade._session_manager
        session = sm.create_session("browser")
        sm.activate_session(session.session_id)
        # Record some actions
        facade._journal.record("navigate", {"url": "https://example.com"})
        facade._journal.record("click", {"selector": "#btn"})
        sm.pause_session(session.session_id)
        assert facade.replay_session(session.session_id) is True

    def test_replay_fails_on_bad_integrity(self, facade):
        sm = facade._session_manager
        session = sm.create_session("browser")
        sm.activate_session(session.session_id)
        sm.pause_session(session.session_id)
        facade._journal.record("navigate", {"url": "https://example.com"})
        facade._journal._entries[0].action_type = "tampered"
        with pytest.raises(ValueError, match="integrity"):
            facade.replay_session(session.session_id)

    def test_stub_mode_uses_mock_worker(self, facade):
        result = facade._browser_worker.launch("about:blank")
        assert isinstance(result, str)
        assert len(result) == 16

    def test_unknown_browser_action_raises(self, facade):
        sm = facade._session_manager
        session = sm.create_session("browser")
        sm.activate_session(session.session_id)
        plan = [{"action_type": "nonexistent", "params": {}}]
        with pytest.raises(ValueError, match="Unknown browser action"):
            facade.dispatch_to_browser(session.session_id, plan)


# ═══════════════════════════════════════════════════════════════════
# Group 5 — ZeroAutomationDeps
# ═══════════════════════════════════════════════════════════════════

class TestZeroAutomationDeps:
    """Verify zero automation libraries in core/computer/."""

    PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
    STRING_BLACKLIST = [
        "playwright",
        "selenium",
        "pyautogui",
        "opencv",
        "cv2",
        "PIL",
        "Image",
    ]

    FILES = [
        PROJECT_ROOT / "core/interfaces/computer/browser.py",
        PROJECT_ROOT / "core/interfaces/computer/desktop.py",
        PROJECT_ROOT / "core/interfaces/computer/vision.py",
        PROJECT_ROOT / "core/runtime/computer/session_manager.py",
        PROJECT_ROOT / "core/runtime/computer/action_journal.py",
        PROJECT_ROOT / "core/runtime/computer/computer_facade.py",
        PROJECT_ROOT / "core/runtime/computer/vision_adapter.py",
        PROJECT_ROOT / "core/runtime/computer/stub_impl.py",
    ]

    @pytest.mark.parametrize("filepath", FILES)
    def test_no_automation_imports(self, filepath):
        text = filepath.read_text()
        lines = text.splitlines()
        import_lines = [line.lower() for line in lines if line.startswith(("import ", "from "))]
        content = "\n".join(import_lines)
        for keyword in self.STRING_BLACKLIST:
            assert keyword not in content, (
                f"Automation keyword '{keyword}' imported in {filepath}"
            )

    def test_facade_no_model_atts(self):
        sm = SessionManager()
        aj = ActionJournal()
        f = ComputerRuntimeFacade(session_manager=sm, action_journal=aj)
        assert not hasattr(f, "_model")
        assert not hasattr(f, "_llm")
        assert not hasattr(f, "_client")
