#!/usr/bin/env python3
"""Router Isolation AST Gate — enforce that routers/ does not import from core.* directly.

LAW 13: Routers MUST NOT import from core.<direct> — only via:
  - core.runtime.*       (the runtime boundary — facade, bootstrap, data_providers)
  - core.composition.*   (the composition root — build_minimal_runtime)

A "direct core import" is any ``from core.X`` where X is not ``runtime`` or
``composition``.  In other words:

  ✅  from core.runtime.facade import EmoRuntimeFacade
  ✅  from core.composition.root import build_minimal_runtime
  ❌  from core.db import db
  ❌  from core.execution_engine import ExecutionEngine

Exit code 0 = pass, 1 = fail.

Usage:
    python scripts/enforce/router_isolation_check.py
    python scripts/enforce/router_isolation_check.py --ci  # JSON output
"""

import ast
import os
import sys
from pathlib import Path


ROUTERS_DIR = Path("routers")
ALLOWED_CORE_PREFIXES = (
    "core.runtime",
    "core.composition",
)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def is_allowed(module: str) -> bool:
    """Return True if the module is an allowed core.* import for routers."""
    if not module.startswith("core"):
        return True
    return any(module.startswith(prefix) for prefix in ALLOWED_CORE_PREFIXES)


def check_file(filepath: Path) -> list[dict]:
    """Scan a single file for disallowed core imports.  Returns list of violations."""
    violations: list[dict] = []
    try:
        tree = ast.parse(filepath.read_text(encoding="utf-8"), filename=str(filepath))
    except SyntaxError as e:
        violations.append({
            "file": str(filepath.relative_to(PROJECT_ROOT)),
            "line": e.lineno or 0,
            "col": e.offset or 0,
            "import": "<syntax error>",
            "severity": "error",
        })
        return violations

    for node in ast.walk(tree):
        # from core.xxx import yyy
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if is_allowed(module):
                continue
            names = [alias.name for alias in node.names]
            violations.append({
                "file": str(filepath.relative_to(PROJECT_ROOT)),
                "line": node.lineno,
                "col": node.col_offset,
                "import": f"from {module} import {', '.join(names)}",
                "severity": "error",
            })

        # import core.xxx
        elif isinstance(node, ast.Import):
            for alias in node.names:
                name = alias.name
                if is_allowed(name):
                    continue
                violations.append({
                    "file": str(filepath.relative_to(PROJECT_ROOT)),
                    "line": node.lineno,
                    "col": node.col_offset,
                    "import": f"import {name}",
                    "severity": "error",
                })

    return violations


def main() -> int:
    ci_mode = "--ci" in sys.argv
    routers_path = PROJECT_ROOT / ROUTERS_DIR

    if not routers_path.is_dir():
        print(f"ERROR: routers/ directory not found at {routers_path}", file=sys.stderr)
        return 1

    all_violations: list[dict] = []
    files_scanned = 0

    for pyfile in sorted(routers_path.rglob("*.py")):
        if pyfile.name == "__init__.py":
            continue
        files_scanned += 1
        violations = check_file(pyfile)
        all_violations.extend(violations)

    if ci_mode:
        import json
        report = {
            "files_scanned": files_scanned,
            "violations": all_violations,
            "passed": len(all_violations) == 0,
        }
        print(json.dumps(report, indent=2))
    else:
        if not all_violations:
            print(f"✅  PASS — {files_scanned} files scanned, 0 violations")
            return 0

        print(f"❌  FAIL — {len(all_violations)} violation(s) in {files_scanned} files:")
        print()
        for v in all_violations:
            print(f"  {v['file']}:{v['line']}:{v['col']}  {v['import']}")
        print()
        print("Allowed core prefixes:", ", ".join(ALLOWED_CORE_PREFIXES))
        print()

    return 1 if all_violations else 0


if __name__ == "__main__":
    sys.exit(main())
