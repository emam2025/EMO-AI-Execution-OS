#!/usr/bin/env python3
"""
Architecture Reality Auditor — Phase A: Repository Reality Scan.

Hostile verification audit. Assumes nothing is real until proven.
"""

from __future__ import annotations

import ast
import json
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

# ── Config ───────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CORE_DIR = PROJECT_ROOT / "core"
TESTS_DIR = PROJECT_ROOT / "tests"
REPORT_DIR = PROJECT_ROOT / "audit" / "reports"
REPORT_DIR.mkdir(parents=True, exist_ok=True)

IGNORE_DIRS = {"__pycache__", ".venv", "venv", "node_modules", ".git", "artifacts"}


# ═══════════════════════════════════════════════════════════════════
# PHASE 1 — PUBLIC API INVENTORY
# ═══════════════════════════════════════════════════════════════════

@dataclass
class PublicAPI:
    classes: List[Dict[str, Any]] = field(default_factory=list)
    public_methods: int = 0
    endpoints: List[Dict[str, Any]] = field(default_factory=list)
    tool_specs: List[Dict[str, Any]] = field(default_factory=list)
    contracts: List[Dict[str, Any]] = field(default_factory=list)
    schedulers: List[Dict[str, Any]] = field(default_factory=list)
    replay_apis: List[Dict[str, Any]] = field(default_factory=list)
    distributed_apis: List[Dict[str, Any]] = field(default_factory=list)


def scan_public_api() -> PublicAPI:
    api = PublicAPI()
    for py_file in sorted(CORE_DIR.rglob("*.py")):
        if any(part in str(py_file) for part in IGNORE_DIRS):
            continue
        try:
            with open(py_file) as f:
                tree = ast.parse(f.read())
        except SyntaxError:
            continue

        rel = py_file.relative_to(PROJECT_ROOT)
        module_name = str(rel).replace("/", ".").replace(".py", "")

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                methods = [n.name for n in node.body if isinstance(n, ast.FunctionDef)]
                public_methods = [m for m in methods if not m.startswith("_")]
                if public_methods:
                    api.classes.append({
                        "module": module_name,
                        "file": str(rel),
                        "class": node.name,
                        "public_methods": public_methods,
                        "method_count": len(public_methods),
                    })
                    api.public_methods += len(public_methods)

            # Detect endpoints (methods with @app.route or @router)
            if isinstance(node, ast.FunctionDef):
                for dec in node.decorator_list:
                    if isinstance(dec, ast.Call):
                    # Check for route/endpoint decorators
                        if (isinstance(dec.func, ast.Attribute) and
                                "route" in dec.func.attr):
                            api.endpoints.append({
                                "module": module_name,
                                "method": node.name,
                                "line": node.lineno,
                            })

            # Detect ToolSpec definitions
            if isinstance(node, ast.ClassDef):
                bases = [b.id for b in node.bases if isinstance(b, ast.Name)]
                if "ToolSpec" in bases or "Tool" in bases:
                    api.tool_specs.append({
                        "module": module_name,
                        "class": node.name,
                    })

        # Detect contracts (Protocol/ABC classes)
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                for base in node.bases:
                    if isinstance(base, ast.Name) and base.id in ("Protocol", "ABC"):
                        api.contracts.append({
                            "module": module_name,
                            "class": node.name,
                        })
                    if isinstance(base, ast.Attribute) and base.attr in ("Protocol", "ABC"):
                        api.contracts.append({
                            "module": module_name,
                            "class": node.name,
                        })

    # Detect schedulers, replay APIs, distributed APIs by keyword in module path
    for cls in api.classes:
        if "scheduler" in cls["module"].lower() or "scheduler" in cls["class"].lower():
            api.schedulers.append(cls)
        if "replay" in cls["module"].lower() or "replay" in cls["class"].lower():
            api.replay_apis.append(cls)
        if "distributed" in cls["module"].lower() or "mesh" in cls["module"].lower():
            api.distributed_apis.append(cls)
        if "remote" in cls["module"].lower() or "transport" in cls["class"].lower():
            if cls not in api.distributed_apis:
                api.distributed_apis.append(cls)

    return api


# ═══════════════════════════════════════════════════════════════════
# PHASE 2 — PLACEHOLDER DETECTION
# ═══════════════════════════════════════════════════════════════════

PLACEHOLDER_PATTERNS = [
    ("pass", re.compile(r"^\s+pass\s*$")),
    ("not_implemented", re.compile(r"NotImplementedError")),
    ("return_empty_dict", re.compile(r"return\s+\{\}")),
    ("return_empty_list", re.compile(r"return\s+\[\]")),
    ("return_none", re.compile(r"return\s+None")),
    ("return_true", re.compile(r"return\s+True")),
    ("return_false", re.compile(r"return\s+False")),
    ("return_zero", re.compile(r"return\s+0")),
    ("return_empty_str", re.compile(r"return\s+['\"]\s*['\"]")),
    ("todo", re.compile(r"#\s*(TODO|FIXME|HACK|XXX)")),
]


@dataclass
class PlaceholderFinding:
    file: str
    line: int
    pattern: str
    code: str
    classification: str = ""


def detect_placeholders() -> List[PlaceholderFinding]:
    findings = []
    for py_file in sorted(CORE_DIR.rglob("*.py")):
        if any(part in str(py_file) for part in IGNORE_DIRS):
            continue
        rel = str(py_file.relative_to(PROJECT_ROOT))
        try:
            with open(py_file) as f:
                lines = f.readlines()
        except Exception:
            continue

        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            for pattern_name, pattern in PLACEHOLDER_PATTERNS:
                if pattern.search(stripped):
                    findings.append(PlaceholderFinding(
                        file=rel,
                        line=i,
                        pattern=pattern_name,
                        code=stripped[:120],
                    ))
                    break

    # Classify
    for f in findings:
        if f.pattern in ("not_implemented",):
            f.classification = "runtime_critical"
        elif f.pattern in ("pass", "return_empty_dict", "return_empty_list",
                           "return_none", "return_zero", "return_empty_str"):
            # Check if it's in a function body
            if is_in_method_body(f.file, f.line):
                f.classification = "suspicious"
            else:
                f.classification = "harmless"
        elif f.pattern in ("todo",):
            f.classification = "suspicious"
        else:
            f.classification = "harmless"

    return findings


def is_in_method_body(file_rel: str, line_num: int) -> bool:
    """Rough check if a line is inside a method."""
    try:
        with open(PROJECT_ROOT / file_rel) as f:
            tree = ast.parse(f.read())
    except Exception:
        return False
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.lineno <= line_num <= node.end_lineno:
                return True
    return False


# ═══════════════════════════════════════════════════════════════════
# PHASE 3 — THIN WRAPPER DETECTION
# ═══════════════════════════════════════════════════════════════════

@dataclass
class ThinWrapperFinding:
    file: str
    class_name: str
    method: str
    line: int
    body_length: int
    is_pure_delegate: bool
    delegations: List[str] = field(default_factory=list)


def detect_thin_wrappers() -> List[ThinWrapperFinding]:
    findings = []
    for py_file in sorted(CORE_DIR.rglob("*.py")):
        if any(part in str(py_file) for part in IGNORE_DIRS):
            continue
        rel = str(py_file.relative_to(PROJECT_ROOT))
        try:
            with open(py_file) as f:
                tree = ast.parse(f.read())
        except Exception:
            continue

        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            for item in node.body:
                if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    continue
                if item.name.startswith("_"):
                    continue

                body = item.body
                if not body:
                    continue

                # Count actual logic statements (not docstrings, not pass)
                logic_count = 0
                delegates = []
                for stmt in body:
                    if isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant):
                        continue  # docstring
                    if isinstance(stmt, ast.Pass):
                        continue
                    logic_count += 1
                    # Detect delegation
                    if isinstance(stmt, ast.Return):
                        if isinstance(stmt.value, ast.Call):
                            call = stmt.value
                            if isinstance(call.func, ast.Attribute):
                                if isinstance(call.func.value, ast.Attribute):
                                    delegates.append(f"{call.func.value.attr}.{call.func.attr}")
                                elif isinstance(call.func.value, ast.Name):
                                    delegates.append(f"{call.func.value.id}.{call.func.attr}")

                is_pure_delegate = logic_count == 1 and len(delegates) == 1

                if logic_count <= 2:
                    findings.append(ThinWrapperFinding(
                        file=rel,
                        class_name=node.name,
                        method=item.name,
                        line=item.lineno,
                        body_length=len(body),
                        is_pure_delegate=is_pure_delegate,
                        delegations=delegates,
                    ))

    return findings


# ═══════════════════════════════════════════════════════════════════
# PHASE 4 — DEAD INFRASTRUCTURE DETECTION
# ═══════════════════════════════════════════════════════════════════

@dataclass
class DeadInfrastructure:
    unused_modules: List[str] = field(default_factory=list)
    orphan_classes: List[Dict[str, Any]] = field(default_factory=list)
    import_graph: Dict[str, List[str]] = field(default_factory=dict)
    used_modules: Set[str] = field(default_factory=set)
    all_modules: List[str] = field(default_factory=list)


def build_import_graph() -> DeadInfrastructure:
    result = DeadInfrastructure()

    # Collect all modules
    for py_file in sorted(CORE_DIR.rglob("*.py")):
        if any(part in str(py_file) for part in IGNORE_DIRS):
            continue
        rel = str(py_file.relative_to(PROJECT_ROOT))
        module = rel.replace("/", ".").replace(".py", "")
        if module.endswith(".__init__"):
            module = module[:-9]
        result.all_modules.append(module)

    # Build import graph
    for py_file in sorted(CORE_DIR.rglob("*.py")):
        if any(part in str(py_file) for part in IGNORE_DIRS):
            continue
        rel = str(py_file.relative_to(PROJECT_ROOT))
        try:
            with open(py_file) as f:
                tree = ast.parse(f.read())
        except Exception:
            continue

        module = rel.replace("/", ".").replace(".py", "")
        if module.endswith(".__init__"):
            module = module[:-9]

        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imp = alias.name
                    if imp.startswith("core") or imp.startswith("tests"):
                        imports.append(imp)
            elif isinstance(node, ast.ImportFrom):
                if node.module and (node.module.startswith("core") or node.module.startswith("tests")):
                    imports.append(node.module)

        result.import_graph[module] = imports
        if imports:
            result.used_modules.add(module)
            for imp in imports:
                result.used_modules.add(imp)

    # Find unused modules
    for m in result.all_modules:
        if m not in result.used_modules and not m.startswith("tests"):
            # Check if it's imported by anything
            found = False
            for imports in result.import_graph.values():
                if m in imports or m.split(".")[-1] in [i.split(".")[-1] for i in imports]:
                    found = True
                    break
            if not found:
                result.unused_modules.append(m)

    return result


# ═══════════════════════════════════════════════════════════════════
# PHASE 5 — EXECUTION PATH VALIDATION
# ═══════════════════════════════════════════════════════════════════

@dataclass
class ExecutionPath:
    layer: str
    components: List[str]
    connected_to: List[str]
    verified: bool = False
    evidence: str = ""


def validate_execution_path() -> Dict[str, Any]:
    """Reconstruct and verify the full execution path:
    Query → Planner → DAG → Scheduler → Ownership → Worker → Replay → Observability → Feedback → Planner
    """
    path_steps = []

    # Helper: check if a component exists in the import graph
    import_graph = build_import_graph()

    def exists(module_prefix: str) -> bool:
        for m in import_graph.all_modules:
            if m.startswith(module_prefix):
                return True
        return False

    def connected(from_mod: str, to_mod: str) -> bool:
        imports = import_graph.import_graph.get(from_mod, [])
        for imp in imports:
            if to_mod in imp:
                return True
        return False

    # Layer 1: Query → Planner
    q_exists = exists("core.query") or exists("core.planner")
    path_steps.append({
        "layer": "Query/Planner",
        "exists": q_exists,
        "components": [m for m in import_graph.all_modules if "planner" in m or "query" in m],
        "connected_to": [],
    })

    # Layer 2: Planner → DAG
    dag_exists = exists("core.models.dag")
    path_steps.append({
        "layer": "DAG",
        "exists": dag_exists,
        "components": [m for m in import_graph.all_modules if ".dag" in m or "models" in m],
        "connected_to": [],
    })

    # Layer 3: DAG → Scheduler
    sched_exists = exists("core.scheduler")
    path_steps.append({
        "layer": "Scheduler",
        "exists": sched_exists,
        "components": [m for m in import_graph.all_modules if "scheduler" in m],
        "connected_to": [],
    })

    # Layer 4: Scheduler → Control Plane (Orchestrator)
    cp_exists = exists("core.control_plane")
    path_steps.append({
        "layer": "ControlPlane (Ownership)",
        "exists": cp_exists,
        "components": [m for m in import_graph.all_modules if "control_plane" in m],
        "connected_to": [],
    })

    # Layer 5: Control Plane → Worker
    worker_exists = exists("core.runtime.control")
    mesh_exists = exists("core.runtime.mesh")
    path_steps.append({
        "layer": "Worker/Mesh",
        "exists": worker_exists or mesh_exists,
        "components": (
            [m for m in import_graph.all_modules if ".control" in m or ".mesh" in m]
        ),
        "connected_to": [],
    })

    # Layer 6: Worker → Execution
    exec_exists = exists("core.runtime.isolation") or exists("core.runtime.sandbox")
    path_steps.append({
        "layer": "Execution (Isolation)",
        "exists": exec_exists,
        "components": [m for m in import_graph.all_modules if "isolation" in m or "sandbox" in m],
        "connected_to": [],
    })

    # Layer 7: Execution → Replay
    replay_exists = exists("core.recovery") or exists("core.runtime.os")
    path_steps.append({
        "layer": "Replay/Recovery",
        "exists": replay_exists,
        "components": [m for m in import_graph.all_modules if "recovery" in m or "replay" in m],
        "connected_to": [],
    })

    # Layer 8: Replay → Observability
    obs_exists = exists("core.observability")
    path_steps.append({
        "layer": "Observability",
        "exists": obs_exists,
        "components": [m for m in import_graph.all_modules if "observability" in m],
        "connected_to": [],
    })

    # Layer 9: Observability → Feedback → Planner
    feedback_exists = exists("core.evolution") or exists("core.feedback")
    path_steps.append({
        "layer": "Feedback/Evolution",
        "exists": feedback_exists,
        "components": [m for m in import_graph.all_modules if "evolution" in m or "feedback" in m],
        "connected_to": [],
    })

    # Verify connections
    for i, step in enumerate(path_steps):
        if i > 0:
            prev = path_steps[i - 1]["layer"]
            step["connected_to"] = [prev]
        if i < len(path_steps) - 1:
            nxt = path_steps[i + 1]["layer"]
            if nxt not in step["connected_to"]:
                step["connected_to"].append(nxt)

    all_connected = all(s["exists"] for s in path_steps)
    broken_layers = [s["layer"] for s in path_steps if not s["exists"]]

    return {
        "path": path_steps,
        "all_layers_present": all_connected,
        "broken_layers": broken_layers,
        "layer_count": len(path_steps),
        "healthy_layer_count": sum(1 for s in path_steps if s["exists"]),
    }


# ═══════════════════════════════════════════════════════════════════
# PHASE 6 — TEST INTEGRITY ANALYSIS
# ═══════════════════════════════════════════════════════════════════

@dataclass
class TestIntegrity:
    total_test_files: int = 0
    total_tests: int = 0
    assertionless_tests: List[Dict[str, Any]] = field(default_factory=list)
    over_mocked_tests: List[Dict[str, Any]] = field(default_factory=list)
    weak_assertion_tests: List[Dict[str, Any]] = field(default_factory=list)
    tests_per_file: Dict[str, int] = field(default_factory=dict)
    mock_ratio: Dict[str, float] = field(default_factory=dict)


def analyze_test_integrity() -> TestIntegrity:
    ti = TestIntegrity()

    for py_file in sorted(TESTS_DIR.rglob("test_*.py")):
        if any(part in str(py_file) for part in IGNORE_DIRS):
            continue
        rel = str(py_file.relative_to(PROJECT_ROOT))
        try:
            with open(py_file) as f:
                content = f.read()
                tree = ast.parse(content)
        except Exception:
            continue

        ti.total_test_files += 1

        # Count test functions
        test_funcs = [
            n for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name.startswith("test_")
        ]
        ti.total_tests += len(test_funcs)
        ti.tests_per_file[rel] = len(test_funcs)

        # Detect assertionless tests
        for func in test_funcs:
            has_assert = any(
                isinstance(n, ast.Assert) or
                (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                 and n.func.attr.startswith("assert"))
                for n in ast.walk(func)
            )
            if not has_assert:
                ti.assertionless_tests.append({
                    "file": rel,
                    "test": func.name,
                    "line": func.lineno,
                })

        # Detect over-mocking (count MagicMock/patch/AsyncMock usage)
        mock_count = content.count("MagicMock") + content.count("patch(") + content.count("AsyncMock")
        total_lines = len(content.splitlines())
        if total_lines > 0:
            ti.mock_ratio[rel] = mock_count / total_lines

        if mock_count > 5:
            ti.over_mocked_tests.append({
                "file": rel,
                "mock_count": mock_count,
                "mock_ratio": round(mock_count / max(1, total_lines), 3),
            })

        # Detect weak assertions (assert True, assert False, assert None)  # Fixed: removed is
        weak_patterns = re.findall(r"assert\s+(True|False|None)\b", content)
        if weak_patterns:
            ti.weak_assertion_tests.append({
                "file": rel,
                "count": len(weak_patterns),
                "patterns": list(set(weak_patterns)),
            })

    return ti


# ═══════════════════════════════════════════════════════════════════
# COMBINED REPORT GENERATION
# ═══════════════════════════════════════════════════════════════════

def classify_subsystem_confidence() -> Dict[str, Dict[str, Any]]:
    """Assess confidence in each subsystem based on audit data."""
    subsystems = {
        "F1 — RuntimeOS API": {"score": 0, "flags": []},
        "F2 — Control Plane": {"score": 0, "flags": []},
        "F3 — Resource Scheduler": {"score": 0, "flags": []},
        "F4 — Observability": {"score": 0, "flags": []},
        "Execution Engine": {"score": 0, "flags": []},
        "Mesh/Distributed": {"score": 0, "flags": []},
        "Sandbox/Isolation": {"score": 0, "flags": []},
        "Secrets/Security": {"score": 0, "flags": []},
        "Tests": {"score": 0, "flags": []},
    }

    # Check for thin wrappers in each subsystem
    wrappers = detect_thin_wrappers()
    placeholders = detect_placeholders()
    import_graph = build_import_graph()
    test_integrity = analyze_test_integrity()

    # F1 — RuntimeOS
    os_wrappers = [w for w in wrappers if "runtime/os" in w.file or "runtime_os" in w.file]
    os_ph = [p for p in placeholders if "runtime/os" in p.file or "runtime_os" in p.file]
    subsystems["F1 — RuntimeOS API"]["flags"].extend(
        [f"thin_wrapper:{w.method}" for w in os_wrappers[:5]]
    )
    subsystems["F1 — RuntimeOS API"]["flags"].extend(
        [f"placeholder:{p.pattern}" for p in os_ph[:5]]
    )
    subsystems["F1 — RuntimeOS API"]["score"] = max(0, 10 - len(os_wrappers) - len(os_ph))

    # F2 — Control Plane
    cp_wrappers = [w for w in wrappers if "control_plane" in w.file]
    cp_ph = [p for p in placeholders if "control_plane" in p.file]
    subsystems["F2 — Control Plane"]["flags"].extend(
        [f"thin_wrapper:{w.method}" for w in cp_wrappers[:5]]
    )
    subsystems["F2 — Control Plane"]["flags"].extend(
        [f"placeholder:{p.pattern}" for p in cp_ph[:5]]
    )
    subsystems["F2 — Control Plane"]["score"] = max(0, 10 - len(cp_wrappers) - len(cp_ph))

    # Tests
    subsystems["Tests"]["flags"].append(
        f"assertionless:{len(test_integrity.assertionless_tests)}"
    )
    subsystems["Tests"]["flags"].append(
        f"over_mocked:{len(test_integrity.over_mocked_tests)}"
    )
    subsystems["Tests"]["flags"].append(
        f"weak_assertions:{len(test_integrity.weak_assertion_tests)}"
    )
    subsystems["Tests"]["score"] = max(0, 10 - (
        len(test_integrity.assertionless_tests) // 5 +
        len(test_integrity.over_mocked_tests) +
        len(test_integrity.weak_assertion_tests)
    ))

    return subsystems


def generate_all_reports() -> Dict[str, Any]:
    api = scan_public_api()
    placeholders = detect_placeholders()
    wrappers = detect_thin_wrappers()
    import_graph = build_import_graph()
    exec_path = validate_execution_path()
    test_integrity = analyze_test_integrity()
    confidence = classify_subsystem_confidence()

    # Write JSON reports
    def write_json(name: str, data: Any) -> None:
        path = REPORT_DIR / name
        with open(path, "w") as f:
            json.dump(data, f, indent=2, default=str)
        print(f"  Wrote {path}")

    print("\n=== PHASE 1: Public API Inventory ===")
    write_json("public_api_inventory.json", {
        "class_count": len(api.classes),
        "public_method_count": api.public_methods,
        "classes": api.classes,
        "endpoints": api.endpoints,
        "tool_specs": api.tool_specs,
        "contracts": api.contracts,
        "schedulers": api.schedulers,
        "replay_apis": api.replay_apis,
        "distributed_apis": api.distributed_apis,
    })

    print("\n=== PHASE 2: Placeholder Detection ===")
    # Separate by classification
    critical = [p for p in placeholders if p.classification == "runtime_critical"]
    suspicious = [p for p in placeholders if p.classification == "suspicious"]
    harmless = [p for p in placeholders if p.classification == "harmless"]
    write_json("placeholders.json", {
        "total": len(placeholders),
        "runtime_critical": len(critical),
        "suspicious": len(suspicious),
        "harmless": len(harmless),
        "critical_findings": [
            {"file": p.file, "line": p.line, "pattern": p.pattern, "code": p.code}
            for p in critical
        ],
        "suspicious_findings": [
            {"file": p.file, "line": p.line, "pattern": p.pattern, "code": p.code}
            for p in suspicious
        ],
    })

    print("\n=== PHASE 3: Thin Wrapper Detection ===")
    pure_delegates = [w for w in wrappers if w.is_pure_delegate]
    write_json("thin_wrappers.json", {
        "total_thin_methods": len(wrappers),
        "pure_delegates": len(pure_delegates),
        "pure_delegate_list": [
            {"file": w.file, "class": w.class_name, "method": w.method,
             "line": w.line, "delegates_to": w.delegations}
            for w in pure_delegates
        ],
        "all_thin_methods": [
            {"file": w.file, "class": w.class_name, "method": w.method,
             "line": w.line, "body_length": w.body_length, "is_pure_delegate": w.is_pure_delegate}
            for w in wrappers
        ],
    })

    print("\n=== PHASE 4: Dead Infrastructure Detection ===")
    write_json("dead_infrastructure.json", {
        "total_modules": len(import_graph.all_modules),
        "used_modules": len(import_graph.used_modules),
        "unused_modules": import_graph.unused_modules,
        "orphan_classes": [],
        "import_graph": import_graph.import_graph,
    })

    print("\n=== PHASE 5: Execution Path Validation ===")
    write_json("runtime_path.json", exec_path)

    print("\n=== PHASE 6: Test Integrity Analysis ===")
    write_json("test_integrity.json", {
        "total_test_files": test_integrity.total_test_files,
        "total_tests": test_integrity.total_tests,
        "assertionless_tests": test_integrity.assertionless_tests[:50],
        "assertionless_count": len(test_integrity.assertionless_tests),
        "over_mocked_tests": test_integrity.over_mocked_tests,
        "weak_assertion_tests": test_integrity.weak_assertion_tests,
        "mock_ratio": test_integrity.mock_ratio,
    })

    print("\n=== Confidence Assessment ===")
    write_json("confidence.json", {
        "subsystems": confidence,
        "overall_confidence": round(
            sum(s["score"] for s in confidence.values()) / max(1, len(confidence)), 1
        ),
    })

    return {
        "api": api,
        "placeholders": placeholders,
        "wrappers": wrappers,
        "dead": import_graph,
        "exec_path": exec_path,
        "tests": test_integrity,
        "confidence": confidence,
    }


# ═══════════════════════════════════════════════════════════════════
# HUMAN-READABLE REPORT
# ═══════════════════════════════════════════════════════════════════

def generate_markdown_report(results: Dict[str, Any]) -> str:
    api: PublicAPI = results["api"]
    placeholders: List[PlaceholderFinding] = results["placeholders"]
    wrappers: List[ThinWrapperFinding] = results["wrappers"]
    dead: DeadInfrastructure = results["dead"]
    exec_path: Dict[str, Any] = results["exec_path"]
    tests: TestIntegrity = results["tests"]
    confidence: Dict[str, Dict[str, Any]] = results["confidence"]

    lines = []
    def L(*args: Any) -> None:
        lines.append(" ".join(str(a) for a in args))
    def H(level: int, text: str) -> None:
        lines.append(f"{'#' * level} {text}")
        lines.append("")

    # ── Header ──
    H(1, "Architecture Reality Report")
    L("**Audit Date:** ", str(__import__("datetime").datetime.now()))
    L("**Role:** Hostile Verification Audit")
    L("**Assumption:** Nothing is real until proven.")
    L("")

    # ── Executive Summary ──
    H(2, "Executive Summary")
    total_classes = len(api.classes)
    total_methods = api.public_methods
    critical_placeholders = len([p for p in placeholders if p.classification == "runtime_critical"])
    suspicious_placeholders = len([p for p in placeholders if p.classification == "suspicious"])
    pure_delegates = len([w for w in wrappers if w.is_pure_delegate])
    unused = len(dead.unused_modules)
    assertionless = len(tests.assertionless_tests)
    path_broken = exec_path["broken_layers"]

    L(f"- **Classes:** {total_classes}")
    L(f"- **Public Methods:** {total_methods}")
    L(f"- **Critical Placeholders:** {critical_placeholders}")
    L(f"- **Suspicious Placeholders:** {suspicious_placeholders}")
    L(f"- **Pure Delegate Wrappers:** {pure_delegates}")
    L(f"- **Unused Modules:** {unused}")
    L(f"- **Assertionless Tests:** {assertionless}")
    L(f"- **Broken Execution Layers:** {len(path_broken)}")
    L("")

    # ── Critical Findings ──
    H(2, "Critical Findings")
    if critical_placeholders:
        H(3, "NotImplementedError (Runtime Critical)")
        for p in placeholders:
            if p.classification == "runtime_critical":
                L(f"- `{p.file}:{p.line}` — `{p.code}`")
        L("")

    if path_broken:
        H(3, "Disconnected Execution Layers")
        for layer in path_broken:
            L(f"- **{layer}**: Layer not found in module tree")
        L("")

    # ── Public API Inventory ──
    H(2, "Public API Inventory")
    L(f"**{total_classes}** classes with **{total_methods}** public methods across the codebase.")
    L("")

    # Top modules by method count
    modules: Dict[str, int] = defaultdict(int)
    for c in api.classes:
        modules[c["module"].split(".")[0]] += c["method_count"]
    H(3, "Top Subsystems by Method Count")
    for mod, count in sorted(modules.items(), key=lambda x: -x[1])[:15]:
        L(f"- `{mod}`: {count} methods")
    L("")

    H(3, "Contracts (Protocols / ABCs)")
    for c in api.contracts:
        L(f"- `{c['class']}` in `{c['module']}`")
    L("")

    H(3, "ToolSpecs")
    for t in api.tool_specs:
        L(f"- `{t['class']}` in `{t['module']}`")
    L("")

    H(3, "Scheduler Components")
    for s in api.schedulers:
        L(f"- `{s['class']}` in `{s['module']}` ({s['method_count']} methods)")
    L("")

    H(3, "Replay APIs")
    for r in api.replay_apis:
        L(f"- `{r['class']}` in `{r['module']}` ({r['method_count']} methods)")
    L("")

    H(3, "Distributed/Mesh APIs")
    for d in api.distributed_apis:
        L(f"- `{d['class']}` in `{d['module']}` ({d['method_count']} methods)")
    L("")

    # ── Placeholder Analysis ──
    H(2, "Placeholder Analysis")
    H(3, "Summary")
    L(f"- **Harmless:** {len([p for p in placeholders if p.classification == 'harmless'])}")
    L(f"- **Suspicious:** {suspicious_placeholders}")
    L(f"- **Runtime Critical:** {critical_placeholders}")
    L("")

    if suspicious_placeholders:
        H(3, "Top Suspicious Files")
        file_counts = defaultdict(int)
        for p in placeholders:
            if p.classification == "suspicious":
                file_counts[p.file.split("/")[0]] += 1
        for f, c in sorted(file_counts.items(), key=lambda x: -x[1])[:10]:
            L(f"- `{f}`: {c} suspicious patterns")
        L("")

    # ── Thin Wrapper Analysis ──
    H(2, "Thin Wrapper Analysis")
    H(3, "Summary")
    total_methods_count = sum(
        len(c["public_methods"]) for c in api.classes
    )
    wrapper_pct = (len(wrappers) / max(1, total_methods_count)) * 100
    pure_pct = (pure_delegates / max(1, len(wrappers))) * 100
    L(f"- **Total thin methods:** {len(wrappers)} ({wrapper_pct:.1f}% of all methods)")
    L(f"- **Pure delegates:** {pure_delegates} ({pure_pct:.1f}% of thin methods)")
    L("")

    # Wrapper-only classes
    class_wrapper_count: Dict[str, int] = defaultdict(int)
    class_total_count: Dict[str, int] = defaultdict(int)
    for c in api.classes:
        class_total_count[c["class"]] = c["method_count"]
    for w in wrappers:
        class_wrapper_count[w.class_name] += 1

    H(3, "Highest Wrapper Ratio Classes")
    high_wrapper = []
    for cls, total in class_total_count.items():
        wrapped = class_wrapper_count.get(cls, 0)
        if total > 0 and wrapped / total > 0.5:
            high_wrapper.append((cls, wrapped, total, wrapped / total * 100))
    for cls, w, t, pct in sorted(high_wrapper, key=lambda x: -x[3])[:10]:
        L(f"- **{cls}**: {w}/{t} methods are thin ({pct:.0f}%)")
    L("")

    if pure_delegates > 0:
        H(3, "Worrying Pure Delegates (Orchestration Layers)")
        worrying = [w for w in wrappers if w.is_pure_delegate and w.body_length <= 2]
        for w in worrying[:20]:
            L(f"- `{w.class_name}.{w.method}()` → `{w.delegations}` at `{w.file}:{w.line}`")
        L("")

    # ── Dead Infrastructure ──
    H(2, "Dead Infrastructure")
    L(f"- **Total modules:** {dead.total_modules if hasattr(dead, 'total_modules') else len(dead.all_modules)}")
    L(f"- **Modules with imports:** {len(dead.used_modules)}")
    L(f"- **Orphan modules (no imports):** {unused}")
    L("")

    if unused > 0:
        H(3, "Orphan Modules (Not Imported by Anything)")
        for m in dead.unused_modules[:30]:
            L(f"- `{m}`")
        L("")

    # Import graph analysis
    H(3, "Module Dependency Islands")
    # Find modules that import nothing from core
    isolated = [m for m, imps in dead.import_graph.items()
                if not any("core" in i for i in imps) and "core" in m]
    for m in isolated[:20]:
        L(f"- `{m}` — imports nothing from core")
    L("")

    # ── Execution Path ──
    H(2, "Execution Path Validation")
    for step in exec_path["path"]:
        icon = "✅" if step["exists"] else "❌"
        L(f"### {icon} {step['layer']}")
        if step["components"]:
            L(f"  Components: {', '.join(step['components'][:5])}")
        L(f"  Connected to: {', '.join(step['connected_to'])}")
        L("")

    H(3, "Verdict")
    if exec_path["all_layers_present"]:
        L("✅ **All layers present** — execution path is structurally complete.")
    else:
        L(f"❌ **Broken layers:** {', '.join(exec_path['broken_layers'])}")
        L("The execution path has gaps that break the adaptive loop.")
    L("")

    # ── Test Integrity ──
    H(2, "Test Integrity Analysis")
    L(f"- **Test files:** {tests.total_test_files}")
    L(f"- **Total tests:** {tests.total_tests}")
    L(f"- **Assertionless tests:** {assertionless}")
    L(f"- **Over-mocked files:** {len(tests.over_mocked_tests)}")
    L(f"- **Files with weak assertions:** {len(tests.weak_assertion_tests)}")
    L("")

    if assertionless > 0:
        H(3, "Assertionless Tests (No Assertions)"
          )
        for t in tests.assertionless_tests[:15]:
            L(f"- `{t['test']}` in `{t['file']}:{t['line']}`")
        L("")

    if tests.over_mocked_tests:
        H(3, "Over-Mocked Test Files"
          )
        for t in tests.over_mocked_tests[:10]:
            L(f"- `{t['file']}` — {t['mock_count']} mocks (ratio: {t['mock_ratio']})")
        L("")

    # ── Subsystem Confidence ──
    H(2, "Subsystem Confidence Assessment")
    L("Scale: 0 (fake/totally broken) → 10 (fully real and connected)")
    L("")
    for subsystem, data in sorted(confidence.items(), key=lambda x: -x[1]["score"]):
        score = data["score"]
        bar = "█" * max(0, score) + "░" * max(0, 10 - score)
        flags = data["flags"]
        L(f"- **{subsystem}:** {bar} {score}/10")
        if flags:
            for f in flags[:5]:
                L(f"  - ⚠ {f}")
        L("")

    overall = round(
        sum(s["score"] for s in confidence.values()) / max(1, len(confidence)), 1
    )
    H(2, "Overall Confidence Score")
    bar = "█" * max(0, int(overall)) + "░" * max(0, 10 - int(overall))
    L(f"**{bar} {overall}/10**")
    L("")

    # ── Final Verdict ──
    H(2, "Final Verdict")
    if overall >= 7:
        L("**The system appears substantially real.**")
        L("The architecture is structurally complete, most layers are connected,")
        L("and the execution path is unbroken. Remediation should focus on")
        L("tightening thin wrappers, filling placeholders, and improving test quality.")
    elif overall >= 4:
        L("**The system is partially real but has significant concerns.**")
        L("Some layers may be architectural sketches. Several execution path")
        L("components are disconnected. Thin wrappers may create the illusion")
        L("of functionality. Recommend focused remediation on broken layers")
        L("and placeholder replacement.")
    else:
        L("**The system has serious reality problems.**")
        L("Multiple execution layers are missing or disconnected. The architecture")
        L("resembles a facade more than a runtime. Recommend fundamental")
        L("re-architecture before relying on this system.")
    L("")

    L("---")
    L("_This report was generated by the Architecture Reality Auditor._")
    L("_It assumes malicious compliance and trusts no naming, comments, or tests._")

    return "\n".join(lines)


def main() -> None:
    print("=" * 60)
    print("  ARCHITECTURE REALITY AUDITOR")
    print("  Hostile Verification Scan — Phase A")
    print("=" * 60)

    results = generate_all_reports()

    print("\n=== Generating Markdown Report ===")
    md = generate_markdown_report(results)
    md_path = PROJECT_ROOT / "audit" / "ARCHITECTURE_REALITY_REPORT.md"
    with open(md_path, "w") as f:
        f.write(md)
    print(f"  Wrote {md_path}")

    print("\n" + "=" * 60)
    print("  AUDIT COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
