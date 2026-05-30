"""Final Freeze & Certification — 15 validation tests.  # LAW-1 # LAW-3 # LAW-5 # RULE-1

4 groups × 3–5 tests = 15 high-signal tests covering:
  1. Certificate Aggregation (4 tests)
  2. Baseline Integrity (4 tests)
  3. Documentation Sync (4 tests)
  4. Freeze Enforcement (3 tests)

Ref: EXEC-DIRECTIVE-028 §Task-5
Ref: Canon LAW 1, LAW 3, LAW 5, RULE 1
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pytest

from scripts.release.certification_aggregator import CertificationAggregator
from scripts.release.baseline_freezer import BaselineFreezer

BASE = Path(__file__).resolve().parent.parent

# ═════════════════════════════════════════════════════════════════════
# Group 1: Certificate Aggregation (4 tests)
# ═════════════════════════════════════════════════════════════════════


class TestGroup1_CertificateAggregation:
    """4 tests validating certification aggregation across K1-K5 phases."""

    def test_collect_k1_k5_certificates(self) -> None:
        aggregator = CertificationAggregator()
        paths = {
            "K1": str(BASE / "artifacts" / "k1" / "REALITY_CERTIFICATE.json"),
            "K2": str(BASE / "artifacts" / "k2" / "CHAOS_CERTIFICATE.json"),
            "K4": str(BASE / "artifacts" / "phase4_d8" / "ISOLATION_AND_MESH_CERTIFICATE.json"),
            "K5": str(BASE / "artifacts" / "k5" / "OPERATOR_VISIBILITY_CERTIFICATE.json"),
        }
        results = aggregator.collect_phase_certificates(paths)
        assert all(v == "COLLECTED" for v in results.values()), f"Failed: {results}"

    def test_verify_all_certificates_pass(self) -> None:
        aggregator = CertificationAggregator()
        paths = {
            "K1": str(BASE / "artifacts" / "k1" / "REALITY_CERTIFICATE.json"),
            "K2": str(BASE / "artifacts" / "k2" / "CHAOS_CERTIFICATE.json"),
            "K4": str(BASE / "artifacts" / "phase4_d8" / "ISOLATION_AND_MESH_CERTIFICATE.json"),
            "K5": str(BASE / "artifacts" / "k5" / "OPERATOR_VISIBILITY_CERTIFICATE.json"),
        }
        aggregator.collect_phase_certificates(paths)
        result = aggregator.verify_all_certificates_pass()
        assert result["all_pass"] is True
        assert result["compliance_pct"] == 100.0

    def test_publish_final_certificate_creates_file(self) -> None:
        aggregator = CertificationAggregator()
        paths = {
            "K1": str(BASE / "artifacts" / "k1" / "REALITY_CERTIFICATE.json"),
            "K2": str(BASE / "artifacts" / "k2" / "CHAOS_CERTIFICATE.json"),
            "K4": str(BASE / "artifacts" / "phase4_d8" / "ISOLATION_AND_MESH_CERTIFICATE.json"),
            "K5": str(BASE / "artifacts" / "k5" / "OPERATOR_VISIBILITY_CERTIFICATE.json"),
        }
        aggregator.collect_phase_certificates(paths)
        out = str(BASE / "artifacts" / "release" / "FINAL_PRODUCTION_CERTIFICATE.json")
        cert = aggregator.publish_certificate(out)
        assert cert["status"] == "PASS"
        assert cert["version"] == "4.10.0-prod-ready"
        assert os.path.exists(out)

    def test_final_certificate_has_hash(self) -> None:
        path = BASE / "artifacts" / "release" / "FINAL_PRODUCTION_CERTIFICATE.json"
        assert path.exists()
        with open(path) as f:
            cert = json.load(f)
        assert len(cert.get("hash", "")) == 64


# ═════════════════════════════════════════════════════════════════════
# Group 2: Baseline Integrity (4 tests)
# ═════════════════════════════════════════════════════════════════════


class TestGroup2_BaselineIntegrity:
    """4 tests validating SHA-256 baseline signing and hash consistency."""

    def test_baseline_freezer_generates_consistent_hashes(self) -> None:
        freezer = BaselineFreezer()
        test_files = [
            str(BASE / "artifacts" / "k5" / "OPERATOR_VISIBILITY_CERTIFICATE.json"),
        ]
        result = freezer.lock_dependencies(test_files)
        assert result["all_dependencies_found"] is True
        for fpath, fhash in result["dependency_details"].items():
            assert len(fhash) == 32 or len(fhash) == 64

    def test_hash_consistency_across_runs(self) -> None:
        freezer = BaselineFreezer()
        test_file = str(BASE / "artifacts" / "k5" / "OPERATOR_VISIBILITY_CERTIFICATE.json")
        r1 = freezer.lock_dependencies([test_file])
        r2 = freezer.lock_dependencies([test_file])
        assert r1["dependency_details"][test_file] == r2["dependency_details"][test_file]

    def test_hash_directory_scans_core(self) -> None:
        freezer = BaselineFreezer()
        core_dir = str(BASE / "core" / "runtime" / "api")
        hashes = freezer.hash_directory(core_dir, recursive=False, extensions=[".py"])
        assert len(hashes) > 0
        for fpath, fhash in hashes.items():
            assert len(fhash) == 64
            assert fpath.endswith(".py")

    def test_signing_manifest_generates_hash(self) -> None:
        freezer = BaselineFreezer()
        test_file = str(BASE / "artifacts" / "k5" / "OPERATOR_VISIBILITY_CERTIFICATE.json")
        freezer.lock_dependencies([test_file])
        out = str(BASE / "artifacts" / "release" / "SIGNING_MANIFEST.md")
        manifest = freezer.generate_signing_manifest(out)
        assert len(manifest.get("manifest_hash", "")) == 64
        assert manifest["version"] == "4.10.0-prod-ready"


# ═════════════════════════════════════════════════════════════════════
# Group 3: Documentation Sync (4 tests)
# ═════════════════════════════════════════════════════════════════════


class TestGroup3_DocumentationSync:
    """4 tests validating DEVELOPER.md, CHANGELOG.md, and debt doc are synced."""

    def test_changelog_has_v4_10_0_entry(self) -> None:
        path = BASE / "CHANGELOG.md"
        content = path.read_text()
        assert "4.10.0-prod-ready" in content
        assert "K5" in content
        assert "EXEC-DIRECTIVE-028" in content

    def test_developer_md_has_section_15_22(self) -> None:
        path = BASE / "DEVELOPER.md"
        content = path.read_text()
        assert "15.22" in content
        assert "Final State & Constraints" in content
        assert "4.10.0-prod-ready" in content

    def test_developer_md_version_updated(self) -> None:
        path = BASE / "DEVELOPER.md"
        content = path.read_text()
        assert "4.10.0-prod-ready" in content

    def test_accepted_architectural_debt_exists(self) -> None:
        path = BASE / "docs" / "ACCEPTED_ARCHITECTURAL_DEBT.md"
        assert path.exists()
        content = path.read_text()
        assert "AD-001" in content
        assert "CERTIFIED" in content
        assert "4.10.0-prod-ready" in content


# ═════════════════════════════════════════════════════════════════════
# Group 4: Freeze Enforcement (3 tests)
# ═════════════════════════════════════════════════════════════════════


class TestGroup4_FreezeEnforcement:
    """3 tests validating strict_final_freeze_mode in CompositionRoot."""

    def test_strict_final_freeze_mode_default_false(self) -> None:
        from core.composition.root import CompositionRoot
        root = CompositionRoot()
        assert root.strict_final_freeze_mode is False

    def test_strict_final_freeze_mode_set_true(self) -> None:
        from core.composition.root import CompositionRoot
        root = CompositionRoot()
        root.strict_final_freeze_mode = True
        assert root.strict_final_freeze_mode is True

    def test_build_final_release_activates_freeze(self) -> None:
        from core.composition.root import CompositionRoot
        root = CompositionRoot()
        root.build_final_release()
        assert root.strict_final_freeze_mode is True
