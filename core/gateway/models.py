"""Provider Gateway Models.

Pure frozen dataclasses and Enums for the Provider Gateway.
No business logic, no execution. stdlib only, zero internal imports.

Ref: Phase P Batch 1B
Ref: Canon LAW 10, LAW 23
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List


class ProviderType(Enum):
    """Supported AI provider types."""

    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    GEMINI = "gemini"
    AZURE = "azure"
    LOCAL = "local"


class PolicyDecision(Enum):
    """Policy evaluation outcome."""

    ALLOW = "allow"
    DENY = "deny"
    FALLBACK = "fallback"


@dataclass(frozen=True)
class ProviderPolicy:
    """Policy rules for a specific provider."""

    provider: ProviderType
    allowed_models: List[str] = field(default_factory=list)
    blocked_models: List[str] = field(default_factory=list)
    max_tokens_per_request: int = 4096
    max_requests_per_minute: int = 60
    require_approval: bool = False


@dataclass(frozen=True)
class ProviderConfig:
    """Configuration for a provider connection."""

    provider: ProviderType
    api_key_env: str
    base_url: str = ""
    timeout_seconds: int = 30
    retry_count: int = 3
    fallback_provider: ProviderType = ProviderType.LOCAL


@dataclass(frozen=True)
class UsageQuota:
    """Usage quota tracking for a provider."""

    provider: ProviderType
    requests_used: int = 0
    requests_limit: int = 1000
    tokens_used: int = 0
    tokens_limit: int = 1000000

    def is_over_quota(self) -> bool:
        """Check if usage exceeds quota limits."""
        return self.requests_used >= self.requests_limit or self.tokens_used >= self.tokens_limit

    def remaining_requests(self) -> int:
        """Return remaining request quota."""
        return max(0, self.requests_limit - self.requests_used)

    def remaining_tokens(self) -> int:
        """Return remaining token quota."""
        return max(0, self.tokens_limit - self.tokens_used)
