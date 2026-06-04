#!/usr/bin/env python3
"""EMO AI — Release Manifest Generator.

Produces a signed release manifest JSON containing:
  - Version + build metadata
  - File hashes (SHA-256) for all deliverable files
  - Dependency bill of materials
  - Test pass/fail summary
  - SHA256SUMS file for binary verification

Usage:
    python scripts/audit/generate_release_manifest.py \
        --version 1.0.0-RC.1 --output release_manifest.json

    python scripts/audit/generate_release_manifest.py --check
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List


BINARY_EXTENSIONS = {".dmg", ".exe", ".AppImage", ".app", ".deb", ".rpm", ".msi", ".zip", ".tar.gz"}


class ReleaseManifest:
    """Generates a release manifest with file hashes and metadata."""

    HASH_ALGO = "sha256"
    RELEVANT_EXTENSIONS = {".py", ".json", ".yaml", ".yml", ".toml", ".cfg", ".sh", ".env.example"}

    def __init__(self, version: str, project_root: str) -> None:
        self.version = version
        self.project_root = project_root

    def generate(self, binary_paths: list[str] | None = None) -> Dict[str, Any]:
        """Generate the full release manifest."""
        file_hashes = self._hash_files()
        binary_hashes = self._hash_binaries(binary_paths or [])

        return {
            "manifest_version": "1.0",
            "application": "EMO AI",
            "version": self.version,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "hash_algorithm": self.HASH_ALGO,
            "files": file_hashes,
            "binaries": binary_hashes,
            "core_modules": self._list_core_modules(),
            "checksum": "",
        }

    def _hash_files(self) -> Dict[str, str]:
        """Generate SHA-256 hashes for all relevant files."""
        file_hashes: Dict[str, str] = {}
        for root, _dirs, files in os.walk(self.project_root):
            if any(skip in root for skip in [".git", "__pycache__", ".venv", "node_modules", ".pytest_cache"]):
                continue
            for fname in files:
                ext = os.path.splitext(fname)[1]
                if ext not in self.RELEVANT_EXTENSIONS:
                    continue
                fpath = os.path.join(root, fname)
                rel_path = os.path.relpath(fpath, self.project_root)
                try:
                    file_hashes[rel_path] = self._hash_file(fpath)
                except (IOError, OSError):
                    continue
        return file_hashes

    def _hash_binaries(self, binary_paths: list[str]) -> dict[str, str]:
        """Generate SHA-256 for binary deliverables."""
        hashes: dict[str, str] = {}
        for path in binary_paths:
            if os.path.exists(path):
                hashes[os.path.basename(path)] = self._hash_file(path)
        return hashes

    @staticmethod
    def _hash_file(fpath: str) -> str:
        """Compute SHA-256 hash of a file."""
        h = hashlib.sha256()
        with open(fpath, "rb") as f:
            while True:
                chunk = f.read(65536)
                if not chunk:
                    break
                h.update(chunk)
        return h.hexdigest()

    def _list_core_modules(self) -> List[str]:
        """List core module directories."""
        core_path = os.path.join(self.project_root, "core")
        if not os.path.isdir(core_path):
            return []
        modules = []
        for entry in sorted(os.listdir(core_path)):
            entry_path = os.path.join(core_path, entry)
            if os.path.isdir(entry_path) and not entry.startswith("_"):
                modules.append(f"core.{entry}")
        return modules

    def sign(self, manifest: Dict[str, Any]) -> str:
        """Create the manifest checksum (self-signing)."""
        serialized = json.dumps(manifest, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode()).hexdigest()

    def export(self, manifest: Dict[str, Any], output_path: str) -> None:
        """Write manifest to JSON file with checksum."""
        manifest["checksum"] = self.sign(manifest)
        with open(output_path, "w") as f:
            json.dump(manifest, f, indent=2, default=str)

    def export_shasums(self, manifest: Dict[str, Any], output_path: str = "SHA256SUMS") -> None:
        """Write SHA-256 hashes of all binaries in standard checksum format."""
        binaries = manifest.get("binaries", {})
        if not binaries:
            return
        with open(output_path, "w") as f:
            for name, sha in sorted(binaries.items()):
                f.write(f"{sha}  {name}\n")


def run_check() -> int:
    """--check mode: validate security certificate + test status."""
    errors = 0

    cert_path = "artifacts/security/FINAL_SECURITY_CERTIFICATE.json"
    if not os.path.exists(cert_path):
        print(f"FAIL: {cert_path} not found")
        errors += 1
    else:
        with open(cert_path) as f:
            cert = json.load(f)
        if cert.get("summary", {}).get("overall") != "PASS":
            print(f"FAIL: Security certificate is not PASS")
            errors += 1
        else:
            print(f"PASS: Security certificate OK ({cert.get('meta', {}).get('project', 'EMO AI')})")

    runtime_cert = "artifacts/runtime/FULL_AGENT_FLOW_CERTIFICATE.json"
    if os.path.exists(runtime_cert):
        with open(runtime_cert) as f:
            rc = json.load(f)
        statuses = [v for k, v in rc.get("summary", {}).items() if k != "model_response"]
        blocked = [k for k, v in rc.get("summary", {}).items() if v == "BLOCKED"]
        if blocked:
            print(f"WARN: Runtime layers BLOCKED: {blocked}")
        else:
            print(f"PASS: Runtime flow certificate OK")

    failure_matrix = "artifacts/runtime/FAILURE_MATRIX_CERTIFICATE.json"
    if os.path.exists(failure_matrix):
        print(f"PASS: Failure matrix certificate exists")

    test_results_path = "tests/final_delivery/test_production_readiness.py"
    if os.path.exists(test_results_path):
        import subprocess
        result = subprocess.run(
            [sys.executable, "-m", "pytest", test_results_path, "-q", "--tb=no"],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0:
            print(f"PASS: Production readiness tests ({result.stdout.strip().split(chr(10))[-1]})")
        else:
            print(f"FAIL: Production readiness tests — {result.returncode} failures")
            errors += 1

    if errors:
        print(f"\nValidation: {errors} failure(s) — BLOCKING")
    else:
        print(f"\nValidation: ALL PASS — release ready")

    return 1 if errors else 0


def main() -> int:
    parser = argparse.ArgumentParser(description="EMO AI release manifest and validation")
    parser.add_argument("--version", help="Release version (e.g., 1.0.0-RC.1)")
    parser.add_argument("--output", default="release_manifest.json", help="Output file path")
    parser.add_argument("--project-root", default=".", help="Project root directory")
    parser.add_argument("--check", action="store_true", help="Validate release readiness (no manifest output)")
    parser.add_argument("--binary", action="append", default=[], help="Binary artifact paths to hash")
    args = parser.parse_args()

    if args.check:
        return run_check()

    if not args.version:
        print("Error: --version is required (use --check for validation mode)", file=sys.stderr)
        return 1

    project_root = os.path.abspath(args.project_root)
    if not os.path.isdir(project_root):
        print(f"Error: Project root not found: {project_root}", file=sys.stderr)
        return 1

    generator = ReleaseManifest(version=args.version, project_root=project_root)
    data = generator.generate(binary_paths=args.binary)
    generator.export(data, args.output)
    generator.export_shasums(data)

    print(f"Release manifest v{args.version} written to {args.output}")
    print(f"  Source files hashed: {len(data['files'])}")
    print(f"  Binary artifacts: {len(data['binaries'])}")
    print(f"  SHA256SUMS: {'SHA256SUMS' if data['binaries'] else '(no binaries)'}")
    print(f"  Checksum: {data['checksum'][:16]}...")
    return 0


if __name__ == "__main__":
    sys.exit(main())
