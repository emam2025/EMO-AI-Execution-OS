"""E4 — WorkerVerifier: trust attestation for remote/unverified workers.

Protocol:
  1. Engine sends a challenge (nonce) to the worker
  2. Worker responds with a signed challenge + identity proof
  3. Engine validates and upgrades trust: UNVERIFIED → TRUSTED
  4. Failed verification → worker stays UNVERIFIED or gets blacklisted
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from core.security.capabilities import TrustLevel

logger = logging.getLogger("emo_ai.security.worker_verifier")


@dataclass
class VerificationResult:
    """Result of a worker verification attempt."""
    worker_id: str
    success: bool
    trust_level: TrustLevel
    reason: str = ""
    verified_at: float = 0.0
    challenge: str = ""


class WorkerVerifier:
    """Verifies worker identity and upgrades trust level.

    The verifier issues cryptographic challenges that workers must
    sign with their secret key. Successful verification upgrades
    a worker from UNVERIFIED to TRUSTED.

    Usage:
        verifier = WorkerVerifier()
        challenge = verifier.issue_challenge("worker_123")
        # worker signs challenge with its secret
        response = compute_worker_response(challenge, worker_secret)
        result = verifier.verify_response("worker_123", challenge, response)
        if result.success:
            worker.trust_level = result.trust_level
    """

    def __init__(self, master_secret: str = "") -> None:
        self._master_secret = master_secret or os.urandom(32).hex()
        self._challenges: Dict[str, Dict[str, Any]] = {}
        self._verification_log: List[Dict[str, Any]] = []
        self._blacklist: set = set()
        self._trust_overrides: Dict[str, TrustLevel] = {}

    def issue_challenge(self, worker_id: str, ttl: float = 60.0) -> str:
        """Issue a cryptographic challenge for a worker.

        The worker must prove identity by signing this challenge.
        """
        nonce = os.urandom(32).hex()
        raw = f"{worker_id}:{nonce}:{time.time()}:{self._master_secret}"
        challenge = hashlib.sha256(raw.encode()).hexdigest()
        self._challenges[challenge] = {
            "worker_id": worker_id,
            "nonce": nonce,
            "issued_at": time.time(),
            "ttl": ttl,
        }
        logger.debug("Issued challenge for worker %s", worker_id)
        return challenge

    def verify_response(
        self, worker_id: str, challenge: str, response: str
    ) -> VerificationResult:
        """Verify a worker's response to a challenge.

        The expected response is HMAC-SHA256(challenge, worker_secret).
        """
        now = time.time()

        challenge_data = self._challenges.get(challenge)
        if challenge_data is None:
            return VerificationResult(
                worker_id=worker_id, success=False,
                trust_level=TrustLevel.UNVERIFIED,
                reason="Unknown challenge",
            )

        elapsed = now - challenge_data["issued_at"]
        if elapsed > challenge_data.get("ttl", 60):
            del self._challenges[challenge]
            return VerificationResult(
                worker_id=worker_id, success=False,
                trust_level=TrustLevel.UNVERIFIED,
                reason="Challenge expired",
            )

        if challenge_data["worker_id"] != worker_id:
            del self._challenges[challenge]
            return VerificationResult(
                worker_id=worker_id, success=False,
                trust_level=TrustLevel.UNVERIFIED,
                reason="Worker ID mismatch",
            )

        if worker_id in self._blacklist:
            return VerificationResult(
                worker_id=worker_id, success=False,
                trust_level=TrustLevel.UNVERIFIED,
                reason="Worker is blacklisted",
            )

        expected = self._compute_expected_response(challenge, worker_id)
        if not hmac.compare_digest(response, expected):
            self._blacklist.add(worker_id)
            del self._challenges[challenge]
            self._log_verification(worker_id, False, "Invalid response signature")
            return VerificationResult(
                worker_id=worker_id, success=False,
                trust_level=TrustLevel.UNVERIFIED,
                reason="Invalid response signature",
            )

        del self._challenges[challenge]
        self._trust_overrides[worker_id] = TrustLevel.TRUSTED
        self._log_verification(worker_id, True, "Verified successfully")
        logger.info("Worker %s verified → TRUSTED", worker_id)
        return VerificationResult(
            worker_id=worker_id, success=True,
            trust_level=TrustLevel.TRUSTED,
            reason="Verified successfully",
            verified_at=now, challenge=challenge,
        )

    @staticmethod
    def compute_worker_response(challenge: str, worker_secret: str) -> str:
        """Compute the expected response for a worker (used on worker side)."""
        return hmac.new(
            worker_secret.encode(), challenge.encode(), hashlib.sha256,
        ).hexdigest()

    def get_trust_level(self, worker_id: str) -> TrustLevel:
        """Get effective trust level for a worker."""
        if worker_id in self._blacklist:
            return TrustLevel.UNVERIFIED
        return self._trust_overrides.get(worker_id, TrustLevel.UNVERIFIED)

    def is_verified(self, worker_id: str) -> bool:
        return self.get_trust_level(worker_id) == TrustLevel.TRUSTED

    def blacklist(self, worker_id: str, reason: str = "") -> None:
        self._blacklist.add(worker_id)
        self._trust_overrides.pop(worker_id, None)
        logger.warning("Blacklisted worker %s: %s", worker_id, reason)

    def unblacklist(self, worker_id: str) -> bool:
        if worker_id in self._blacklist:
            self._blacklist.discard(worker_id)
            return True
        return False

    def set_trust_override(self, worker_id: str, level: TrustLevel) -> None:
        self._trust_overrides[worker_id] = level
        logger.info("Trust override for %s → %s", worker_id, level)

    def clear_trust(self, worker_id: str) -> None:
        self._trust_overrides.pop(worker_id, None)
        self._blacklist.discard(worker_id)

    def _compute_expected_response(self, challenge: str, worker_id: str) -> str:
        """Compute expected response using the worker's pre-shared secret.

        Uses the same algorithm as compute_worker_response so that
        the worker's response matches the expected response.
        """
        worker_secret = self._get_worker_secret(worker_id)
        return hmac.new(
            worker_secret.encode(),
            challenge.encode(),
            hashlib.sha256,
        ).hexdigest()

    def _get_worker_secret(self, worker_id: str) -> str:
        """Get the pre-shared secret for a worker.

        In production, look up from a secure store.
        For now, derive from master secret for deterministic testing.
        """
        return hashlib.sha256(f"{worker_id}:{self._master_secret}".encode()).hexdigest()[:32]

    def _log_verification(self, worker_id: str, success: bool, reason: str) -> None:
        self._verification_log.append({
            "worker_id": worker_id, "success": success,
            "reason": reason, "timestamp": time.time(),
        })

    def verification_log(self, limit: int = 100) -> List[Dict[str, Any]]:
        return self._verification_log[-limit:]

    def stats(self) -> Dict[str, Any]:
        return {
            "verified_workers": sum(
                1 for v in self._trust_overrides.values()
                if v == TrustLevel.TRUSTED
            ),
            "blacklisted": len(self._blacklist),
            "pending_challenges": len(self._challenges),
            "total_attempts": len(self._verification_log),
        }
