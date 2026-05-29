"""
Root conftest — registers quarantined marker and auto-skip logic.

Tests marked @pytest.mark.quarantined are skipped by default.
Run them explicitly with: pytest -m quarantined
"""
import pytest


def pytest_collection_modifyitems(config, items):
    # If --run-quarantined is passed, don't skip
    if config.getoption("--run-quarantined", False):
        return
    skip_quarantined = pytest.mark.skipif(
        True,
        reason="Quarantined test — use --run-quarantined to execute",
    )
    for item in items:
        if item.get_closest_marker("quarantined"):
            item.add_marker(skip_quarantined)


def pytest_addoption(parser):
    parser.addoption(
        "--run-quarantined",
        action="store_true",
        default=False,
        help="Run quarantined (known-failing) tests",
    )
