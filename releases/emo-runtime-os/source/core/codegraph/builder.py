from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Dict, List, Optional, Set

from .graph import CodeGraph, Edge, EdgeType, Node, NodeType
from .parser import ParsedFile, discover_files, parse_file
from .analyzer import (
    AnalysisResult,
    analyze_parsed_file,
    compute_complexity,
    compute_risk_score,
)
from .determinism import make_node_id, sort_edges, stable_hash


def build_module_map(files: List[str]) -> Dict[str, str]:
    """Build a map of module name → file path for import resolution.

    Maps both short names (stem) and relative dotted paths from the
    repository root (e.g. core.interfaces.execution).

    On stem conflicts (same name in different directories), the
    shortest path wins (closest to repo root), then alphabetical.
    """
    module_map: Dict[str, str] = {}
    for fpath in files:
        p = Path(fpath)
        stem = p.stem

        # Stem mapping — prefer shorter paths on conflict
        if stem not in module_map:
            module_map[stem] = fpath
        else:
            existing = len(Path(module_map[stem]).parts)
            candidate = len(p.parts)
            if candidate < existing or (candidate == existing and fpath < module_map[stem]):
                module_map[stem] = fpath

        # Relative dotted path from repo root
        rel_suffix = p.relative_to(p.anchor).with_suffix("")
        rel_parts = rel_suffix.parts

        try:
            src_idx = rel_parts.index("core")
            dotted = ".".join(rel_parts[src_idx:])
            module_map[dotted] = fpath
            # Also register without the top-level package prefix
            # so intra-package imports resolve (e.g. models.dag, interfaces.*)
            if len(rel_parts) > src_idx + 1:
                sub = ".".join(rel_parts[src_idx + 1:])
                if sub not in module_map:
                    module_map[sub] = fpath
        except ValueError:
            module_map[".".join(rel_parts)] = fpath

    return module_map


def build_codegraph(
    root_dir: str,
    include_docs: bool = True,
) -> CodeGraph:
    """Full 5-stage pipeline.

    Stage 1 — Parse Layer:   discover + parse files
    Stage 2 — Analysis Layer: semantic dependency detection
    Stage 3 — Compilation:    build nodes + edges, resolve references
    Stage 4 — Optimization:   dedup, merge, compute scores
    Stage 5 — Persistence:    caller's responsibility (use storage.save)
    """
    graph = CodeGraph()
    graph.generated_at = time.time()

    # ── Stage 1: Parse Layer ──────────────────────────────────────
    files = discover_files(root_dir)
    if include_docs:
        files = _include_doc_files(root_dir, files)

    parsed_files: Dict[str, ParsedFile] = {}
    for fpath in files:
        parsed = parse_file(fpath)
        parsed_files[fpath] = parsed

    module_map = build_module_map(files)

    # ── Stage 2: Analysis Layer ───────────────────────────────────
    analysis: Dict[str, AnalysisResult] = {}
    for fpath, parsed in parsed_files.items():
        analysis[fpath] = analyze_parsed_file(parsed, module_map)

    # ── Stage 3: Graph Compilation Layer ──────────────────────────
    _compile_nodes(graph, parsed_files)
    _compile_edges(graph, parsed_files, analysis)

    # Resolve reverse dependencies
    _resolve_reverse_deps(graph)

    # ── Stage 4: Optimization Layer ───────────────────────────────
    _optimize(graph, parsed_files)

    # ── Checksum ──────────────────────────────────────────────────
    raw = str(sorted(graph.nodes.keys())) + str([e.sort_key() for e in graph.sorted_edges()])
    graph.checksum = stable_hash(raw)

    return graph


# ── Stage 3 helpers ──────────────────────────────────────────────────────────


def _compile_nodes(graph: CodeGraph, parsed_files: Dict[str, ParsedFile]) -> None:
    for fpath, parsed in parsed_files.items():
        # FILE node
        ftype = _classify_file_type(fpath)
        fid = make_node_id(fpath, "FILE", Path(fpath).name)
        graph.add_node(Node(
            id=fid,
            type=NodeType.FILE,
            name=Path(fpath).name,
            path=fpath,
            metadata={"file_type": ftype},
        ))

        # CLASS nodes
        for cls_name, lineno in parsed.classes:
            cid = make_node_id(fpath, "CLASS", cls_name)
            graph.add_node(Node(
                id=cid,
                type=NodeType.CLASS,
                name=cls_name,
                path=fpath,
                metadata={"lineno": lineno},
            ))

        # FUNCTION nodes
        for fn_name, lineno in parsed.functions:
            fnid = make_node_id(fpath, "FUNCTION", fn_name)
            graph.add_node(Node(
                id=fnid,
                type=NodeType.FUNCTION,
                name=fn_name,
                path=fpath,
                metadata={"lineno": lineno},
            ))

        # INTERFACE nodes
        for if_name, lineno in parsed.interfaces:
            iid = make_node_id(fpath, "INTERFACE", if_name)
            graph.add_node(Node(
                id=iid,
                type=NodeType.INTERFACE,
                name=if_name,
                path=fpath,
                metadata={"lineno": lineno},
            ))

        # MODEL nodes
        for mdl_name, lineno in parsed.models:
            mid = make_node_id(fpath, "MODEL", mdl_name)
            graph.add_node(Node(
                id=mid,
                type=NodeType.MODEL,
                name=mdl_name,
                path=fpath,
                metadata={"lineno": lineno},
            ))


def _compile_edges(
    graph: CodeGraph,
    parsed_files: Dict[str, ParsedFile],
    analysis: Dict[str, AnalysisResult],
) -> None:
    # Build lookup: file path → FILE node id
    path_to_fid: Dict[str, str] = {}
    for nid, node in graph.nodes.items():
        if node.type == NodeType.FILE:
            path_to_fid[node.path] = nid

    for fpath, result in analysis.items():
        src_fid = path_to_fid.get(fpath)
        if src_fid is None:
            continue

        # Import edges
        for src, tgt, etype, weight in result.import_edges:
            tgt_fid = path_to_fid.get(tgt)
            if tgt_fid:
                graph.add_edge(Edge(
                    from_id=src_fid,
                    to_id=tgt_fid,
                    type=EdgeType.IMPORTS,
                    weight=weight,
                ))

        # Dependency edges (imports → DEPENDS_ON)
        for src, tgt, etype, weight in result.import_edges:
            tgt_fid = path_to_fid.get(tgt)
            if tgt_fid:
                graph.add_edge(Edge(
                    from_id=src_fid,
                    to_id=tgt_fid,
                    type=EdgeType.DEPENDS_ON,
                    weight=weight * 0.8,
                ))

        # Call edges
        for src, tgt, etype, weight in result.call_edges:
            graph.add_edge(Edge(
                from_id=src_fid,
                to_id=tgt,
                type=EdgeType.CALLS,
                weight=weight,
            ))

        # DI injection edges
        for src, tgt, etype, weight in result.di_edges:
            graph.add_edge(Edge(
                from_id=src_fid,
                to_id=tgt,
                type=EdgeType.INJECTS,
                weight=weight,
            ))


def _resolve_reverse_deps(graph: CodeGraph) -> None:
    for nid, node in graph.nodes.items():
        outgoing: List[str] = []
        incoming: List[str] = []
        for edge in graph.edges:
            if edge.from_id == nid and edge.type == EdgeType.DEPENDS_ON:
                outgoing.append(edge.to_id)
            if edge.to_id == nid and edge.type == EdgeType.DEPENDS_ON:
                incoming.append(edge.from_id)
        node.dependencies = sorted(set(outgoing))
        node.reverse_dependencies = sorted(set(incoming))


# ── Stage 4 helpers ──────────────────────────────────────────────────────────


def _optimize(
    graph: CodeGraph,
    parsed_files: Dict[str, ParsedFile],
) -> None:
    """Dedup, merge redundant edges, compute scores."""
    # Dedup nodes by (path, name) — keep first occurrence
    seen: Set[str] = set()
    deduped: Dict[str, Node] = {}
    for nid, node in sorted(graph.nodes.items()):
        key = f"{node.path}:{node.name}:{node.type.value}"
        if key not in seen:
            seen.add(key)
            deduped[nid] = node
    graph.nodes = deduped

    # Merge redundant edges (same from→to→type, keep highest weight)
    edge_map: Dict[tuple, Edge] = {}
    for edge in graph.edges:
        key = (edge.from_id, edge.to_id, edge.type.value)
        if key in edge_map:
            existing = edge_map[key]
            if edge.weight > existing.weight:
                edge_map[key] = edge
        else:
            edge_map[key] = edge
    graph.edges = set(edge_map.values())

    # Compute complexity + risk scores
    for nid, node in graph.nodes.items():
        if node.type == NodeType.FILE:
            parsed = parsed_files.get(node.path)
            if parsed:
                node.complexity_score = compute_complexity(parsed)
                node.risk_score = compute_risk_score(
                    node.path,
                    dep_count=len(node.dependencies),
                    reverse_dep_count=len(node.reverse_dependencies),
                )


# ── Helpers ──────────────────────────────────────────────────────────────────


def _classify_file_type(path: str) -> str:
    if "interface" in path.lower() or "interfaces/" in path:
        return "interface"
    if "model" in path.lower() or "models/" in path:
        return "model"
    if "adapter" in path.lower() or "adapters/" in path:
        return "adapter"
    if "test_" in path or "/tests/" in path:
        return "test"
    return "source"


def _include_doc_files(root_dir: str, files: List[str]) -> List[str]:
    doc_candidates = [
        str(Path(root_dir) / "DEVELOPER.md"),
        str(Path(root_dir) / "CHANGELOG.md"),
        str(Path(root_dir) / "ARCHITECTURE_AUDIT_REPORT.md"),
    ]
    for doc in doc_candidates:
        p = Path(doc)
        if p.exists() and str(p) not in files:
            files.append(str(p))
    return sorted(files)
