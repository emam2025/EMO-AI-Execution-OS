from __future__ import annotations

import hashlib
from typing import List, Sequence


def make_node_id(path: str, type_name: str, name: str) -> str:
    """Deterministic node ID: sha256(path + type + name).

    This is the ONLY allowed ID generation function.
    """
    raw = f"{path}::{type_name}::{name}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def stable_hash(content: str) -> str:
    """Deterministic content checksum (no timestamps)."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()[:16]


def sort_files(files: List[str]) -> List[str]:
    """Alphabetical sort — MUST be applied before any processing."""
    return sorted(files)


def sort_edges(
    edges: List[tuple],
) -> List[tuple]:
    """Edge sort key: (from_id, to_id, edge_type)."""
    return sorted(edges, key=lambda e: (e[0], e[1], str(e[2])))


def sort_nodes(nodes: List[str]) -> List[str]:
    return sorted(nodes)
