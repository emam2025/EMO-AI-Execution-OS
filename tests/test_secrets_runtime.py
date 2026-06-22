"""Tests for Secrets Runtime — Ephemeral Secret Injection.

6 tests covering registration, scoped injection, denial, expiration,
revocation, and audit trail.

Ref: Phase E.3 — Secrets Runtime (Ephemeral Secret Injection)
"""

import asyncio
import time

import pytest

from core.models.event import EventTopic
from core.models.secrets import SecretRef, SecretScope
from core.security.secrets_runtime import SecretsRuntime


class MockEventBus:
    def __init__(self) -> None:
        self.published: list[dict] = []

    async def publish(self, topic: EventTopic, event) -> None:
        self.published.append({"topic": topic, "event": event})

    def subscribe(self, topic, handler) -> str:
        return "mock-sub-001"

    def unsubscribe(self, subscription_id: str) -> None:
        pass


# --- Tests ---


def test_register_secret_with_scope():
    """E.3.1: Secret registration stores ref and encrypted value."""
    runtime = SecretsRuntime()
    ref = SecretRef(
        secret_id="api_key_1",
        scope=SecretScope.TOOL,
        expiration_seconds=3600.0,
        allowed_tools=("web_fetch",),
    )
    runtime.register_secret("api_key_1", "sk-test-12345", ref)

    assert runtime.is_secret_registered("api_key_1") is True
    assert runtime.is_secret_registered("unknown_secret") is False

    stored_ref = runtime.get_ref("api_key_1")
    assert stored_ref is not None
    assert stored_ref.secret_id == "api_key_1"
    assert stored_ref.scope == SecretScope.TOOL
    assert stored_ref.allowed_tools == ("web_fetch",)


def test_inject_secret_for_allowed_tool():
    """E.3.1: Authorized tool receives decrypted secret."""
    runtime = SecretsRuntime()
    ref = SecretRef(
        secret_id="api_key_1",
        scope=SecretScope.TOOL,
        allowed_tools=("web_fetch", "data_reader"),
    )
    runtime.register_secret("api_key_1", "sk-test-12345", ref)

    injected = runtime.inject_for_tool(
        tool_id="web_fetch",
        requested_secrets=["api_key_1"],
    )

    assert "api_key_1" in injected
    assert injected["api_key_1"] == "sk-test-12345"


def test_inject_secret_denied_for_unauthorized_tool():
    """E.3.1: Unauthorized tool cannot access restricted secret."""
    runtime = SecretsRuntime()
    ref = SecretRef(
        secret_id="api_key_1",
        scope=SecretScope.TOOL,
        allowed_tools=("web_fetch",),
    )
    runtime.register_secret("api_key_1", "sk-test-12345", ref)

    injected = runtime.inject_for_tool(
        tool_id="data_reader",
        requested_secrets=["api_key_1"],
    )

    assert "api_key_1" not in injected
    assert len(injected) == 0

    log = runtime.get_access_log()
    denied_entries = [e for e in log if e["action"] == "denied"]
    assert len(denied_entries) == 1
    assert denied_entries[0]["secret_id"] == "api_key_1"
    assert denied_entries[0]["tool_id"] == "data_reader"


def test_secret_expiration_enforced():
    """E.3.1: Expired secrets are denied injection."""
    runtime = SecretsRuntime()
    ref = SecretRef(
        secret_id="short_lived",
        scope=SecretScope.TOOL,
        expiration_seconds=0.01,
        allowed_tools=("tool_a",),
    )
    runtime.register_secret("short_lived", "value_123", ref)

    injected = runtime.inject_for_tool(
        tool_id="tool_a",
        requested_secrets=["short_lived"],
    )
    assert "short_lived" in injected

    time.sleep(0.02)

    injected = runtime.inject_for_tool(
        tool_id="tool_a",
        requested_secrets=["short_lived"],
    )
    assert "short_lived" not in injected


def test_revoke_all_for_tool_clears_secrets():
    """E.3.1: Revocation clears all active injections for a tool."""
    runtime = SecretsRuntime()
    ref1 = SecretRef(secret_id="key_1", scope=SecretScope.TOOL, allowed_tools=("tool_a",))
    ref2 = SecretRef(secret_id="key_2", scope=SecretScope.TOOL, allowed_tools=("tool_a",))
    runtime.register_secret("key_1", "val_1", ref1)
    runtime.register_secret("key_2", "val_2", ref2)

    injected = runtime.inject_for_tool(
        tool_id="tool_a",
        requested_secrets=["key_1", "key_2"],
    )
    assert len(injected) == 2

    runtime.revoke_all_for_tool("tool_a")

    log = runtime.get_access_log()
    revoked_entries = [e for e in log if e["action"] == "revoked"]
    assert len(revoked_entries) == 2
    revoked_ids = {e["secret_id"] for e in revoked_entries}
    assert revoked_ids == {"key_1", "key_2"}


@pytest.mark.asyncio
async def test_secret_access_publishes_audit_event():
    """E.3.1: Secret access publishes SECURITY_VIOLATION audit event."""
    event_bus = MockEventBus()
    runtime = SecretsRuntime(event_bus=event_bus)
    ref = SecretRef(
        secret_id="api_key_1",
        scope=SecretScope.TOOL,
        allowed_tools=("web_fetch",),
    )
    runtime.register_secret("api_key_1", "sk-test-12345", ref)

    runtime.inject_for_tool(
        tool_id="web_fetch",
        requested_secrets=["api_key_1"],
    )
    await asyncio.sleep(0.01)

    assert len(event_bus.published) == 1
    published = event_bus.published[0]
    assert published["topic"] == EventTopic.SECURITY_VIOLATION
    assert published["event"].payload["tool_id"] == "web_fetch"
    assert published["event"].payload["secret_id"] == "api_key_1"
    assert published["event"].payload["action"] == "injected"
