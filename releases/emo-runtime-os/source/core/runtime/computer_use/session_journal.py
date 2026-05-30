"""Phase H1 — Session Journal.  # LAW-24 RULE-1 RULE-3

Concrete implementation of ISessionJournal. Records every action with
deterministic hashing for replay and rollback safety.

Ref: Canon LAW 24 (Dispatcher Ownership)
Ref: Canon RULE 1 (Determinism), RULE 3 (Safety Guards)
Ref: artifacts/design/h1/protocols/01_computer_use_protocols.py
"""

from __future__ import annotations

import hashlib
import time
import uuid
from typing import Any, Dict, List, Optional

from core.runtime.computer_use.session_state_machine import (
    ComputerUseSessionStateMachine,
    InteractionGuardResult,
    SessionState,
)


class SessionJournal:  # LAW-24 RULE-1 RULE-3
    """Deterministic action journal for computer use sessions."""

    def __init__(
        self,
        state_machine: Optional[ComputerUseSessionStateMachine] = None,
    ) -> None:
        self._sm = state_machine or ComputerUseSessionStateMachine()
        self._journal: Dict[str, List[Dict[str, Any]]] = {}
        self._checkpoints: Dict[str, Dict[str, Any]] = {}
        self._last_state_hash: str = hashlib.sha256(b"init").hexdigest()[:32]

    @property
    def state_machine(self) -> ComputerUseSessionStateMachine:
        return self._sm

    def _get_or_create_journal(self, session_id: str) -> List[Dict[str, Any]]:
        if session_id not in self._journal:
            self._journal[session_id] = []
        return self._journal[session_id]

    def record_action(  # LAW-24 RULE-1
        self,
        session_id: str,
        action_payload: Dict[str, Any],
        sandbox_token: str = "",
    ) -> Dict[str, Any]:
        journal = self._get_or_create_journal(session_id)
        seq = len(journal) + 1

        action_type = action_payload.get("action_type", "")
        target_selector = action_payload.get("target_selector", "")
        input_data = action_payload.get("input_data", "")
        visual_hash = action_payload.get("visual_context_hash", "")
        guard_result = action_payload.get("guard_status", InteractionGuardResult.PASSED.value)
        error = action_payload.get("error", "")

        state_hash = self._sm.compute_state_hash(
            self._last_state_hash, action_type, target_selector,
            input_data, seq, visual_hash, guard_result, error,
        )

        entry = {
            "entry_id": f"je_{uuid.uuid4().hex[:16]}",
            "session_id": session_id,
            "sequence_number": seq,
            "action_type": action_type,
            "target_selector": target_selector,
            "input_data": input_data,
            "visual_context_hash": visual_hash,
            "guard_status": guard_result,
            "error": error,
            "state_hash": state_hash,
            "previous_state_hash": self._last_state_hash,
            "recorded_at_ns": time.time_ns(),
        }

        journal.append(entry)
        self._last_state_hash = state_hash

        return {
            "journal_entry_id": entry["entry_id"],
            "sequence_number": seq,
            "recorded_at_ns": entry["recorded_at_ns"],
            "state_hash": state_hash,
        }

    def save_checkpoint(  # LAW-10 RULE-3
        self,
        session_id: str,
        sandbox_token: str = "",
    ) -> Dict[str, Any]:
        journal = self._journal.get(session_id, [])
        checkpoint_id = f"ckpt_{uuid.uuid4().hex[:16]}"

        self._checkpoints[checkpoint_id] = {
            "checkpoint_id": checkpoint_id,
            "session_id": session_id,
            "state_snapshot": {"action_count": len(journal), "last_state_hash": self._last_state_hash},
            "checkpoint_hash": hashlib.sha256(f"ckpt:{session_id}:{len(journal)}:{self._last_state_hash}".encode()).hexdigest()[:32],
            "action_count": len(journal),
            "recorded_at_ns": time.time_ns(),
        }

        return self._checkpoints[checkpoint_id].copy()

    def replay_to_state(  # RULE-1 RULE-3
        self,
        session_id: str,
        target_state: Dict[str, Any],
        sandbox_token: str = "",
    ) -> Dict[str, Any]:
        journal = self._journal.get(session_id, [])
        target_hash = target_state.get("state_hash", "")
        target_seq = target_state.get("sequence_number", len(journal))

        actions_to_replay = [e for e in journal if e["sequence_number"] <= target_seq]
        deviations = []

        current_hash = hashlib.sha256(b"init").hexdigest()[:32]
        for entry in actions_to_replay:
            expected = entry["state_hash"]
            computed = self._sm.compute_state_hash(
                current_hash, entry["action_type"], entry["target_selector"],
                entry["input_data"], entry["sequence_number"],
                entry["visual_context_hash"], entry["guard_status"], entry["error"],
            )
            if computed != expected:
                deviations.append({
                    "sequence_number": entry["sequence_number"],
                    "expected": expected,
                    "computed": computed,
                })
            current_hash = expected

        replay_ok = len(deviations) == 0
        if target_hash and current_hash != target_hash:
            deviations.append({"detail": f"Final hash mismatch: {current_hash} != {target_hash}"})
            replay_ok = False

        return {
            "replay_ok": replay_ok,
            "actions_replayed": len(actions_to_replay),
            "final_state_hash": current_hash,
            "deviations": deviations,
            "replay_duration_ms": len(actions_to_replay) * 5.0,
        }

    def rollback_transaction(  # RULE-3
        self,
        session_id: str,
        to_checkpoint_id: str,
        sandbox_token: str = "",
    ) -> Dict[str, Any]:
        checkpoint = self._checkpoints.get(to_checkpoint_id)
        if not checkpoint:
            return {"rollback_ok": False, "rolled_back_actions": 0,
                    "restored_checkpoint": "", "current_state_hash": ""}

        journal = self._journal.get(session_id, [])
        ckpt_action_count = checkpoint["action_count"]
        rolled_back = journal[ckpt_action_count:]
        self._journal[session_id] = journal[:ckpt_action_count]

        self._last_state_hash = checkpoint["state_snapshot"]["last_state_hash"]

        return {
            "rollback_ok": True,
            "rolled_back_actions": len(rolled_back),
            "restored_checkpoint": to_checkpoint_id,
            "current_state_hash": self._last_state_hash,
        }

    def get_journal(self, session_id: str) -> List[Dict[str, Any]]:
        return list(self._journal.get(session_id, []))

    def get_checkpoint(self, checkpoint_id: str) -> Optional[Dict[str, Any]]:
        return self._checkpoints.get(checkpoint_id)

    def reset(self) -> None:
        self._journal.clear()
        self._checkpoints.clear()
        self._last_state_hash = hashlib.sha256(b"init").hexdigest()[:32]
        self._sm.reset()
