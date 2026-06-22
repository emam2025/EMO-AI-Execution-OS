"""Phase 1 — main.py Lifespan Verification.

Tests the core lifespan components in isolation:
  1. EmoRuntime bootstrap (build + start + shutdown)
  2. EmoRuntimeFacade construction with partial components
  3. Graceful shutdown with no errors

Ref: DEVELOPER.md §15.15
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


# ═══════════════════════════════════════════════════════════════════
# 1. EmoRuntime bootstrap
# ═══════════════════════════════════════════════════════════════════

class TestEmoRuntimeBootstrap:
    """EmoRuntime bootstraps CompositionRoot without errors."""

    def test_build_with_default_config(self):
        from core.runtime.bootstrap import EmoRuntime
        runtime = EmoRuntime(config={"worker_pool_size": 2})
        try:
            runtime.build()
            assert runtime.is_built, "EmoRuntime should be built"
            assert runtime.root is not None, "CompositionRoot should exist"
            assert runtime.engine is not None, "ExecutionEngine should be accessible"
        finally:
            runtime.shutdown()

    def test_start_and_shutdown(self):
        from core.runtime.bootstrap import EmoRuntime
        runtime = EmoRuntime(config={"worker_pool_size": 2})
        try:
            runtime.build().start()
            assert runtime.is_started, "EmoRuntime should be started"
            assert runtime.is_built, "EmoRuntime should be built"
        finally:
            runtime.shutdown()
        assert not runtime.is_started, "EmoRuntime should be stopped after shutdown"

    def test_context_manager(self):
        from core.runtime.bootstrap import EmoRuntime
        with EmoRuntime(config={"worker_pool_size": 2}) as runtime:
            assert runtime.is_started, "Context manager should start the runtime"
            assert runtime.is_built
        assert not runtime.is_started, "Context manager should shutdown on exit"


# ═══════════════════════════════════════════════════════════════════
# 2. EmoRuntimeFacade construction
# ═══════════════════════════════════════════════════════════════════

class TestEmoRuntimeFacade:
    """EmoRuntimeFacade can be built with partial components."""

    def test_facade_none_components(self):
        from core.runtime.facade import EmoRuntimeFacade
        facade = EmoRuntimeFacade()
        health = facade.health()
        assert health["status"] == "ok"
        assert health["components"] == {}

    def test_facade_with_event_bus(self):
        from core.runtime.facade import EmoRuntimeFacade
        from core.runtime.event_bus import InMemoryEventBus
        bus = InMemoryEventBus()
        facade = EmoRuntimeFacade(event_bus=bus)
        health = facade.health()
        assert health["components"]["event_bus"]["status"] == "connected"

    def test_facade_health_returns_dict(self):
        from core.runtime.facade import EmoRuntimeFacade
        facade = EmoRuntimeFacade()
        result = facade.health()
        assert isinstance(result, dict)
        assert "status" in result
        assert "components" in result

    def test_facade_submit_no_runtime(self):
        from core.runtime.facade import EmoRuntimeFacade
        facade = EmoRuntimeFacade()
        result = facade.submit({"query": "test"})
        assert result["status"] == "error"
        assert "No runtime available" in result["message"]

    def test_facade_admin_no_runtime(self):
        from core.runtime.facade import EmoRuntimeFacade
        facade = EmoRuntimeFacade()
        result = facade.admin("cancel", {"task_id": "123"})
        assert result["status"] == "error"


# ═══════════════════════════════════════════════════════════════════
# 3. ai_state wiring (root cause of 503)
# ═══════════════════════════════════════════════════════════════════

class TestAIStateWiring:
    """The AI router state must have facade set (was None)."""

    def test_ai_state_facade_default_none(self):
        from routers.ai import ai_state
        assert ai_state.facade is None
        assert not ai_state.initialized

    def test_ai_state_facade_can_be_set(self):
        from routers.ai import ai_state
        from core.runtime.facade import EmoRuntimeFacade
        facade = EmoRuntimeFacade()
        ai_state.initialized = True
        ai_state.facade = facade
        ai_state.error = None
        assert ai_state.initialized
        assert ai_state.facade is not None
        status = ai_state.status()
        assert status["status"] == "ok"

    def test_ensure_initialized_raises_503_when_facade_none(self):
        from routers.ai import ai_state, _ensure_initialized
        from fastapi import HTTPException

        old_facade = ai_state.facade
        old_init = ai_state.initialized
        try:
            ai_state.initialized = False
            ai_state.facade = None
            with pytest.raises(HTTPException) as exc_info:
                _ensure_initialized()
            assert exc_info.value.status_code == 503
        finally:
            ai_state.initialized = old_init
            ai_state.facade = old_facade

    def test_ensure_initialized_passes_when_facade_set(self):
        from routers.ai import ai_state, _ensure_initialized
        from core.runtime.facade import EmoRuntimeFacade

        old_facade = ai_state.facade
        old_init = ai_state.initialized
        try:
            facade = EmoRuntimeFacade()
            ai_state.initialized = True
            ai_state.facade = facade
            _ensure_initialized()
        finally:
            ai_state.initialized = old_init
            ai_state.facade = old_facade
        assert True


# ═══════════════════════════════════════════════════════════════════
# 4. Lifespan shutdown is idempotent
# ═══════════════════════════════════════════════════════════════════

class TestGracefulShutdown:
    """Double shutdown and no-runtime shutdown must not error."""

    def test_double_shutdown_no_error(self):
        from core.runtime.bootstrap import EmoRuntime
        runtime = EmoRuntime(config={"worker_pool_size": 2})
        runtime.build().start()
        runtime.shutdown()
        runtime.shutdown()
        assert True

    def test_shutdown_without_start(self):
        from core.runtime.bootstrap import EmoRuntime
        runtime = EmoRuntime(config={"worker_pool_size": 2})
        runtime.shutdown()
        assert True

    def test_shutdown_without_build(self):
        from core.runtime.bootstrap import EmoRuntime
        runtime = EmoRuntime()
        runtime.shutdown()
        assert True
