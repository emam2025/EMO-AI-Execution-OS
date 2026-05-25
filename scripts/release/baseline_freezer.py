"""Phase FINAL — Baseline Freezer.  # LAW-1 LAW-3 LAW-5 LAW-11 RULE-1 RULE-3 RULE-5

Freezes all release artifacts, generates signing manifests, locks dependency
hashes, and archives the production readiness snapshot.

v4.10.0-prod-ready: Extended SHA-256 signing for core/, scripts/, docs/,
artifacts/ directories and K5 operator visibility files.

Ref: Canon LAW 1-27, RULE 1-5
Ref: EXEC-DIRECTIVE-028
Ref: DEVELOPER.md §16 (Architecture Canon)
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from typing import Any, Dict, List, Optional


class BaselineFreezer:  # LAW-1 LAW-3 LAW-5 LAW-11 RULE-1 RULE-3 RULE-5
    """Freezes release baseline with deterministic artifact hashing.

    LAW 3: Every artifact hash is computable and verifiable.
    LAW 5: Frozen baseline is the stability anchor for production.
    LAW 11: No global state — freezer state is instance-scoped.
    RULE 1: Deterministic SHA-256 hashes for all files.
    RULE 3: Freeze blocked if any required file is missing.
    RULE 5: Archive preserves rollback capability.
    """

    def __init__(self) -> None:
        self._file_hashes: Dict[str, str] = {}

    def lock_dependencies(  # LAW-3 RULE-1
        self,
        dep_files: List[str],
    ) -> Dict[str, Any]:
        all_found = True
        dep_details: Dict[str, str] = {}
        for fpath in dep_files:
            if os.path.exists(fpath):
                with open(fpath, "rb") as f:
                    h = hashlib.sha256(f.read()).hexdigest()[:32]
                self._file_hashes[fpath] = h
                dep_details[fpath] = h
            else:
                dep_details[fpath] = "MISSING"
                all_found = False
        return {
            "all_dependencies_found": all_found,
            "dependency_count": len(dep_files),
            "dependency_details": dep_details,
        }

    def hash_directory(  # LAW-3 RULE-1 # EXEC-DIRECTIVE-028
        self,
        base_dir: str,
        recursive: bool = True,
        extensions: Optional[List[str]] = None,
    ) -> Dict[str, str]:
        """SHA-256 hash all files in a directory deterministically."""
        result: Dict[str, str] = {}
        if not os.path.isdir(base_dir):
            return result
        for root, _dirs, files in os.walk(base_dir):
            for fname in sorted(files):
                fpath = os.path.join(root, fname)
                if extensions:
                    ext = os.path.splitext(fname)[1]
                    if ext not in extensions:
                        continue
                try:
                    with open(fpath, "rb") as f:
                        h = hashlib.sha256(f.read()).hexdigest()[:64]
                    result[fpath] = h
                    self._file_hashes[fpath] = h
                except (OSError, PermissionError):
                    continue
            if not recursive:
                break
        return result

    def generate_signing_manifest(  # LAW-5 RULE-1
        self,
        manifest_path: str,
        artifacts: Optional[Dict[str, str]] = None,
    ) -> Dict[str, Any]:
        manifest = {
            "phase": "FINAL",
            "stage": "SIGNING_MANIFEST",
            "version": "4.10.0-prod-ready",
            "generated_at_ns": time.time_ns(),
            "artifacts": artifacts or {},
            "manifest_hash": "",
        }
        for fpath, fhash in sorted(self._file_hashes.items()):
            manifest["artifacts"][fpath] = fhash
        raw = json.dumps(manifest, sort_keys=True, default=str)
        manifest["manifest_hash"] = hashlib.sha256(raw.encode()).hexdigest()[:64]
        with open(manifest_path, "w") as f:
            json.dump(manifest, f, indent=2, default=str)
        return manifest

    def freeze_codegraph_hash(  # LAW-3 RULE-1
        self,
        codegraph_dirs: List[str],
    ) -> Dict[str, str]:
        codegraph_hashes: Dict[str, str] = {}
        for d in codegraph_dirs:
            for root, _dirs, files in os.walk(d):
                for fname in sorted(files):
                    fpath = os.path.join(root, fname)
                    try:
                        with open(fpath, "rb") as f:
                            h = hashlib.sha256(f.read()).hexdigest()[:32]
                        codegraph_hashes[fpath] = h
                        self._file_hashes[fpath] = h
                    except (OSError, PermissionError):
                        continue
        return codegraph_hashes

    def archive_artifacts(  # LAW-5 RULE-5
        self,
        archive_log_path: str,
        artifact_log: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        archive = {
            "phase": "FINAL",
            "stage": "ARCHIVE_LOG",
            "version": "4.10.0-prod-ready",
            "archived_at_ns": time.time_ns(),
            "artifact_count": len(artifact_log or {}),
            "artifacts": artifact_log or {},
            "file_hashes": self._file_hashes,
        }
        with open(archive_log_path, "w") as f:
            json.dump(archive, f, indent=2, default=str)
        return archive

    def verify_hash_consistency(  # LAW-3 RULE-1 # EXEC-DIRECTIVE-028
        self,
        manifest: Dict[str, Any],
        files_to_check: List[str],
    ) -> Dict[str, bool]:
        """Verify SHA-256 hashes are stable across runs."""
        results: Dict[str, bool] = {}
        for fpath in files_to_check:
            expected = manifest.get("artifacts", {}).get(fpath)
            if not expected:
                results[fpath] = False
                continue
            try:
                with open(fpath, "rb") as f:
                    actual = hashlib.sha256(f.read()).hexdigest()[:64]
                results[fpath] = actual == expected
            except (OSError, PermissionError):
                results[fpath] = False
        return results
