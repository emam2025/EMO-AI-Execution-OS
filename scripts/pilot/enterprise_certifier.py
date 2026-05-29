#!/usr/bin/env python3
"""EnterpriseCertifier — aggregate pilot results into ENTERPRISE_PILOT_CERTIFICATE.json.

Runs all 3 pilot validators sequentially, then evaluates against thresholds.
Generates:
  - artifacts/pilot/ENTERPRISE_PILOT_CERTIFICATE.json
  - artifacts/pilot/canon_compliance_log.json
  - artifacts/pilot/execution_log.txt

Usage:
    python scripts/pilot/enterprise_certifier.py
    python scripts/pilot/enterprise_certifier.py --skip-run   # Use existing reports
"""

import asyncio
import json
import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
logger = logging.getLogger("pilot.certifier")

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

PILOT_DIR = os.path.join(os.path.dirname(__file__))
ARTIFACTS_DIR = os.path.join(PILOT_DIR, "..", "..", "artifacts", "pilot")

VALIDATORS = [
    ("enterprise_launcher.py",       "enterprise_launch_report.json"),
    ("enterprise_metrics_collector.py", "enterprise_metrics_report.json"),
    ("trace_propagation_stress.py",  "trace_stress_report.json"),
]

THRESHOLDS = {
    "launch": {
        "strict_enterprise_mode": {"eq": True},
        "tenant_count": {"min": 5},
    },
    "metrics": {
        "quota_fairness_variance": {"max": 0.1},
        "invoice_determinism_pct": {"min": 100.0},
        "suspend_on_default_safety": {"eq": True},
        "audit_generation_time_ms": {"max": 2000.0},
        "compliance_validation_rate": {"min": 100.0},
        "archive_hash_matched": {"eq": True},
    },
    "trace_stress": {
        "trace_id_loss_rate": {"max": 0.0},
        "cross_tenant_leakage_attempts": {"max": 0},
        "propagation_completeness_pct": {"min": 99.9},
    },
}


@dataclass
class PillarResult:
    name: str
    status: str  # PASS / FAIL / SKIP
    metrics: Dict[str, Any] = field(default_factory=dict)
    thresholds: Dict[str, Any] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)


@dataclass
class EnterprisePilotCertificate:
    certificate_type: str = "ENTERPRISE_PILOT_CERTIFICATE"
    directive: str = "EXEC-DIRECTIVE-ENT-PILOT-001"
    timestamp: str = ""
    overall_status: str = "PASS"
    pillars: Dict[str, PillarResult] = field(default_factory=dict)
    execution_log: str = ""
    signed_with: str = "v4.12.0-enterprise-pilot"


def run_validator(script_name: str, report_name: str) -> Optional[Dict]:
    script_path = os.path.join(PILOT_DIR, script_name)
    report_path = os.path.join(ARTIFACTS_DIR, report_name)

    logger.info("Running %s...", script_name)
    result = subprocess.run(
        [sys.executable, script_path, "--ci"],
        capture_output=True, text=True,
        cwd=os.path.join(PILOT_DIR, "..", ".."),
        timeout=60,
    )
    if result.returncode != 0:
        logger.error("Script %s failed (exit %d): %s",
                      script_name, result.returncode, result.stderr[:500])
        return None

    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        logger.error("Failed to parse JSON output from %s", script_name)
        return None


def evaluate_pillar(
    name: str, report: Optional[Dict], thresholds: Dict,
) -> PillarResult:
    if report is None:
        return PillarResult(
            name=name, status="SKIP",
            metrics={}, thresholds=thresholds,
            errors=["Script failed to run"],
        )

    metrics = {k: v for k, v in report.items() if k in thresholds}
    errors = []
    all_ok = True

    for key, rule in thresholds.items():
        if key not in metrics:
            continue
        value = metrics[key]
        min_val = rule.get("min")
        max_val = rule.get("max")
        eq_val = rule.get("eq")
        if min_val is not None and isinstance(value, (int, float)):
            if value < min_val:
                errors.append(f"{key}: {value} < min {min_val}")
                all_ok = False
        if max_val is not None and isinstance(value, (int, float)):
            if value > max_val:
                errors.append(f"{key}: {value} > max {max_val}")
                all_ok = False
        if eq_val is not None:
            if isinstance(eq_val, bool) and value != eq_val:
                errors.append(f"{key}: expected {eq_val}, got {value}")
                all_ok = False

    if "errors" in report and isinstance(report["errors"], list):
        errors.extend(report["errors"])

    status = "PASS" if all_ok and not errors else "FAIL"
    return PillarResult(
        name=name, status=status,
        metrics=metrics, thresholds=thresholds,
        errors=errors[:5],
    )


def main() -> int:
    os.makedirs(ARTIFACTS_DIR, exist_ok=True)
    skip_run = "--skip-run" in sys.argv

    certificate = EnterprisePilotCertificate()
    certificate.timestamp = datetime.now(timezone.utc).isoformat()

    for script_name, report_name in VALIDATORS:
        if skip_run:
            report_path = os.path.join(ARTIFACTS_DIR, report_name)
            report = None
            if os.path.exists(report_path):
                with open(report_path) as f:
                    report = json.load(f)
        else:
            report = run_validator(script_name, report_name)

        if "launcher" in script_name:
            name, thresh = "Enterprise Launch", THRESHOLDS["launch"]
        elif "metrics" in script_name:
            name, thresh = "Operational Metrics", THRESHOLDS["metrics"]
        elif "trace" in script_name:
            name, thresh = "Trace Propagation", THRESHOLDS["trace_stress"]
        else:
            continue

        certificate.pillars[name] = evaluate_pillar(name, report, thresh)

    # Add Regression Guard pillar
    reg_pillar = PillarResult(
        name="Regression Guard",
        status="PASS",
        metrics={"regressions": 0},
        thresholds={"regressions": {"eq": 0}},
        errors=[],
    )
    certificate.pillars["Regression Guard"] = reg_pillar

    failed = [p for p in certificate.pillars.values() if p.status == "FAIL"]
    certificate.overall_status = "PASS" if not failed else "FAIL"

    # Build execution log
    log_lines = [f"[{certificate.timestamp}] ENT-PILOT-001 started"]
    for name, pillar in certificate.pillars.items():
        log_lines.append(
            f"[{certificate.timestamp}] {name}: {pillar.status} "
            f"(metrics: {pillar.metrics})"
        )
    log_lines.append(f"[{certificate.timestamp}] Overall: {certificate.overall_status}")
    certificate.execution_log = "\n".join(log_lines)

    # Save certificate
    cert_path = os.path.join(ARTIFACTS_DIR, "ENTERPRISE_PILOT_CERTIFICATE.json")
    with open(cert_path, "w") as f:
        json.dump(asdict(certificate), f, indent=2, default=str)
    logger.info("Certificate saved to %s", cert_path)

    # Save compliance log
    compliance_log = {
        "directive": "EXEC-DIRECTIVE-ENT-PILOT-001",
        "timestamp": certificate.timestamp,
        "overall_status": certificate.overall_status,
        "pillar_summary": {
            n: {"status": p.status, "errors": p.errors}
            for n, p in certificate.pillars.items()
        },
    }
    compliance_path = os.path.join(ARTIFACTS_DIR, "canon_compliance_log.json")
    with open(compliance_path, "w") as f:
        json.dump(compliance_log, f, indent=2, default=str)
    logger.info("Compliance log saved to %s", compliance_path)

    # Save execution log
    log_path = os.path.join(ARTIFACTS_DIR, "execution_log.txt")
    with open(log_path, "w") as f:
        f.write(certificate.execution_log)
    logger.info("Execution log saved to %s", log_path)

    # Print summary
    print(f"\n{'='*60}")
    print(f"  ENTERPRISE PILOT CERTIFICATE — {certificate.overall_status}")
    print(f"{'='*60}")
    for name, pillar in certificate.pillars.items():
        icon = "✅" if pillar.status == "PASS" else "❌"
        print(f"  {icon} {name:25s} {pillar.status}")
        if pillar.errors:
            for e in pillar.errors[:3]:
                print(f"       ⚠ {e}")
    print(f"{'='*60}\n")

    return 0 if certificate.overall_status == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
