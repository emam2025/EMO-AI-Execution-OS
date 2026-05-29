"""HIGH-001A Task 3 — JWT Lifecycle Security Tests.

Tests:
  1. Access token expiry is ≤ 2 hours
  2. Refresh token generation returns a hash (different from raw)
  3. Refresh token is one-time-use (reuse invalidated)
  4. Refresh rotation: new token after /refresh invalidates old
  5. Logout revokes all tokens
  6. Theft simulation: replay of used refresh revokes ALL tokens
"""

import os
import sys
import time
import hashlib

import pytest

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ.setdefault("EMO_JWT_SECRET", "test-jwt-lifecycle-secret")


class TestJwtAccessToken:
    """Access token expiry and structure tests."""

    def test_access_token_expiry_2h(self):
        from middleware.auth import JWT_EXPIRE_HOURS
        assert JWT_EXPIRE_HOURS <= 2, (
            f"JWT expiry {JWT_EXPIRE_HOURS}h exceeds 2h limit"
        )

    def test_token_contains_role(self):
        from middleware.auth import create_token, decode_token
        token = create_token("user-1", "test_user", role="operator")
        payload = decode_token(token)
        assert payload["role"] == "operator"
        assert payload["sub"] == "user-1"

    def test_token_expires_correctly(self):
        from middleware.auth import create_token, decode_token
        from fastapi import HTTPException
        token = create_token("u1", "user1")
        # fast-forward expiry check by mocking time is impractical;
        # instead verify the exp claim is set and reasonable
        import jwt
        import time as ttime
        payload = jwt.decode(token, os.environ["EMO_JWT_SECRET"], algorithms=["HS256"], options={"verify_exp": False})
        expected_max = ttime.time() + 7200 + 60  # 2h + 1min tolerance
        assert payload["exp"] <= expected_max, "exp claim exceeds 2h window"
        assert payload["exp"] > ttime.time(), "exp claim is in the past"


class TestRefreshToken:
    """Refresh token lifecycle tests."""

    def test_generate_returns_raw_string(self):
        from middleware.auth import generate_refresh_token
        raw = generate_refresh_token("user-1")
        assert isinstance(raw, str)
        assert len(raw) > 40  # 48 bytes URL-safe base64

    def test_generated_token_not_stored_as_plaintext(self):
        from middleware.auth import generate_refresh_token, _refresh_store
        raw = generate_refresh_token("user-2")
        # The store should never contain the raw token
        store_contents = str(_refresh_store)
        assert raw not in store_contents, "Raw token leaked into store!"

    def test_one_time_use(self):
        from middleware.auth import (
            generate_refresh_token,
            validate_refresh_token,
        )
        raw = generate_refresh_token("user-3")
        # First use — should succeed
        assert validate_refresh_token(raw, "user-3"), "First use should succeed"
        # Second use — should fail (one-time use enforced)
        assert not validate_refresh_token(raw, "user-3"), "Second use should fail"

    def test_rotation_invalidates_old(self):
        """After rotating, the old refresh token should be invalid."""
        from middleware.auth import (
            generate_refresh_token,
            validate_refresh_token,
        )
        old_raw = generate_refresh_token("user-4")
        # Validate once (consumes it)
        assert validate_refresh_token(old_raw, "user-4")
        # Generate a new one (rotation)
        new_raw = generate_refresh_token("user-4")
        # The old one is already used — should fail
        assert not validate_refresh_token(old_raw, "user-4")

    def test_logout_revokes_all(self):
        from middleware.auth import (
            generate_refresh_token,
            validate_refresh_token,
            _revoke_all_for_user,
        )
        r1 = generate_refresh_token("user-5")
        r2 = generate_refresh_token("user-5")
        _revoke_all_for_user("user-5")
        assert not validate_refresh_token(r1, "user-5"), "Should be revoked"
        assert not validate_refresh_token(r2, "user-5"), "Should be revoked"

    def test_theft_simulation_replay_detected(self):
        """Replay of an already-used refresh token revokes ALL tokens."""
        from middleware.auth import (
            generate_refresh_token,
            validate_refresh_token,
            _refresh_store,
        )
        # Generate two tokens for the same user
        r1 = generate_refresh_token("user-6")
        r2 = generate_refresh_token("user-6")

        # Use r1 legitimately
        assert validate_refresh_token(r1, "user-6")

        # Attacker replays r1 (second use) — should fail AND revoke all
        assert not validate_refresh_token(r1, "user-6")

        # r2 should also be revoked now
        assert not validate_refresh_token(r2, "user-6"), (
            "Theft replay should revoke ALL tokens for that user"
        )
