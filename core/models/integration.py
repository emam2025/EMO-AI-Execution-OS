"""Integration Hub Models.

Pure models for multi-channel integration configuration.
Frozen dataclasses only — stdlib only.

Ref: Phase P Batch 4 (P.5 — Integration Hub)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum


class IntegrationChannel(Enum):
    TELEGRAM = "telegram"
    DISCORD = "discord"
    SLACK = "slack"
    WHATSAPP = "whatsapp"


class IntegrationStatus(Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    ERROR = "error"
    RATE_LIMITED = "rate_limited"


@dataclass(frozen=True)
class IntegrationConfig:
    workspace_id: str = ""
    channel_type: IntegrationChannel = IntegrationChannel.TELEGRAM
    bot_token_env_var: str = ""
    webhook_url: str = ""
    is_active: bool = True
    status: IntegrationStatus = IntegrationStatus.ACTIVE
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def is_accessible(self) -> bool:
        return self.is_active and self.status == IntegrationStatus.ACTIVE

    def has_configured_token(self) -> bool:
        return len(self.bot_token_env_var) > 0

    def has_webhook(self) -> bool:
        return len(self.webhook_url) > 0


@dataclass(frozen=True)
class MessageEnvelope:
    channel_type: IntegrationChannel = IntegrationChannel.TELEGRAM
    external_message_id: str = ""
    sender_id: str = ""
    content: str = ""
    workspace_id: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def has_content(self) -> bool:
        return len(self.content) > 0

    def has_sender(self) -> bool:
        return len(self.sender_id) > 0
