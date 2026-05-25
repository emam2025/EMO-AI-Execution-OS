"""Tests for Phase E4 — WorkerVerifier (Unverified Workers).

Challenge-response protocol, trust upgrades, blacklisting.
"""

import hashlib
import time

import pytest

from core.security.worker_verifier import WorkerVerifier, VerificationResult
from core.security.capabilities import TrustLevel


def _worker_secret(worker_id: str, master_secret: str) -> str:
    """Derive a worker's pre-shared secret the same way the verifier does."""
    return hashlib.sha256(f"{worker_id}:{master_secret}".encode()).hexdigest()[:32]


class TestWorkerVerifier:
    def test_issue_challenge(self):
        verifier = WorkerVerifier()
        challenge = verifier.issue_challenge("worker_1")
        assert len(challenge) == 64  # sha256 hex

    def test_successful_verification(self):
        verifier = WorkerVerifier(master_secret="test-secret")
        wid = "worker_1"
        challenge = verifier.issue_challenge(wid)
        secret = _worker_secret(wid, "test-secret")
        response = verifier.compute_worker_response(challenge, secret)
        result = verifier.verify_response(wid, challenge, response)
        assert result.success is True
        assert result.trust_level == TrustLevel.TRUSTED

    def test_failed_verification_wrong_secret(self):
        verifier = WorkerVerifier(master_secret="correct-secret")
        wid = "worker_1"
        challenge = verifier.issue_challenge(wid)
        # Worker signs with a wrong secret (not derived from master)
        response = verifier.compute_worker_response(challenge, "this-is-a-wrong-secret-key-1234")
        result = verifier.verify_response(wid, challenge, response)
        assert result.success is False
        assert result.trust_level == TrustLevel.UNVERIFIED

    def test_failed_verification_unknown_challenge(self):
        verifier = WorkerVerifier()
        result = verifier.verify_response("worker_1", "fake-challenge", "fake-response")
        assert result.success is False

    def test_expired_challenge(self):
        verifier = WorkerVerifier(master_secret="test")
        wid = "worker_1"
        challenge = verifier.issue_challenge(wid, ttl=0.01)
        secret = _worker_secret(wid, "test")
        time.sleep(0.02)
        response = verifier.compute_worker_response(challenge, secret)
        result = verifier.verify_response(wid, challenge, response)
        assert result.success is False
        assert "expired" in result.reason.lower()

    def test_wrong_worker_id(self):
        verifier = WorkerVerifier(master_secret="test")
        challenge = verifier.issue_challenge("worker_a")
        secret = _worker_secret("worker_a", "test")
        response = verifier.compute_worker_response(challenge, secret)
        result = verifier.verify_response("worker_b", challenge, response)
        assert result.success is False

    def test_blacklist_after_failed(self):
        verifier = WorkerVerifier(master_secret="test")
        wid = "worker_1"
        challenge = verifier.issue_challenge(wid)
        response = verifier.compute_worker_response(challenge, "wrong-secret-1234567890")
        verifier.verify_response(wid, challenge, response)
        assert wid in verifier._blacklist

    def test_blacklist_blocks_verification(self):
        verifier = WorkerVerifier(master_secret="test")
        wid = "worker_1"
        verifier.blacklist(wid, "Manual blacklist")
        challenge = verifier.issue_challenge(wid)
        secret = _worker_secret(wid, "test")
        response = verifier.compute_worker_response(challenge, secret)
        result = verifier.verify_response(wid, challenge, response)
        assert result.success is False
        assert "blacklisted" in result.reason

    def test_unblacklist(self):
        verifier = WorkerVerifier()
        verifier.blacklist("worker_1")
        assert verifier.unblacklist("worker_1") is True
        assert "worker_1" not in verifier._blacklist
        assert verifier.unblacklist("nobody") is False

    def test_get_trust_level_default(self):
        verifier = WorkerVerifier()
        assert verifier.get_trust_level("unknown") == TrustLevel.UNVERIFIED

    def test_get_trust_level_after_verification(self):
        verifier = WorkerVerifier(master_secret="test")
        wid = "worker_1"
        challenge = verifier.issue_challenge(wid)
        secret = _worker_secret(wid, "test")
        response = verifier.compute_worker_response(challenge, secret)
        verifier.verify_response(wid, challenge, response)
        assert verifier.get_trust_level(wid) == TrustLevel.TRUSTED

    def test_get_trust_level_blacklisted(self):
        verifier = WorkerVerifier()
        verifier.blacklist("worker_1")
        assert verifier.get_trust_level("worker_1") == TrustLevel.UNVERIFIED

    def test_set_trust_override(self):
        verifier = WorkerVerifier()
        verifier.set_trust_override("worker_1", TrustLevel.TRUSTED)
        assert verifier.is_verified("worker_1") is True

    def test_clear_trust(self):
        verifier = WorkerVerifier()
        verifier.set_trust_override("worker_1", TrustLevel.TRUSTED)
        verifier.clear_trust("worker_1")
        assert verifier.is_verified("worker_1") is False

    def test_verification_log(self):
        verifier = WorkerVerifier(master_secret="test")
        wid = "worker_1"
        challenge = verifier.issue_challenge(wid)
        secret = _worker_secret(wid, "test")
        response = verifier.compute_worker_response(challenge, secret)
        verifier.verify_response(wid, challenge, response)

        # Failed attempt
        c2 = verifier.issue_challenge("worker_2")
        r2 = verifier.compute_worker_response(c2, "wrong-secret-1234567890")
        verifier.verify_response("worker_2", c2, r2)

        log = verifier.verification_log()
        assert len(log) == 2
        assert log[0]["success"] is True
        assert log[1]["success"] is False

    def test_stats(self):
        verifier = WorkerVerifier(master_secret="test")
        wid = "worker_1"
        challenge = verifier.issue_challenge(wid)
        secret = _worker_secret(wid, "test")
        response = verifier.compute_worker_response(challenge, secret)
        verifier.verify_response(wid, challenge, response)
        verifier.blacklist("worker_bad")

        stats = verifier.stats()
        assert stats["verified_workers"] == 1
        assert stats["blacklisted"] == 1
