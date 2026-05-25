"""Persistent store for drift snapshots."""

import json
import os
from typing import Any, Dict, List, Optional


class DriftStore:
    """Stores and retrieves DriftSnapshots as JSON files.

    Each snapshot is stored at ``<base_path>/<version>.json``.
    """

    def __init__(self, base_path: Optional[str] = None) -> None:
        if base_path is None:
            base_path = os.path.join(
                "artifacts", "codegraph", "drift",
            )
        self._base_path = os.path.abspath(base_path)
        os.makedirs(self._base_path, exist_ok=True)

    def save(self, snapshot: Dict[str, Any]) -> str:
        version = snapshot.get("version", "unknown")
        file_path = os.path.join(self._base_path, f"{version}.json")
        with open(file_path, "w") as f:
            json.dump(snapshot, f, indent=2)
        return file_path

    def load(self, version: str) -> Optional[Dict[str, Any]]:
        file_path = os.path.join(self._base_path, f"{version}.json")
        if not os.path.exists(file_path):
            return None
        with open(file_path) as f:
            return json.load(f)

    def list_versions(self) -> List[str]:
        files = sorted(os.listdir(self._base_path))
        return [f.replace(".json", "") for f in files if f.endswith(".json")]

    def latest(self) -> Optional[Dict[str, Any]]:
        versions = self.list_versions()
        if not versions:
            return None
        return self.load(versions[-1])

    def clear(self) -> None:
        for f in os.listdir(self._base_path):
            if f.endswith(".json"):
                os.remove(os.path.join(self._base_path, f))
