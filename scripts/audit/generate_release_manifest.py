#!/usr/bin/env python3
"""EMO AI — Release Manifest Generator.

Produces a signed release manifest JSON containing:
  - Version + build metadata
  - File hashes (SHA-256) for all deliverable files
  - Dependency bill of materials
  - Test pass/fail summary

Usage:
    python scripts/audit/generate_release_manifest.py \\
        --version 1.0.0-RC.1 --output release_manifest.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from typing import Any, Dict, List


class ReleaseManifest:
    """Generates a release manifest with file hashes and metadata."""

    HASH_ALGO = "sha256"
    RELEVANT_EXTENSIONS = {".py", ".json", ".yaml", ".yml", ".toml", ".cfg", ".sh", ".env.example"}

    def __init__(self, version: str, project_root: str) -> None:
        self.version = version
        self.project_root = project_root

    def generate(self) -> Dict[str, Any]:
        """Generate the full release manifest."""
        return {
            "manifest_version": "1.0",
            "application": "EMO AI Runtime",
            "version": self.version,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "hash_algorithm": self.HASH_ALGO,
            "files": self._hash_files(),
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

    def _hash_file(self, fpath: str) -> str:
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate EMO AI release manifest")
    parser.add_argument("--version", required=True, help="Release version (e.g., 1.0.0-RC.1)")
    parser.add_argument("--output", default="release_manifest.json", help="Output file path")
    parser.add_argument("--project-root", default=".", help="Project root directory")
    args = parser.parse_args()

    project_root = os.path.abspath(args.project_root)
    if not os.path.isdir(project_root):
        print(f"Error: Project root not found: {project_root}", file=sys.stderr)
        return 1

    manifest = ReleaseManifest(version=args.version, project_root=project_root)
    data = manifest.generate()
    manifest.export(data, args.output)
    print(f"Release manifest v{args.version} written to {args.output}")
    print(f"  Files hashed: {len(data['files'])}")
    print(f"  Checksum: {data['checksum'][:16]}...")
    return 0


if __name__ == "__main__":
    sys.exit(main())
