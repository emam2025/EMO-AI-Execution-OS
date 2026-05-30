"""memory_certifier.py — Generates MEMORY_OPERATIONAL_CERTIFICATE.json.

EXEC-DIRECTIVE-L-VAL-001 Task 4:
  Runs all 3 validation scripts, evaluates thresholds, generates certificate.

Acceptance thresholds:
  - hash_match_rate ≥ 99.9%
  - cross_tenant_context_leakage = 0
  - cascade_containment_rate = 100%
  - 20/20 tests PASS, 0 regressions
"""

from __future__ import annotations

import asyncio
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict

from scripts.validation.memory_load_injector import run_load_test
from scripts.validation.deterministic_replay_validator import run_determinism_test
from scripts.validation.memory_isolation_stress import run_isolation_test

SCRIPT_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = SCRIPT_DIR.parent.parent.resolve()

THRESHOLDS = {
    "hash_match_rate": {"min": 99.9, "direction": "min"},
    "cross_tenant_context_leakage": {"max": 0, "direction": "max"},
    "cascade_containment_rate": {"min": 100.0, "direction": "min"},
    "throughput_ops_sec": {"min": 10.0, "direction": "min"},
}

PILLARS = [
    "load_injection",
    "deterministic_replay",
    "isolation_stress",
    "integration_tests",
]


def _pillar_pass(result: Dict[str, Any], pillar: str) -> bool:
    if pillar == "integration_tests":
        return result.get("passed", False)
    metrics = result.get("metrics", {})
    if pillar == "load_injection":
        return metrics.get("throughput_ops_sec", 0) >= 10.0
    if pillar == "deterministic_replay":
        return metrics.get("hash_match_rate_pass", False)
    if pillar == "isolation_stress":
        return metrics.get("cascade_containment_pass", False)
    return False


async def run_certification() -> Dict[str, Any]:
    """Execute all validations and generate certificate."""
    ts = int(time.time())

    # Pillar 1: Load Injection
    load_result = await run_load_test()

    # Pillar 2: Deterministic Replay
    det_result = await run_determinism_test()

    # Pillar 3: Isolation Stress
    iso_result = await run_isolation_test()

    # Pillar 4: Integration tests
    pytest_result = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/test_memory_operational_validation.py",
         "-v", "--tb=short"],
        capture_output=True, text=True, cwd=str(PROJECT_ROOT),
    )
    tests_passed = pytest_result.returncode == 0

    results: Dict[str, Any] = {
        "load_injection": load_result,
        "deterministic_replay": det_result,
        "isolation_stress": iso_result,
        "integration_tests": {
            "exit_code": pytest_result.returncode,
            "passed": tests_passed,
            "output": pytest_result.stdout[-500:] if pytest_result.stdout else "",
            "errors": pytest_result.stderr[-500:] if pytest_result.stderr else "",
        },
    }

    pillar_results: Dict[str, bool] = {}
    all_pass = True
    for pillar in PILLARS:
        p = _pillar_pass(results[pillar], pillar)
        pillar_results[pillar] = p
        if not p:
            all_pass = False

    # Aggregate metrics
    hash_rate = det_result.get("metrics", {}).get("hash_match_rate", 0)
    leakage = iso_result.get("metrics", {}).get("cross_tenant_context_leakage", -1)
    cascade_rate = iso_result.get("metrics", {}).get("cascade_containment_rate", 0)
    throughput = load_result.get("metrics", {}).get("throughput_ops_sec", 0)

    threshold_results = {}
    for name, cfg in THRESHOLDS.items():
        if name == "hash_match_rate":
            val = hash_rate
        elif name == "cross_tenant_context_leakage":
            val = leakage
        elif name == "cascade_containment_rate":
            val = cascade_rate
        elif name == "throughput_ops_sec":
            val = throughput
        else:
            val = 0

        if cfg["direction"] == "min":
            passed = val >= cfg["min"]
        else:
            passed = val <= cfg["max"]
        threshold_results[name] = {
            "value": val,
            "threshold": cfg,
            "passed": passed,
        }
        if not passed:
            all_pass = False

    certificate = {
        "certificate": "MEMORY_OPERATIONAL_CERTIFICATE",
        "directive": "EXEC-DIRECTIVE-L-VAL-001",
        "signed": "v4.13.0-memory-validated",
        "timestamp_ns": time.time_ns(),
        "overall_status": "PASS" if all_pass else "FAIL",
        "pillars": pillar_results,
        "thresholds": threshold_results,
        "details": {
            "throughput_ops_sec": throughput,
            "hash_match_rate_pct": hash_rate,
            "cross_tenant_leakage": leakage,
            "cascade_containment_rate_pct": cascade_rate,
            "tests_20_20": tests_passed,
        },
    }

    # Write certificate
    cert_dir = PROJECT_ROOT / "artifacts" / "validation" / "memory"
    cert_dir.mkdir(parents=True, exist_ok=True)
    cert_path = cert_dir / "MEMORY_OPERATIONAL_CERTIFICATE.json"
    cert_path.write_text(json.dumps(certificate, indent=2, default=str))

    print(f"Certificate written to {cert_path}")
    print(f"Overall: {certificate['overall_status']}")

    return certificate


if __name__ == "__main__":
    cert = asyncio.run(run_certification())
    print(json.dumps(cert, indent=2, default=str))
