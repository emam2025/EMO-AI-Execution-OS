"""E3.1 — SecretInjector: ephemeral secret injection into sandbox contexts.

Injects secrets into SandboxContext.environment securely and
cleans up after execution completes.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

from core.runtime.secrets.vault import RuntimeVault

logger = logging.getLogger("emo_ai.secrets.injector")


class SecretInjector:
    """Injects vault secrets into execution environments.

    Usage:
        injector = SecretInjector(vault)
        injector.inject(context, "exec_123", ["DB_PASSWORD", "API_KEY"])
        # ... execution runs ...
        injector.cleanup(context, "exec_123")
    """

    def __init__(self, vault: RuntimeVault) -> None:
        self._vault = vault
        self._injection_log: List[Dict[str, Any]] = []

    def inject(
        self,
        environment: Dict[str, str],
        execution_id: str,
        secret_keys: List[str],
        scope: str = "",
    ) -> int:
        """Inject secrets into an execution environment.

        Args:
            environment: The execution's environment dict (mutated in-place).
            execution_id: The execution requesting the secrets.
            secret_keys: List of secret keys to inject.
            scope: Scope filter for secret access.

        Returns:
            Number of secrets successfully injected.
        """
        count = 0
        for key in secret_keys:
            value = self._vault.retrieve(key, scope=scope or execution_id)
            if value is not None:
                env_key = f"EMO_SECRET_{key}"
                environment[env_key] = value
                count += 1
                self._log_injection(key, execution_id, env_key)
            else:
                logger.warning("Secret '%s' not found for exec %s", key, execution_id)
        return count

    def inject_all_for_scope(
        self,
        environment: Dict[str, str],
        execution_id: str,
        scope: str = "",
    ) -> int:
        """Inject all secrets matching a scope into the environment."""
        scope_key = scope or execution_id
        keys = self._vault.list_secrets(scope=scope_key)
        return self.inject(environment, execution_id, keys, scope=scope_key)

    def cleanup(self, environment: Dict[str, str], execution_id: str) -> int:
        """Remove injected secrets from an environment.

        Also deletes the secrets from the vault.
        """
        removed = 0
        env_keys_to_del = [k for k in environment if k.startswith("EMO_SECRET_")]
        for k in env_keys_to_del:
            del environment[k]
            removed += 1

        # Remove execution-scoped secrets from vault
        for sk in self._vault.list_secrets(scope=execution_id):
            self._vault.delete(sk)
            removed += 1

        if removed:
            logger.info("Cleanup for exec %s: removed %d secrets", execution_id, removed)
        return removed

    def injection_log(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Return recent injection events."""
        return self._injection_log[-limit:]

    def _log_injection(self, secret_key: str, execution_id: str, env_key: str) -> None:
        self._injection_log.append({
            "secret_key": secret_key,
            "execution_id": execution_id,
            "env_key": env_key,
            "timestamp": time.time(),
        })
