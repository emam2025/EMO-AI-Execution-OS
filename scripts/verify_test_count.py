#!/usr/bin/env python3
"""Verify test count consistency across docs.
Run: python3 scripts/verify_test_count.py
Exit 0 = pass, Exit 1 = inconsistency detected.
"""
import re
import subprocess
import sys
from pathlib import Path

# Get actual test count
result = subprocess.run(
    ["python3", "-m", "pytest", "--collect-only", "-q"],
    capture_output=True, text=True, cwd=Path(__file__).parent.parent
)
match = re.search(r"(\d+) tests collected", result.stdout + result.stderr)
if not match:
    print("ERROR: Could not collect tests")
    sys.exit(1)
actual_count = int(match.group(1))

# Files to check
DOC_FILES = [
    "README.md",
    "PROJECT_STATUS_REPORT.md",
    "CHANGELOG.md",
    "DEVELOPER.md",
    "docs/REPOSITORY_STRUCTURE_MAP.md",
]

inconsistencies = []
for f in DOC_FILES:
    path = Path(__file__).parent.parent / f
    if not path.exists():
        continue
    content = path.read_text(encoding="utf-8")
    # Find all "NNN+ tests" patterns
    matches = re.findall(r"(\d{3,5})\+\s*tests", content)
    for m in matches:
        if abs(int(m) - actual_count) > actual_count * 0.1:  # 10% tolerance
            inconsistencies.append(f"{f}: mentions {m}+ tests, actual is {actual_count}")

if inconsistencies:
    print("FAIL: Test count inconsistency detected:")
    for inc in inconsistencies:
        print(f"  - {inc}")
    print(f"\nActual count: {actual_count}")
    print("Run: python3 scripts/sync_test_count.py to fix")
    sys.exit(1)
else:
    print(f"OK: All docs consistent with actual count ({actual_count})")
    sys.exit(0)
