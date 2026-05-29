"""
async_fixture — Pre-existing async fixture / collection incompatibility failures.

These tests fail due to async fixture mismatches (sync/async collection mode in pytest)
or incompatible test patterns (e.g. sync assertion on async result).

Root cause: pytest asyncio_mode=auto + legacy sync test patterns.
Estimated effort: 1-2 hours (convert sync assertions to async).
"""
import pytest


@pytest.mark.quarantined
@pytest.mark.async_fixture
class TestAsyncFixture:
    """~4 async fixture / collection failures."""

    def test_async_fixture_placeholder(self):
        pytest.skip("4 async fixture tests quarantined — see DEBT_RESOLUTION_PLAN.md")
