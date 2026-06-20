"""Provider Gateway Tests.

Verifies policy evaluation, quota enforcement, fallback routing,
and architectural isolation.

Ref: Phase P Batch 1E
Ref: Canon LAW 10, LAW 13, LAW 23
"""

from core.gateway.models import (
    PolicyDecision,
    ProviderConfig,
    ProviderPolicy,
    ProviderType,
    UsageQuota,
)
from core.gateway.provider_gateway import ProviderGateway


def _build_gateway(
    blocked_models=None,
    allowed_models=None,
    over_quota=False,
) -> ProviderGateway:
    blocked = blocked_models or []
    allowed = allowed_models or []
    policy = ProviderPolicy(
        provider=ProviderType.OPENAI,
        allowed_models=allowed,
        blocked_models=blocked,
        max_tokens_per_request=4096,
        max_requests_per_minute=60,
    )
    config = ProviderConfig(
        provider=ProviderType.OPENAI,
        api_key_env="OPENAI_API_KEY",
        base_url="https://api.openai.com/v1",
        fallback_provider=ProviderType.LOCAL,
    )
    quota = UsageQuota(
        provider=ProviderType.OPENAI,
        requests_used=1000 if over_quota else 10,
        requests_limit=1000,
        tokens_used=500000,
        tokens_limit=1000000,
    )
    return ProviderGateway(
        policies={ProviderType.OPENAI: policy},
        configs={ProviderType.OPENAI: config},
        quotas={ProviderType.OPENAI: quota},
    )


class TestProviderGateway:
    def test_allows_valid_request(self) -> None:
        gw = _build_gateway(allowed_models=["gpt-4", "gpt-3.5-turbo"])
        decision = gw.evaluate_policy(ProviderType.OPENAI, "gpt-4")
        assert decision == PolicyDecision.ALLOW

    def test_denies_blocked_model(self) -> None:
        gw = _build_gateway(blocked_models=["gpt-4-turbo"])
        decision = gw.evaluate_policy(ProviderType.OPENAI, "gpt-4-turbo")
        assert decision == PolicyDecision.DENY

    def test_falls_back_when_over_quota(self) -> None:
        gw = _build_gateway(over_quota=True)
        decision = gw.evaluate_policy(ProviderType.OPENAI, "gpt-4")
        assert decision == PolicyDecision.FALLBACK

    def test_returns_correct_adapter_name(self) -> None:
        gw = _build_gateway()
        assert gw.get_adapter_name(ProviderType.OPENAI) == "openai_adapter"
        assert gw.get_adapter_name(ProviderType.ANTHROPIC) == "anthropic_adapter"
        assert gw.get_adapter_name(ProviderType.LOCAL) == "local_adapter"

    def test_returns_fallback_provider(self) -> None:
        gw = _build_gateway()
        fallback = gw.get_fallback_provider(ProviderType.OPENAI)
        assert fallback == ProviderType.LOCAL

    def test_denies_unknown_provider(self) -> None:
        gw = _build_gateway()
        decision = gw.evaluate_policy(ProviderType.AZURE, "gpt-4")
        assert decision == PolicyDecision.DENY
