import os
import logging
from datetime import datetime, timezone
from typing import Optional

import keyring

logger = logging.getLogger("emo_ai.keychain")

SERVICE_NAME = "EMO-AI-LLM-Credentials"
AUDIT_LOGGER = logging.getLogger("emo_ai.audit.keychain")


class KeychainProvider:
    """OS-level credential vault with secure dev fallback.

    Production: reads/writes/deletes via ``keyring`` (macOS Keychain,
    Linux Secret Service, Windows Credential Manager).

    Development: falls back to ``os.getenv("{ACCOUNT}_API_KEY")`` when
    keyring is unavailable AND ``ENVIRONMENT=development``.

    Every operation is logged to the ``emo_ai.audit.keychain`` logger.

    Usage::

        provider = KeychainProvider()
        key = provider.get("openrouter")
        provider.set("openrouter", "sk-or-...")
        provider.delete("openrouter")
    """

    def __init__(self, service: str = SERVICE_NAME):
        self.service = service
        self._is_dev = os.getenv("ENVIRONMENT", "production").lower() == "development"

    # ── Public API ────────────────────────────────────────────────

    def get(self, account: str) -> Optional[str]:
        """Retrieve a secret from the OS keychain.

        Returns ``None`` if the secret does not exist AND the
        environment is production (no fallback).  In development
        mode, falls back to ``os.getenv("{account.upper()}_API_KEY")``.
        """
        try:
            secret = keyring.get_password(self.service, account)
            if secret is not None:
                self._audit("read", account, "keyring", "success")
                return secret
        except keyring.errors.KeyringError as e:
            logger.warning("[KEYCHAIN] Read failed for %s: %s", account, e)

        if self._is_dev:
            env_key = f"{account.upper()}_API_KEY"
            fallback = os.getenv(env_key)
            if fallback is not None:
                self._audit("read", account, "env_fallback", "success")
                logger.warning(
                    "[SECURITY] Using ENV fallback for %s via %s. "
                    "PRODUCTION MUST USE KEYRING.",
                    account, env_key,
                )
            else:
                self._audit("read", account, "env_fallback", "miss")
                logger.debug("[KEYCHAIN] No fallback env var %s for %s", env_key, account)
            return fallback

        self._audit("read", account, "keyring", "miss")
        return None

    def set(self, account: str, secret: str) -> None:
        """Store a secret in the OS keychain."""
        try:
            keyring.set_password(self.service, account, secret)
            self._audit("set", account, "keyring", "success")
            logger.info("[AUDIT] Credential stored for %s", account)
        except keyring.errors.KeyringError as e:
            self._audit("set", account, "keyring", "error", detail=str(e))
            logger.error("[KEYCHAIN] Failed to store %s: %s", account, e)

    def delete(self, account: str) -> None:
        """Delete a secret from the OS keychain."""
        try:
            keyring.delete_password(self.service, account)
            self._audit("delete", account, "keyring", "success")
            logger.info("[AUDIT] Credential deleted for %s", account)
        except keyring.errors.PasswordDeleteError:
            self._audit("delete", account, "keyring", "miss")
            pass
        except keyring.errors.KeyringError as e:
            self._audit("delete", account, "keyring", "error", detail=str(e))
            logger.error("[KEYCHAIN] Failed to delete %s: %s", account, e)

    # ── Helpers ───────────────────────────────────────────────────

    def _audit(self, action: str, account: str, source: str, status: str, detail: str = "") -> None:
        AUDIT_LOGGER.info(
            "ts=%s action=%s account=%s source=%s status=%s detail=%s",
            datetime.now(timezone.utc).isoformat(),
            action,
            account,
            source,
            status,
            detail,
        )
