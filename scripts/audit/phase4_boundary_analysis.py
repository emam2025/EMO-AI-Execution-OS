"""Phase 4 Boundary & Bridge Analysis — Audit Script.

Read-only analysis of core/execution_engine.py and core/runtime/
to identify OS-touching call sites, LAW 10/RULE 1 violations,
and bridge points requiring IsolationRuntime.

OUTPUT: artifacts/design/phase4/01_boundary_mapping.md
"""

from __future__ import annotations

import ast
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Tuple

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("phase4_boundary_analysis")

ANALYSIS_LOG: List[Dict[str, Any]] = []


def record(category: str, file: str, line: int, detail: str, canon_ref: str) -> None:
    ANALYSIS_LOG.append({
        "category": category,
        "file": file,
        "line": line,
        "detail": detail,
        "canon_ref": canon_ref,
    })
    log.info("  [%s] %s:%d — %s", category, os.path.basename(file), line, detail)


def scan_ast_calls(filepath: str) -> None:
    """Scan a Python file for OS-touching call sites using AST."""
    path = Path(filepath)
    if not path.exists():
        return
    source = path.read_text()
    try:
        tree = ast.parse(source)
    except SyntaxError:
        record("PARSE_ERROR", filepath, 0, "Syntax error in file", "N/A")
        return

    # Blacklisted call patterns (OS/IO/subprocess touching)
    BLACKLIST_CALLS: Dict[str, str] = {
        "subprocess.run": "LAW 10 — direct subprocess bypasses sandbox",
        "subprocess.Popen": "LAW 10 — direct subprocess bypasses sandbox",
        "subprocess.call": "LAW 10 — direct subprocess bypasses sandbox",
        "subprocess.check_call": "LAW 10 — direct subprocess bypasses sandbox",
        "os.system": "RULE 1 — NO DIRECT EXECUTION",
        "os.popen": "RULE 1 — NO DIRECT EXECUTION",
        "os.spawn": "RULE 1 — NO DIRECT EXECUTION",
        "os.execvp": "RULE 1 — NO DIRECT EXECUTION",
        "os.execl": "RULE 1 — NO DIRECT EXECUTION",
        "socket.socket": "RULE 2 — uncontrolled IO",
        "socket.connect": "RULE 2 — uncontrolled IO",
        "requests.get": "RULE 2 — uncontrolled IO",
        "requests.post": "RULE 2 — uncontrolled IO",
        "requests.put": "RULE 2 — uncontrolled IO",
        "urllib.request": "RULE 2 — uncontrolled IO",
        "open(": "RULE 2 — uncontrolled filesystem IO",
        "tempfile": "RULE 2 — uncontrolled filesystem IO",
    }

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            call_str = _node_to_call_str(node)
            for pattern, violation in BLACKLIST_CALLS.items():
                if pattern in call_str:
                    record(
                        "OS_TOUCH",
                        filepath,
                        node.lineno or 0,
                        f"Direct call {call_str} — {violation}",
                        violation.split("—")[0].strip(),
                    )

    # Scan for direct ExecutionEngine instantiation (LAW 13 violation)
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            try:
                func = node.func
                if isinstance(func, ast.Name) and func.id == "ExecutionEngine":
                    record(
                        "LAW13_VIOLATION",
                        filepath,
                        node.lineno or 0,
                        "Direct ExecutionEngine() call — LAW 13 violation",
                        "LAW 13",
                    )
                if isinstance(func, ast.Attribute):
                    if isinstance(func.value, ast.Name) and func.value.id == "ExecutionEngine":
                        record(
                            "LAW13_VIOLATION",
                            filepath,
                            node.lineno or 0,
                            f"Direct {func.attr}() on ExecutionEngine — LAW 13 violation",
                            "LAW 13",
                        )
            except Exception:
                pass


def _node_to_call_str(node: ast.Call) -> str:
    """Convert an AST Call node to a string representation."""
    try:
        func = node.func
        if isinstance(func, ast.Attribute):
            if isinstance(func.value, ast.Name):
                return f"{func.value.id}.{func.attr}"
            if isinstance(func.value, ast.Attribute):
                return _node_to_call_str(func.value) + "." + func.attr
            return f"?.{func.attr}"
        if isinstance(func, ast.Name):
            return func.id
        return "?"
    except Exception:
        return "?"


def scan_for_bridge_points(filepath: str) -> None:
    """Identify points where IsolationRuntime bridges are needed."""
    path = Path(filepath)
    if not path.exists():
        return
    source = path.read_text()
    lines = source.split("\n")

    for i, line in enumerate(lines, 1):
        stripped = line.strip()

        # Direct import of OS/subprocess/socket modules
        for mod in ("import subprocess", "import os", "import socket",
                     "import tempfile", "from subprocess"):
            if stripped.startswith(mod) and mod != "import os":
                record("BRIDGE_IMPORT", filepath, i,
                       f"Direct {mod} — needs IsolationRuntime bridge",
                       "RULE 1/2")

        # Direct filesystem path references
        if "open(" in stripped and "# isolation-ok" not in stripped:
            pass  # Too noisy — filter at review

        # Thread/process spawning patterns
        if "threading.Thread" in stripped and "daemon=True" not in stripped:
            record("POTENTIAL_LEAK", filepath, i,
                   "Non-daemon thread — may violate RULE 4 (killable)",
                   "RULE 4")

        # SIGKILL/RLIMIT patterns — verify against RULE 4
        if "SIGKILL" in stripped or "RLIMIT" in stripped:
            record("RULE4_ENFORCEMENT", filepath, i,
                   f"Found kill/limit enforcement: {stripped[:80]}",
                   "RULE 4")


def main() -> None:
    log.info("=" * 72)
    log.info("PHASE 4 — BOUNDARY & BRIDGE ANALYSIS")
    log.info("=" * 72)

    CORE_DIR = Path("core")

    # Scan all Python files in runtime/ and execution_engine.py
    targets = [str(CORE_DIR / "execution_engine.py")]
    for root, dirs, files in os.walk(str(CORE_DIR / "runtime")):
        for f in files:
            if f.endswith(".py"):
                targets.append(os.path.join(root, f))

    log.info("\nScanning %d files for OS-touching call sites...\n", len(targets))
    for t in sorted(targets):
        scan_ast_calls(t)
        scan_for_bridge_points(t)

    # Summary
    log.info("\n" + "=" * 72)
    log.info("SUMMARY")
    log.info("=" * 72)

    categories: Dict[str, int] = {}
    canon_refs: Dict[str, int] = {}
    for entry in ANALYSIS_LOG:
        categories[entry["category"]] = categories.get(entry["category"], 0) + 1
        canon_refs[entry["canon_ref"]] = canon_refs.get(entry["canon_ref"], 0) + 1

    log.info("\nBy Category:")
    for cat, count in sorted(categories.items(), key=lambda x: -x[1]):
        log.info("  %-25s %d", cat, count)

    log.info("\nBy Canon Reference:")
    for ref, count in sorted(canon_refs.items(), key=lambda x: -x[1]):
        log.info("  %-25s %d", ref, count)

    log.info("\nTotal findings: %d", len(ANALYSIS_LOG))

    # Write structured JSON for artifact generation
    import json
    output = Path("artifacts/design/phase4/01_boundary_analysis_raw.json")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps({
        "scanned_files": len(targets),
        "findings": ANALYSIS_LOG,
        "summary": {
            "by_category": categories,
            "by_canon_ref": canon_refs,
            "total": len(ANALYSIS_LOG),
        },
    }, indent=2))
    log.info("\nRaw data → %s", output)


if __name__ == "__main__":
    main()
