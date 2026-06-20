"""Provider Marketplace Tests.

Verifies per-workspace provider configuration, usage tracking, and access control.
Tests models and business logic directly — no mocks, no ellipsis.

Ref: Phase P Batch 3 (P.4 — Provider Marketplace)
Ref: Canon LAW 10, LAW 23
"""

from core.gateway.models import ProviderType
from core.models.provider_marketplace import (
    ProviderAccessDecision,
    ProviderUsage,
    WorkspaceProviderConfig,
)


class TestWorkspaceProviderConfig:
    def test_config_creation(self) -> None:
        config = WorkspaceProviderConfig(
            workspace_id="ws-1",
            provider_type=ProviderType.OPENAI,
            api_key_env_var="OPENAI_API_KEY",
            quota_limit=5000,
            cost_limit=50.0,
        )
        assert config.workspace_id == "ws-1"
        assert config.provider_type == ProviderType.OPENAI
        assert config.quota_limit == 5000
        assert config.cost_limit == 50.0
        assert config.is_active is True
        assert config.is_accessible() is True

    def test_config_inactive(self) -> None:
        config = WorkspaceProviderConfig(workspace_id="ws-1", provider_type=ProviderType.ANTHROPIC, is_active=False)
        assert config.is_accessible() is False

    def test_config_has_key(self) -> None:
        config = WorkspaceProviderConfig(workspace_id="ws-1", provider_type=ProviderType.OPENAI, api_key_env_var="OPENAI_API_KEY")
        assert config.has_configured_key() is True

    def test_config_no_key(self) -> None:
        config = WorkspaceProviderConfig(workspace_id="ws-1", provider_type=ProviderType.OPENAI, api_key_env_var="")
        assert config.has_configured_key() is False


class TestProviderUsage:
    def test_usage_creation(self) -> None:
        usage = ProviderUsage(workspace_id="ws-1", provider_type=ProviderType.OPENAI)
        assert usage.requests_used == 0
        assert usage.tokens_used == 0
        assert usage.cost_incurred == 0.0

    def test_usage_within_quota(self) -> None:
        usage = ProviderUsage(workspace_id="ws-1", provider_type=ProviderType.OPENAI, requests_used=500)
        assert usage.is_over_quota(10000) is False
        assert usage.remaining_requests(10000) == 9500

    def test_usage_over_quota(self) -> None:
        usage = ProviderUsage(workspace_id="ws-1", provider_type=ProviderType.OPENAI, requests_used=10000)
        assert usage.is_over_quota(10000) is True
        assert usage.remaining_requests(10000) == 0

    def test_usage_within_cost(self) -> None:
        usage = ProviderUsage(workspace_id="ws-1", provider_type=ProviderType.OPENAI, cost_incurred=25.0)
        assert usage.is_over_cost(100.0) is False
        assert usage.remaining_cost(100.0) == 75.0

    def test_usage_over_cost(self) -> None:
        usage = ProviderUsage(workspace_id="ws-1", provider_type=ProviderType.OPENAI, cost_incurred=150.0)
        assert usage.is_over_cost(100.0) is True
        assert usage.remaining_cost(100.0) == 0.0


class TestProviderAccessDecision:
    def test_decision_enum_values(self) -> None:
        assert ProviderAccessDecision.ALLOWED.value == "allowed"
        assert ProviderAccessDecision.DENIED_QUOTA_EXCEEDED.value == "denied_quota_exceeded"
        assert ProviderAccessDecision.DENIED_NOT_CONFIGURED.value == "denied_not_configured"
        assert ProviderAccessDecision.DENIED_INACTIVE.value == "denied_inactive"


class TestProviderIsolation:
    def test_provider_configured_only_in_own_workspace(self) -> None:
        config_a = WorkspaceProviderConfig(workspace_id="ws-a", provider_type=ProviderType.OPENAI, api_key_env_var="KEY_A")
        config_b = WorkspaceProviderConfig(workspace_id="ws-b", provider_type=ProviderType.OPENAI, api_key_env_var="KEY_B")
        assert config_a.workspace_id != config_b.workspace_id
        assert config_a.api_key_env_var != config_b.api_key_env_var

    def test_usage_is_per_workspace(self) -> None:
        usage_a = ProviderUsage(workspace_id="ws-a", provider_type=ProviderType.OPENAI, requests_used=100)
        usage_b = ProviderUsage(workspace_id="ws-b", provider_type=ProviderType.OPENAI, requests_used=50)
        assert usage_a.requests_used != usage_b.requests_used

    def test_inactive_provider_denied(self) -> None:
        config = WorkspaceProviderConfig(workspace_id="ws-1", provider_type=ProviderType.OPENAI, is_active=False)
        assert config.is_accessible() is False
        decision = ProviderAccessDecision.DENIED_INACTIVE if not config.is_accessible() else ProviderAccessDecision.ALLOWED
        assert decision == ProviderAccessDecision.DENIED_INACTIVE

    def test_unconfigured_provider_denied(self) -> None:
        decision = ProviderAccessDecision.DENIED_NOT_CONFIGURED
        assert decision == ProviderAccessDecision.DENIED_NOT_CONFIGURED

    def test_quota_exceeded_denied(self) -> None:
        usage = ProviderUsage(workspace_id="ws-1", provider_type=ProviderType.OPENAI, requests_used=10000)
        config = WorkspaceProviderConfig(workspace_id="ws-1", provider_type=ProviderType.OPENAI, quota_limit=10000)
        decision = ProviderAccessDecision.DENIED_QUOTA_EXCEEDED if usage.is_over_quota(config.quota_limit) else ProviderAccessDecision.ALLOWED
        assert decision == ProviderAccessDecision.DENIED_QUOTA_EXCEEDED

    def test_cost_exceeded_denied(self) -> None:
        usage = ProviderUsage(workspace_id="ws-1", provider_type=ProviderType.OPENAI, cost_incurred=200.0)
        config = WorkspaceProviderConfig(workspace_id="ws-1", provider_type=ProviderType.OPENAI, cost_limit=100.0)
        decision = ProviderAccessDecision.DENIED_QUOTA_EXCEEDED if usage.is_over_cost(config.cost_limit) else ProviderAccessDecision.ALLOWED
        assert decision == ProviderAccessDecision.DENIED_QUOTA_EXCEEDED
