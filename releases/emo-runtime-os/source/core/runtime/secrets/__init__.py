"""E3 — Secrets Runtime.

Ephemeral secret injection, runtime vault, scoped credentials,
and secret expiration.
"""

from core.runtime.secrets.vault import RuntimeVault, SecretEntry
from core.runtime.secrets.injector import SecretInjector
from core.runtime.secrets.credentials import CredentialManager, ScopedCredential

__all__ = [
    "RuntimeVault",
    "SecretEntry",
    "SecretInjector",
    "CredentialManager",
    "ScopedCredential",
]
