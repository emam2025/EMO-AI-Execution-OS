"""
Quarantine Zone — Pre-existing test failures isolated from main CI.

These tests are known to fail due to:
- env_missing: Missing dependencies (aiosqlite, fastapi)
- legacy_billing: Legacy billing enterprise integration (requires enterprise env)
- jwt_migration: JWT security migration in progress
- async_fixture: Async fixture / collection incompatibilities
- other_legacy: Other legacy integration failures

All tests in this directory are marked @pytest.mark.quarantined and excluded
from the default `pytest` run. Run them explicitly with:
    pytest tests/quarantine/ -m quarantined
"""
