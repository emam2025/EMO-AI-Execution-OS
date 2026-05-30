"""Phase 4.3.2 — NetworkIsolation: outbound request control.

Intercepts and filters network requests based on capability policy
and domain whitelists.
"""

from __future__ import annotations

import logging
import socket
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from urllib.parse import urlparse

from core.runtime.io.io_policy_engine import IOViolation

logger = logging.getLogger("emo_ai.io.network")


class NetworkBlocked(IOViolation):
    """Raised when a network request is blocked."""

    def __init__(self, url: str, reason: str, tool: str = ""):
        super().__init__(f"network_request:{url}", reason, tool)


@dataclass
class NetworkPolicy:
    """Network access policy for a tool."""
    allow_outbound: bool = False
    allowed_domains: List[str] = field(default_factory=list)
    block_private: bool = True
    max_requests: int = 100
    max_request_size: int = 10 * 1024 * 1024


class NetworkIsolation:
    """Controls and filters outbound network requests.

    Provides a logical interception layer — in production this
    would hook into OS-level or proxy-based filtering.
    """

    PRIVATE_PREFIXES = (
        "10.", "172.16.", "172.17.", "172.18.", "172.19.",
        "172.20.", "172.21.", "172.22.", "172.23.", "172.24.",
        "172.25.", "172.26.", "172.27.", "172.28.", "172.29.",
        "172.30.", "172.31.", "192.168.", "127.", "169.254.",
        "0.", "::1", "fc00:", "fe80:",
    )

    def __init__(self) -> None:
        self._policies: Dict[str, NetworkPolicy] = {}
        self._default_policy = NetworkPolicy()

    def set_policy(self, tool: str, policy: NetworkPolicy) -> None:
        """Set the network policy for a tool."""
        self._policies[tool] = policy

    def check_request(self, tool: str, url: str) -> None:
        """Check if a network request is allowed.

        Args:
            tool: Tool making the request.
            url: Target URL.

        Raises:
            NetworkBlocked: If the request is not permitted.
        """
        policy = self._policies.get(tool, self._default_policy)

        if not policy.allow_outbound:
            raise NetworkBlocked(url, "Outbound network blocked", tool)

        parsed = urlparse(url)
        hostname = parsed.hostname or ""

        if policy.block_private and self._is_private(hostname):
            raise NetworkBlocked(
                url, f"Private address blocked: {hostname}", tool,
            )

        if policy.allowed_domains:
            domain_match = any(
                hostname == d or hostname.endswith(f".{d}")
                for d in policy.allowed_domains
            )
            if not domain_match:
                raise NetworkBlocked(
                    url,
                    f"Domain {hostname} not in whitelist: {policy.allowed_domains}",
                    tool,
                )

    @staticmethod
    def _is_private(hostname: str) -> bool:
        try:
            addr = socket.getaddrinfo(hostname, 80)[0][4][0]
            return any(addr.startswith(p) for p in NetworkIsolation.PRIVATE_PREFIXES)
        except Exception:
            return hostname in ("localhost", "127.0.0.1", "::1")
