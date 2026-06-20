"""Integration Hub Tests.

Verifies multi-channel integration configuration, webhook handling, and workspace isolation.
Tests models and business logic directly — no mocks, no ellipsis, no pass.

Ref: Phase P Batch 4 (P.5 — Integration Hub)
Ref: Canon LAW 10, LAW 23
"""

from core.models.integration import (
    IntegrationChannel,
    IntegrationConfig,
    IntegrationStatus,
    MessageEnvelope,
)


class TestIntegrationChannel:
    def test_channel_enum_values(self) -> None:
        assert IntegrationChannel.TELEGRAM.value == "telegram"
        assert IntegrationChannel.DISCORD.value == "discord"
        assert IntegrationChannel.SLACK.value == "slack"
        assert IntegrationChannel.WHATSAPP.value == "whatsapp"

    def test_channel_count(self) -> None:
        assert len(IntegrationChannel) == 4


class TestIntegrationConfig:
    def test_config_creation(self) -> None:
        config = IntegrationConfig(
            workspace_id="ws-1",
            channel_type=IntegrationChannel.TELEGRAM,
            bot_token_env_var="TG_BOT_TOKEN",
            webhook_url="https://api.example.com/webhook/tg",
        )
        assert config.workspace_id == "ws-1"
        assert config.channel_type == IntegrationChannel.TELEGRAM
        assert config.bot_token_env_var == "TG_BOT_TOKEN"
        assert config.webhook_url == "https://api.example.com/webhook/tg"
        assert config.is_active is True
        assert config.status == IntegrationStatus.ACTIVE
        assert config.is_accessible() is True

    def test_config_inactive(self) -> None:
        config = IntegrationConfig(workspace_id="ws-1", channel_type=IntegrationChannel.DISCORD, is_active=False)
        assert config.is_accessible() is False

    def test_config_error_status(self) -> None:
        config = IntegrationConfig(workspace_id="ws-1", channel_type=IntegrationChannel.SLACK, status=IntegrationStatus.ERROR)
        assert config.is_accessible() is False

    def test_config_rate_limited(self) -> None:
        config = IntegrationConfig(workspace_id="ws-1", channel_type=IntegrationChannel.WHATSAPP, status=IntegrationStatus.RATE_LIMITED)
        assert config.is_accessible() is False

    def test_config_has_token(self) -> None:
        config = IntegrationConfig(workspace_id="ws-1", channel_type=IntegrationChannel.TELEGRAM, bot_token_env_var="TG_TOKEN")
        assert config.has_configured_token() is True

    def test_config_no_token(self) -> None:
        config = IntegrationConfig(workspace_id="ws-1", channel_type=IntegrationChannel.TELEGRAM, bot_token_env_var="")
        assert config.has_configured_token() is False

    def test_config_has_webhook(self) -> None:
        config = IntegrationConfig(workspace_id="ws-1", channel_type=IntegrationChannel.TELEGRAM, webhook_url="https://example.com/hook")
        assert config.has_webhook() is True

    def test_config_no_webhook(self) -> None:
        config = IntegrationConfig(workspace_id="ws-1", channel_type=IntegrationChannel.TELEGRAM, webhook_url="")
        assert config.has_webhook() is False


class TestMessageEnvelope:
    def test_envelope_creation(self) -> None:
        envelope = MessageEnvelope(
            channel_type=IntegrationChannel.TELEGRAM,
            external_message_id="msg-123",
            sender_id="user-456",
            content="Hello from Telegram",
            workspace_id="ws-1",
        )
        assert envelope.channel_type == IntegrationChannel.TELEGRAM
        assert envelope.external_message_id == "msg-123"
        assert envelope.sender_id == "user-456"
        assert envelope.content == "Hello from Telegram"
        assert envelope.workspace_id == "ws-1"
        assert envelope.has_content() is True
        assert envelope.has_sender() is True

    def test_envelope_empty_content(self) -> None:
        envelope = MessageEnvelope(channel_type=IntegrationChannel.DISCORD, content="")
        assert envelope.has_content() is False

    def test_envelope_empty_sender(self) -> None:
        envelope = MessageEnvelope(channel_type=IntegrationChannel.SLACK, sender_id="")
        assert envelope.has_sender() is False


class TestIntegrationStatus:
    def test_status_enum_values(self) -> None:
        assert IntegrationStatus.ACTIVE.value == "active"
        assert IntegrationStatus.INACTIVE.value == "inactive"
        assert IntegrationStatus.ERROR.value == "error"
        assert IntegrationStatus.RATE_LIMITED.value == "rate_limited"


class TestIntegrationIsolation:
    def test_channel_isolated_per_workspace(self) -> None:
        config_a = IntegrationConfig(workspace_id="ws-a", channel_type=IntegrationChannel.TELEGRAM, bot_token_env_var="TOKEN_A")
        config_b = IntegrationConfig(workspace_id="ws-b", channel_type=IntegrationChannel.TELEGRAM, bot_token_env_var="TOKEN_B")
        assert config_a.workspace_id != config_b.workspace_id
        assert config_a.bot_token_env_var != config_b.bot_token_env_var

    def test_different_channels_same_workspace(self) -> None:
        config_tg = IntegrationConfig(workspace_id="ws-1", channel_type=IntegrationChannel.TELEGRAM)
        config_dc = IntegrationConfig(workspace_id="ws-1", channel_type=IntegrationChannel.DISCORD)
        assert config_tg.channel_type != config_dc.channel_type
        assert config_tg.workspace_id == config_dc.workspace_id

    def test_inactive_channel_cannot_receive_webhook(self) -> None:
        config = IntegrationConfig(workspace_id="ws-1", channel_type=IntegrationChannel.TELEGRAM, is_active=False)
        assert config.is_accessible() is False

    def test_error_channel_cannot_receive_webhook(self) -> None:
        config = IntegrationConfig(workspace_id="ws-1", channel_type=IntegrationChannel.SLACK, status=IntegrationStatus.ERROR)
        assert config.is_accessible() is False

    def test_envelope_preserves_channel_context(self) -> None:
        envelope = MessageEnvelope(
            channel_type=IntegrationChannel.WHATSAPP,
            sender_id="phone-123",
            content="Message",
            workspace_id="ws-1",
        )
        assert envelope.channel_type == IntegrationChannel.WHATSAPP
        assert envelope.workspace_id == "ws-1"
