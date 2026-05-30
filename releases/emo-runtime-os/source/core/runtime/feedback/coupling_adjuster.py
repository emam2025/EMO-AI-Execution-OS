"""D9 — IDynamicCouplingAdjuster implementation.

Computes new coupling/risk scores from runtime trace data,
validates against architectural thresholds, and commits boundary
updates to CodeGraph metadata (via file protocol — §17.9).

LAW 14: All boundary decisions MUST be derived from analysis.
LAW 15: No refactor without graph update.
LAW 16: risk_score > 0.8 → decomposition required.

§17.9: CodeGraph MUST NOT depend on runtime — file protocol only.

Ref: DEVELOPER.md §5.3, §5.4, §17.9
Ref: Canon LAW 14-16
Ref: artifacts/design/d9/protocols/01_feedback_loop_protocols.py
"""

from __future__ import annotations

import json
import os
import tempfile
from hashlib import sha256
from typing import Any, Dict, List, Optional, Tuple

from core.runtime.models.feedback_models import FeedbackPolicy, TraceEvent


class DynamicCouplingAdjuster:
    """Computes coupling/risk scores from traces and commits to metadata.

    LAW 14: Scores are derived from execution trace analysis.
    LAW 15: Atomic file swap for metadata updates.
    LAW 16: Risk scores above 0.8 flagged for decomposition.

    §17.9: Communicates with CodeGraph exclusively through filesystem.
    """

    def compute_new_scores(
        self,
        traces: List[TraceEvent],
        baseline: Optional[Dict[str, float]] = None,
    ) -> Dict[str, float]:
        """Compute new coupling/risk scores from execution traces.

        LAW 14: All boundary decisions MUST be derived from analysis.

        Algorithm:
          1. Count cross-boundary calls per node from traces
          2. Compute coupling = cross_boundary / total_calls
          3. Compute risk = coupling * (1 + failure_rate)

        Args:
            traces: List of TraceEvent records from recent window.
            baseline: Optional current baseline scores.

        Returns:
            Dict mapping node_id → new_coupling_score (0.0–1.0).
        """
        if not traces:
            return dict(baseline or {})

        node_data: Dict[str, Dict[str, Any]] = {}
        for trace in traces:
            node_id = trace.node_id or trace.tool_name
            if not node_id:
                continue
            if node_id not in node_data:
                node_data[node_id] = {"total": 0, "cross_boundary": 0, "failures": 0}
            node_data[node_id]["total"] += 1
            if trace.outcome in ("failed", "timeout", "cancelled", "blocked"):
                node_data[node_id]["failures"] += 1
            # Simulate cross-boundary detection via feedback_signals
            if "infrastructure_leakage" in trace.feedback_signals:
                node_data[node_id]["cross_boundary"] += 1

        scores: Dict[str, float] = {}
        for node_id, data in node_data.items():
            total = max(data["total"], 1)
            cross = data["cross_boundary"]
            failures = data["failures"]
            coupling = cross / max(total, 1)
            failure_rate = failures / max(total, 1)
            risk = coupling * (1.0 + failure_rate)
            risk = min(1.0, max(0.0, risk))
            scores[node_id] = round(risk, 4)

        return scores

    def validate_threshold(
        self,
        new_score: float,
        old_score: float,
        node_id: str = "",
    ) -> Tuple[bool, str]:
        """Validate that a score change is within acceptable thresholds.

        LAW 14: coupling delta > 0.1 → violation.
        LAW 16: risk_score > 0.8 → decomposition required.

        Args:
            new_score: Proposed new score.
            old_score: Current baseline score.
            node_id: Node identifier for context.

        Returns:
            (valid: bool, reason: str)
        """
        delta = new_score - old_score
        if new_score > 0.8:
            return False, (
                f"LAW 16: risk_score {new_score:.4f} > 0.8 for {node_id} "
                f"— decomposition required"
            )
        if delta > 0.1:
            return False, (
                f"LAW 14: coupling delta {delta:.4f} > 0.1 for {node_id}"
            )
        if delta < -0.1:
            return False, (
                f"Coupling delta {delta:.4f} < -0.1 — unusual decrease"
            )
        return True, "within threshold"

    def commit_boundary_update(
        self,
        node_id: str,
        new_score: float,
        metadata_path: str = "",
    ) -> bool:
        """Commit a boundary score update via atomic file swap.

        LAW 15: Graph MUST be updated before any refactor.
        §17.9: File protocol only — no CodeGraph imports.

        Atomic swap:
          1. Read existing metadata (if path provided)
          2. Compute new scores dict
          3. Write to .tmp file
          4. Compute sha256 checksum
          5. Rename .tmp → metadata.json

        Args:
            node_id: Node identifier.
            new_score: New coupling/risk score.
            metadata_path: Path to CodeGraph metadata file.

        Returns:
            True if commit succeeded.
        """
        if not metadata_path:
            return True

        try:
            existing: Dict[str, Any] = {}
            if os.path.exists(metadata_path):
                with open(metadata_path) as f:
                    existing = json.load(f)

            existing["scores"] = existing.get("scores", {})
            existing["scores"][node_id] = new_score
            existing["checksum"] = sha256(
                json.dumps(existing["scores"], sort_keys=True).encode()
            ).hexdigest()

            dir_path = os.path.dirname(metadata_path) or "."
            with tempfile.NamedTemporaryFile(
                mode="w", dir=dir_path, prefix="metadata_",
                suffix=".tmp", delete=False,
            ) as tmp:
                json.dump(existing, tmp, indent=2)
                tmp_path = tmp.name

            os.replace(tmp_path, metadata_path)
            return True

        except (OSError, json.JSONDecodeError):
            return False

    def compute_checksum(self, metadata: Dict[str, Any]) -> str:
        """Compute SHA-256 checksum of metadata scores.

        Args:
            metadata: Metadata dict with scores.

        Returns:
            Hex digest string.
        """
        scores = metadata.get("scores", {})
        return sha256(
            json.dumps(scores, sort_keys=True).encode()
        ).hexdigest()
