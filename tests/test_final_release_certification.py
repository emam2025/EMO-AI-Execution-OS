"""Phase FINAL — Release Certification Integration Tests.  # LAW-1 LAW-3 LAW-5 LAW-8 LAW-11 RULE-1 RULE-2 RULE-3 RULE-4 RULE-5

5 test groups covering Certification Aggregation, Baseline Freeze Integrity,
Release Validation, Certificate Generation, and Archive Completeness.

Ref: Canon LAW 1-27, RULE 1-5
Ref: DEVELOPER.md §16 (Architecture Canon)
"""

from __future__ import annotations

import json
import os
import tempfile

import pytest

from scripts.release.certification_aggregator import CertificationAggregator
from scripts.release.baseline_freezer import BaselineFreezer
from scripts.release.release_validator import ReleaseValidator
from scripts.release.certificate_engine import CertificateEngine


# ══════════════════════════════════════════════════════════════════
# Group 1: TestCertificationAggregation (4 tests)
# ══════════════════════════════════════════════════════════════════

class TestCertificationAggregation:
    """ICertificationAggregator: collect, verify, aggregate, publish."""

    def test_collect_phase_reports(self) -> None:
        aggregator = CertificationAggregator()
        results = aggregator.collect_phase_reports([])
        assert isinstance(results, dict)

    def test_collect_with_invalid_paths(self) -> None:
        aggregator = CertificationAggregator()
        results = aggregator.collect_phase_reports(["/nonexistent/path.json"])
        assert results["/nonexistent/path.json"] is False

    def test_verify_canon_empty(self) -> None:
        aggregator = CertificationAggregator()
        result = aggregator.verify_canon_100()
        assert result["total_phases"] == 0
        assert result["overall_compliant"] is False

    def test_aggregate_test_metrics_empty(self) -> None:
        aggregator = CertificationAggregator()
        metrics = aggregator.aggregate_test_metrics()
        assert metrics["total_tests"] == 0
        assert metrics["all_passing"] is True

    def test_publish_certificate_to_temp(self) -> None:
        aggregator = CertificationAggregator()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            path = f.name
        try:
            cert = aggregator.publish_certificate(path)
            assert cert["version"] == "4.7.0-prod-ready"
            assert cert["hash"] != ""
            assert os.path.exists(path)
            with open(path) as f:
                loaded = json.load(f)
            assert loaded["stage"] == "RELEASE_CERTIFICATION"
        finally:
            os.unlink(path)


# ══════════════════════════════════════════════════════════════════
# Group 2: TestBaselineFreezeIntegrity (4 tests)
# ══════════════════════════════════════════════════════════════════

class TestBaselineFreezeIntegrity:
    """IBaselineFreezer: lock, sign, freeze, archive."""

    def test_lock_dependencies_with_valid_files(self) -> None:
        freezer = BaselineFreezer()
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"test content")
            path = f.name
        try:
            result = freezer.lock_dependencies([path])
            assert result["all_dependencies_found"] is True
            assert result["dependency_count"] == 1
        finally:
            os.unlink(path)

    def test_lock_dependencies_with_missing_file(self) -> None:
        freezer = BaselineFreezer()
        result = freezer.lock_dependencies(["/nonexistent/file.txt"])
        assert result["all_dependencies_found"] is False
        assert "/nonexistent/file.txt" in result["dependency_details"]

    def test_generate_signing_manifest(self) -> None:
        freezer = BaselineFreezer()
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            manifest_path = f.name
        try:
            manifest = freezer.generate_signing_manifest(manifest_path, {"test.txt": "abc123"})
            assert manifest["version"] == "4.7.0-prod-ready"
            assert manifest["manifest_hash"] != ""
            assert os.path.exists(manifest_path)
        finally:
            os.unlink(manifest_path)

    def test_archive_artifacts(self) -> None:
        freezer = BaselineFreezer()
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            archive_path = f.name
        try:
            archive = freezer.archive_artifacts(archive_path, {"report.json": "passed"})
            assert archive["artifact_count"] == 1
            assert archive["version"] == "4.7.0-prod-ready"
            assert os.path.exists(archive_path)
        finally:
            os.unlink(archive_path)


# ══════════════════════════════════════════════════════════════════
# Group 3: TestReleaseValidation (4 tests)
# ══════════════════════════════════════════════════════════════════

class TestReleaseValidation:
    """IReleaseValidator: zero regressions, guards, drift, approve."""

    def test_validate_zero_regressions_passes(self) -> None:
        validator = ReleaseValidator()
        result = validator.validate_zero_regressions(
            known_failures=["test_fail_1"],
        )
        assert result["zero_regressions"] is True
        assert result["pre_existing_failures"] == 1

    def test_validate_zero_regressions_known_only(self) -> None:
        validator = ReleaseValidator()
        result = validator.validate_zero_regressions(known_failures=[])
        assert result["zero_regressions"] is True

    def test_check_guards_enforced_all_pass(self) -> None:
        validator = ReleaseValidator()
        result = validator.check_guards_enforced({
            "J3": {"G-C1": True, "G-C2": True, "G-C3": True},
            "FINAL": {"G-C0": True},
        })
        assert result["all_guards_enforced"] is True
        assert result["total_guards"] == 4

    def test_check_guards_enforced_some_fail(self) -> None:
        validator = ReleaseValidator()
        result = validator.check_guards_enforced({
            "J3": {"G-C1": True, "G-C3": False},
        })
        assert result["all_guards_enforced"] is False
        assert result["guards_failed"] == 1

    def test_verify_drift_free_passes(self) -> None:
        validator = ReleaseValidator()
        result = validator.verify_drift_free(0)
        assert result["drift_free"] is True

    def test_approve_release_all_conditions(self) -> None:
        validator = ReleaseValidator()
        result = validator.approve_release(
            zero_regressions=True,
            guards_enforced=True,
            drift_free=True,
            canon_compliant=True,
        )
        assert result["approved"] is True
        assert result["blocked_by"] == []

    def test_approve_release_blocked(self) -> None:
        validator = ReleaseValidator()
        result = validator.approve_release(
            zero_regressions=False,
            guards_enforced=False,
            drift_free=True,
            canon_compliant=False,
        )
        assert result["approved"] is False
        assert "zero_regressions" in result["blocked_by"]
        assert "guards_enforced" in result["blocked_by"]
        assert "canon_compliant" in result["blocked_by"]
        assert result["conditions_met"] == 1


# ══════════════════════════════════════════════════════════════════
# Group 4: TestCertificateGeneration (3 tests)
# ══════════════════════════════════════════════════════════════════

class TestCertificateGeneration:
    """CertificateEngine: RELEASE_CERTIFICATE.json generation."""

    def test_generate_release_certificate_full(self) -> None:
        engine = CertificateEngine()
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            cert = engine.generate_release_certificate(
                output_path=path,
                total_tests=2600,
                total_passed=2590,
                total_skipped=10,
                total_failed=0,
                regressions=0,
                canon_compliance_pct=100.0,
                critical_guards_enforced=45,
                critical_guards_total=45,
                architecture_drift=0,
                phase_files={"test.txt": "test file"},
            )
            assert cert["overall_status"] == "APPROVED"
            assert cert["test_matrix"]["total_tests"] == 2600
            assert cert["test_matrix"]["pass_rate_pct"] == 99.62
            assert cert["certificate_hash"] != ""
        finally:
            os.unlink(path)

    def test_generate_release_certificate_blocked(self) -> None:
        engine = CertificateEngine()
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            path = f.name
        try:
            cert = engine.generate_release_certificate(
                output_path=path,
                regressions=3,
                canon_compliance_pct=85.0,
                critical_guards_enforced=10,
                critical_guards_total=15,
                architecture_drift=2,
            )
            assert cert["overall_status"] == "BLOCKED"
            assert cert["test_matrix"]["regressions"] == 3
            assert cert["canon_compliance"]["all_compliant"] is False
        finally:
            os.unlink(path)

    def test_generate_release_certificate_file_fingerprints(self) -> None:
        engine = CertificateEngine()
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tmp:
            tmp.write(b"hello world")
            fpath = tmp.name
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            out_path = f.name
        try:
            cert = engine.generate_release_certificate(
                output_path=out_path,
                total_tests=100,
                total_passed=100,
                phase_files={fpath: "test fixture"},
            )
            assert fpath in cert["file_fingerprints"]
            assert len(cert["file_fingerprints"][fpath]) == 64  # SHA-256
        finally:
            os.unlink(fpath)
            os.unlink(out_path)


# ══════════════════════════════════════════════════════════════════
# Group 5: TestArchiveCompleteness (3 tests)
# ══════════════════════════════════════════════════════════════════

class TestArchiveCompleteness:
    """Archive completeness — all artifacts present."""

    def test_aggregator_has_required_methods(self) -> None:
        agg = CertificationAggregator()
        assert hasattr(agg, "collect_phase_reports")
        assert hasattr(agg, "verify_canon_100")
        assert hasattr(agg, "aggregate_test_metrics")
        assert hasattr(agg, "publish_certificate")

    def test_freezer_has_required_methods(self) -> None:
        fz = BaselineFreezer()
        assert hasattr(fz, "lock_dependencies")
        assert hasattr(fz, "generate_signing_manifest")
        assert hasattr(fz, "freeze_codegraph_hash")
        assert hasattr(fz, "archive_artifacts")

    def test_validator_has_required_methods(self) -> None:
        val = ReleaseValidator()
        assert hasattr(val, "validate_zero_regressions")
        assert hasattr(val, "check_guards_enforced")
        assert hasattr(val, "verify_drift_free")
        assert hasattr(val, "approve_release")
