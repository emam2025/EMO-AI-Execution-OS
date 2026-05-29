"""Quarantine conftest — marks all tests in quarantine/ as quarantined."""
import pytest


def pytest_collection_modifyitems(items):
    for item in items:
        item.add_marker(pytest.mark.quarantined)
