"""Provider Gateway: policy evaluation and routing.

Evaluates provider policies and quotas. No execution logic.
Decides ALLOW/DENY/FALLBACK based on configuration.

Ref: Phase P Batch 1C
Ref: Canon LAW 10, LAW 13, LAW 23
"""

from __future__ import annotations

import logging
from typing import Dict, Optional

from core.gateway.models import (
    PolicyDecision,
    ProviderConfig,
    ProviderPolicy,
    ProviderType,
    UsageQuota,
)

logger = logging.getLogger("emo_ai.gateway.provider")


class ProviderGateway:
    """Policy router for AI provider selection.

    Evaluates policies and quotas. No execution — routing only.
    Dependencies injected via constructor (LAW 13).
    """

    def __init__(
        self,
        policies: Dict[ProviderType, ProviderPolicy],
        configs: Dict[ProviderType, ProviderConfig],
        quotas: Dict[ProviderType, UsageQuota],
    ) -> None:
        self._policies = policies
        self._configs = configs
        self._quotas = quotas

    def evaluate_policy(
        self,
        provider: ProviderType,
        model: str,
    ) -> PolicyDecision:
        """Evaluate whether a request to a provider/model is allowed.

        Returns ALLOW, DENY, or FALLBACK.
        """
        policy = self._policies.get(provider)
        if policy is None:
            logger.warning("No policy for provider %s, defaulting DENY", provider.value)
            return PolicyDecision.DENY

        if model in policy.blocked_models:
            logger.info("Model %s blocked for provider %s", model, provider.value)
            return PolicyDecision.DENY

        if policy.allowed_models and model not in policy.allowed_models:
            logger.info("Model %s not in allowed list for provider %s", model, provider.value)
            return PolicyDecision.DENY

        quota = self._quotas.get(provider)
        if quota is not None and quota.is_over_quota():
            logger.warning("Provider %s over quota, falling back", provider.value)
            return PolicyDecision.FALLBACK

        return PolicyDecision.ALLOW

    def get_adapter_name(self, provider: ProviderType) -> str:
        """Return the adapter module name for a provider."""
        adapter_map = {
            ProviderType.OPENAI: "openai_adapter",
            ProviderType.ANTHROPIC: "anthropic_adapter",
            ProviderType.GOOGLE: "google_adapter",
            ProviderType.GEMINI: "gemini_adapter",
            ProviderType.AZURE: "azure_adapter",
            ProviderType.LOCAL: "local_adapter",
        }
        return adapter_map.get(provider, "local_adapter")

    def get_fallback_provider(self, provider: ProviderType) -> ProviderType:
        """Return the configured fallback provider."""
        config = self._configs.get(provider)
        if config is not None:
            return config.fallback_provider
        return ProviderType.LOCAL
