"""
env_missing — Missing dependencies that prevent test collection.

These test files fail to import due to missing system dependencies (aiosqlite, fastapi).
They are quarantined until the environment is provisioned with the required packages.

Affected files:
- tests/test_bootstrap.py          — requires aiosqlite
- tests/test_composition_root_isolation.py — requires aiosqlite
- tests/test_pilot_safety.py        — requires aiosqlite
- tests/test_sql_injection_prevention.py — requires aiosqlite

Root cause: aiosqlite>=0.20.0 listed in requirements.txt but not installed.
"""
