import os
import logging
import time
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple

import keyring

logger = logging.getLogger("emo_ai.keychain")

SERVICE_NAME = "emo-desktop"  # must match Rust keyring service name
AUDIT_LOGGER = logging.getLogger("emo_ai.audit.keychain")
_CACHE_TTL = 30.0  # seconds


class KeychainProvider:
    """OS-level credential vault with secure dev fallback.

    Production: reads/writes/deletes via ``keyring`` (macOS Keychain,
    Linux Secret Service, Windows Credential Manager).

    Development: falls back to ``os.getenv("{ACCOUNT}_API_KEY")`` when
    keyring is unavailable AND ``ENVIRONMENT=development``.

    Every operation is logged to the ``emo_ai.audit.keychain`` logger.

    Caches retrieved secrets in memory for ``_CACHE_TTL`` seconds
    to avoid synchronous OS keychain IPC on every request.

    Usage::

        provider = KeychainProvider()
        key = provider.get("openrouter")
        provider.set("openrouter", "sk-or-...")
        provider.delete("openrouter")
    """

    _cache: Dict[str, Tuple[float, str]] = {}  # account -> (timestamp, value)

    def __init__(self, service: str = SERVICE_NAME):
        self.service = service
        self._is_dev = os.getenv("ENVIRONMENT", "production").lower() == "development"

    # ── Public API ────────────────────────────────────────────────

    @staticmethod
    def _keyring_account(provider: str) -> str:
        """Normalize provider name to keyring account name (match Rust prefix)."""
        return f"provider_{provider}"

    def get(self, provider: str) -> Optional[str]:
        """Retrieve a secret from the OS keychain with in-memory caching.

        Args:
            provider: Provider name (e.g. 'openrouter', 'groq').
            Stored under keyring account ``provider_{name}``.

        Returns ``None`` if the secret does not exist AND the
        environment is production (no fallback).  In development
        mode, falls back to ``os.getenv("{name.upper()}_API_KEY")``.
        """
        account = self._keyring_account(provider)

        # Check cache first
        now = time.time()
        cached = self._cache.get(account)
        if cached and (now - cached[0]) < _CACHE_TTL:
            return cached[1]

        try:
            secret = keyring.get_password(self.service, account)
            if secret is not None:
                self._cache[account] = (now, secret)
                self._audit("read", account, "keyring", "success")
                return secret
        except keyring.errors.KeyringError as e:
            logger.warning("[KEYCHAIN] Read failed for %s: %s", account, e)

        if self._is_dev:
            env_key = f"{provider.upper()}_API_KEY"
            fallback = os.getenv(env_key)
            if fallback is not None:
                self._cache[account] = (now, fallback)
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

    def set(self, provider: str, secret: str) -> None:
        """Store a secret in the OS keychain.

        Args:
            provider: Provider name (e.g. 'openrouter', 'groq').
        """
        account = self._keyring_account(provider)
        try:
            keyring.set_password(self.service, account, secret)
            now = time.time()
            self._cache[account] = (now, secret)
            self._audit("set", account, "keyring", "success")
            logger.info("[AUDIT] Credential stored for %s", account)
        except keyring.errors.KeyringError as e:
            self._audit("set", account, "keyring", "error", detail=str(e))
            logger.error("[KEYCHAIN] Failed to store %s: %s", account, e)

    def delete(self, provider: str) -> None:
        """Delete a secret from the OS keychain.

        Args:
            provider: Provider name (e.g. 'openrouter', 'groq').
        """
        account = self._keyring_account(provider)
        self._cache.pop(account, None)
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
