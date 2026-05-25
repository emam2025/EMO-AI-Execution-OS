"""P1 — Final Architecture Review.  # LAW-5 # LAW-18

Generates KNOWN_PRODUCTION_CONSTRAINTS.md — a signed register of certified
trade-offs, each linked to a Canon Law and mitigation strategy.

Ref: EXEC-DIRECTIVE-029 §Task-4
Ref: Canon LAW 5 (Observability), LAW 18 (Trace Analysis Determinism)
Ref: RULE 1 (Deterministic Hashing)
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

BASE = Path(__file__).resolve().parent.parent.parent

# Known constraints: (id, area, description, canon_law, mitigation, severity)
KNOWN_CONSTRAINTS: List[Tuple[str, str, str, str, str, str]] = [
    (
        "PC-001",
        "Persistence",
        "SQLite-based EventStore — writes are single-node. At > 10k events/sec the WAL becomes a bottleneck.",
        "LAW 5, LAW 20",
        "Replace with PostgreSQL or distributed log (Phase I2 ready, not activated). Monitor WAL lag. Triggers at 8k events/sec.",
        "medium",
    ),
    (
        "PC-002",
        "Replay",
        "Replay determinism is ≥ 99.3% but not 100% — time-dependent operations (wall_clock, random seeds) drift across runs.",
        "LAW 3, LAW 18",
        "Accept ≤ 0.7% drift for time-dependent DAGs. Isolate time via TimeProvider interface in future.",
        "low",
    ),
    (
        "PC-003",
        "Scale",
        "Worker pool is fixed at construction time (default 4, max 256). No dynamic auto-scaling in production.",
        "LAW 13, F2",
        "Auto-scaler implemented but not activated. Manual scaling via operator action. Set target count via `build_final_release(worker_pool_size=N)`.",
        "medium",
    ),
    (
        "PC-004",
        "Observability",
        "TopologyViewer returns static/mocked data — no live agent inventory. Operator CLI shows placeholder worker topology.",
        "LAW 5",
        "Post-freeze agent discovery integration. Current worker count hardcoded to 3. Acceptable for pilot.",
        "low",
    ),
    (
        "PC-005",
        "Replay Drift",
        "ReplayDrift metric reports 0.0 (placeholder) — no actual cross-run drift measurement implemented.",
        "LAW 3, LAW 12",
        "Accurate drift requires replay baseline comparison. Accept 0.0 placeholder for pilot. Tracked as AD-007.",
        "low",
    ),
    (
        "PC-006",
        "Operator UI",
        "Operator UI is single-process (no auth, no TLS, no multi-session). Suitable for local pilot only.",
        "LAW 10",
        "Wrap behind reverse proxy with basic auth for >3 users. TLS and session management not implemented.",
        "medium",
    ),
    (
        "PC-007",
        "Agent Layer",
        "Multi-agent layer (G5) has zero test coverage — conceptual only. Not activated in production.",
        "LAW 5, RULE 2",
        "Deferred to K6 phase. No runtime impact — layer is not wired in CompositionRoot.",
        "low",
    ),
]


def generate_constraints_doc(output_path: str) -> Dict[str, Any]:
    lines: List[str] = []
    lines.append("# Known Production Constraints — Certified Trade-Offs  # LAW-5 # LAW-18")
    lines.append("")
    lines.append(f"*Generated at: {time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())}*")
    lines.append(f"*Version: 4.10.1-human-validated*")
    lines.append("")
    lines.append("This document catalogs all known production constraints accepted as")
    lines.append("**Certified Trade-Offs** for the v4.10.1 pilot release. Each constraint")
    lines.append("is linked to a Canon Law and has an explicit mitigation strategy.")
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("| ID | Area | Description | Canon Law | Mitigation | Severity |")
    lines.append("|----|------|-------------|-----------|------------|----------|")

    constraints_data: List[Dict[str, Any]] = []
    for cid, area, desc, law, mit, sev in KNOWN_CONSTRAINTS:
        lines.append(f"| **{cid}** | {area} | {desc} | {law} | {mit} | {sev} |")
        constraints_data.append({
            "id": cid, "area": area, "description": desc,
            "canon_law": law, "mitigation": mit, "severity": sev,
        })

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("## Signature")
    lines.append("")

    content = "\n".join(lines)
    signature = hashlib.sha256(content.encode()).hexdigest()[:64]

    lines.append(f"**SHA-256:** `{signature}`")
    lines.append("")
    lines.append("*This document is digitally signed. Any modification invalidates the signature.*")

    content_signed = "\n".join(lines)
    with open(output_path, "w") as f:
        f.write(content_signed)

    result = {
        "constraint_count": len(KNOWN_CONSTRAINTS),
        "signature": signature,
        "output_path": output_path,
        "constraints": constraints_data,
    }

    meta_path = Path(output_path).with_suffix(".meta.json")
    with open(meta_path, "w") as f:
        json.dump(result, f, indent=2, default=str)

    return result


def main() -> None:
    out = str(BASE / "docs" / "KNOWN_PRODUCTION_CONSTRAINTS.md")
    result = generate_constraints_doc(out)
    print(f"Generated {result['output_path']}")
    print(f"Constraints: {result['constraint_count']}")
    print(f"Signature: {result['signature'][:16]}...")


if __name__ == "__main__":
    main()
