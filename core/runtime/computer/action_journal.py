"""ActionJournal — Deterministic action recording + replay.

LAW 5: Every interaction recorded as observable event.
LAW 8: Fully recoverable — same journal → same replay.
RULE 1: Deterministic — same entries → same integrity hash.

Each JournalEntry captures:
  - timestamp: ISO-8601 when the action occurred
  - action_type: Category (navigate, click, send_keys, etc.)
  - payload: Action-specific data (url, selector, text, etc.)
  - dom_snapshot_hash: DOM state fingerprint before the action
  - cursor_state: Cursor position and UI context at time of action
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


@dataclass
class JournalEntry:
    """A single deterministic action record."""

    timestamp: str
    action_type: str
    payload: Dict[str, Any]
    dom_snapshot_hash: str = ""
    cursor_state: Dict[str, Any] = field(default_factory=dict)

    def integrity_hash(self) -> str:
        """SHA-256 hash of all fields for integrity verification."""
        raw = json.dumps(asdict(self), sort_keys=True, ensure_ascii=False).encode()
        return hashlib.sha256(raw).hexdigest()


class ActionJournal:
    """Append-only journal of interface interactions.

    Supports export, import, and integrity verification.
    Thread-safe for concurrent recording (append-only).
    """

    def __init__(self) -> None:
        self._entries: List[JournalEntry] = []
        self._entry_hashes: Dict[int, str] = {}  # index → sha256

    def record(
        self,
        action_type: str,
        payload: Dict[str, Any],
        dom_snapshot_hash: str = "",
        cursor_state: Optional[Dict[str, Any]] = None,
    ) -> JournalEntry:
        """Record an action in the journal.

        Args:
            action_type: Category of action.
            payload: Action-specific data.
            dom_snapshot_hash: Pre-action DOM fingerprint.
            cursor_state: Cursor position and context.

        Returns:
            The created JournalEntry.
        """
        entry = JournalEntry(
            timestamp=datetime.now(timezone.utc).isoformat(),
            action_type=action_type,
            payload=payload,
            dom_snapshot_hash=dom_snapshot_hash,
            cursor_state=cursor_state or {},
        )
        self._entries.append(entry)
        self._entry_hashes[len(self._entries) - 1] = entry.integrity_hash()
        return entry

    def get_entries(self) -> List[JournalEntry]:
        """Return all recorded entries (immutable view)."""
        return list(self._entries)

    def entry_count(self) -> int:
        """Number of entries in the journal."""
        return len(self._entries)

    def export(self) -> Dict[str, Any]:
        """Export the entire journal as a serializable dict.

        Returns:
            Dict with metadata and all entries.
        """
        return {
            "version": 1,
            "entry_count": len(self._entries),
            "root_hash": self.root_hash(),
            "entries": [asdict(e) for e in self._entries],
            "hashes": dict(self._entry_hashes),
        }

    def import_journal(self, data: Dict[str, Any]) -> None:
        """Import entries from an exported journal dict.

        Rebuilds internal hash table for integrity verification.
        Appends to existing entries (does not clear).
        """
        if data.get("version") != 1:
            raise ValueError(f"Unsupported journal version: {data.get('version')}")
        start_index = len(self._entries)
        for entry_dict in data["entries"]:
            entry = JournalEntry(**entry_dict)
            self._entries.append(entry)
            self._entry_hashes[start_index] = entry.integrity_hash()
            start_index += 1

    def verify_integrity(self) -> bool:
        """Verify that all entries match their recorded hashes.

        Returns:
            True if every entry's hash matches its stored hash.
        """
        for idx, entry in enumerate(self._entries):
            expected = self._entry_hashes.get(idx)
            if expected is None:
                return False
            if entry.integrity_hash() != expected:
                return False
        return True

    def root_hash(self) -> str:
        """SHA-256 hash of the entire journal chain.

        Uses the hashes of all entries to produce a single root.
        Deterministic: same entries → same root_hash.
        """
        combined = "".join(
            self._entry_hashes.get(i, "") for i in range(len(self._entries))
        ).encode()
        return hashlib.sha256(combined).hexdigest()
