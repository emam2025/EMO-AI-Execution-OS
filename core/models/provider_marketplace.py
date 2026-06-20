"""Provider Marketplace Models.

Pure models for per-workspace provider configuration and usage tracking.
Frozen dataclasses only — stdlib only.

Ref: Phase P Batch 3 (P.4 — Provider Marketplace)
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum

from core.gateway.models import ProviderType


class ProviderAccessDecision(Enum):
    ALLOWED = "allowed"
    DENIED_QUOTA_EXCEEDED = "denied_quota_exceeded"
    DENIED_NOT_CONFIGURED = "denied_not_configured"
    DENIED_INACTIVE = "denied_inactive"


@dataclass(frozen=True)
class WorkspaceProviderConfig:
    workspace_id: str = ""
    provider_type: ProviderType = ProviderType.OPENAI
    api_key_env_var: str = ""
    quota_limit: int = 10000
    cost_limit: float = 100.0
    is_active: bool = True
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def is_accessible(self) -> bool:
        return self.is_active

    def has_configured_key(self) -> bool:
        return len(self.api_key_env_var) > 0


@dataclass(frozen=True)
class ProviderUsage:
    workspace_id: str = ""
    provider_type: ProviderType = ProviderType.OPENAI
    requests_used: int = 0
    tokens_used: int = 0
    cost_incurred: float = 0.0
    last_updated: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def is_over_quota(self, quota_limit: int) -> bool:
        return self.requests_used >= quota_limit

    def is_over_cost(self, cost_limit: float) -> bool:
        return self.cost_incurred >= cost_limit

    def remaining_requests(self, quota_limit: int) -> int:
        remaining = quota_limit - self.requests_used
        return remaining if remaining > 0 else 0

    def remaining_cost(self, cost_limit: float) -> float:
        remaining = cost_limit - self.cost_incurred
        return remaining if remaining > 0 else 0.0
