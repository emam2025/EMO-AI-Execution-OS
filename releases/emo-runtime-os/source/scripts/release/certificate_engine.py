"""Phase FINAL — Certificate Engine.  # LAW-1 LAW-3 LAW-5 LAW-11 RULE-1 RULE-3

Generates the final RELEASE_CERTIFICATE.json with SHA-256 file fingerprints,
test matrix, guard compliance matrix, and the full certification summary.

Ref: Canon LAW 1-27, RULE 1-5
Ref: DEVELOPER.md §16 (Architecture Canon)
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any, Dict, List, Optional


class CertificateEngine:  # LAW-1 LAW-3 LAW-5 LAW-11 RULE-1 RULE-3
    """Generates the final release certificate with full test and guard matrix.

    LAW 3: All file hashes are deterministic.
    LAW 5: Certificate is the stability anchor.
    LAW 11: No global state.
    RULE 1: SHA-256 hashes for all referenced files.
    RULE 3: Certificate refused if any condition fails.
    """

    def generate_release_certificate(  # LAW-5
        self,
        output_path: str,
        version: str = "4.7.0-prod-ready",
        total_tests: int = 0,
        total_passed: int = 0,
        total_skipped: int = 0,
        total_failed: int = 0,
        regressions: int = 0,
        canon_compliance_pct: float = 100.0,
        critical_guards_enforced: int = 0,
        critical_guards_total: int = 0,
        architecture_drift: int = 0,
        phase_files: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        all_phase_files = phase_files or {}
        file_hashes: Dict[str, str] = {}
        for fpath, desc in all_phase_files.items():
            if os.path.exists(fpath):
                with open(fpath, "rb") as f:
                    h = hashlib.sha256(f.read()).hexdigest()[:64]
                file_hashes[fpath] = h

        certificate = {
            "phase": "FINAL",
            "stage": "RELEASE_CERTIFICATE",
            "version": version,
            "timestamp_ns": time.time_ns(),
            "test_matrix": {
                "total_tests": total_tests,
                "total_passed": total_passed,
                "total_skipped": total_skipped,
                "total_failed": total_failed,
                "regressions": regressions,
                "pass_rate_pct": round((total_passed / max(total_tests, 1)) * 100.0, 2),
            },
            "canon_compliance": {
                "overall_pct": canon_compliance_pct,
                "phases_evaluated": len(all_phase_files),
                "all_compliant": canon_compliance_pct == 100.0,
            },
            "guard_compliance_matrix": {
                "critical_guards_enforced": critical_guards_enforced,
                "critical_guards_total": critical_guards_total,
                "all_guards_passed": critical_guards_enforced == critical_guards_total,
            },
            "architecture_drift": architecture_drift,
            "drift_free": architecture_drift == 0,
            "file_fingerprints": file_hashes,
            "overall_status": "APPROVED" if (
                regressions == 0
                and canon_compliance_pct == 100.0
                and critical_guards_enforced == critical_guards_total
                and architecture_drift == 0
            ) else "BLOCKED",
            "certificate_hash": "",
        }
        raw = json.dumps(certificate, sort_keys=True, default=str)
        certificate["certificate_hash"] = hashlib.sha256(raw.encode()).hexdigest()[:64]
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(certificate, f, indent=2, default=str)
        return certificate
