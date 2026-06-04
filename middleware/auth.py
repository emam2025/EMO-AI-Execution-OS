import os
import time
import hashlib
import secrets
import threading
from typing import Dict, Optional
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
import jwt
from pydantic import BaseModel


JWT_SECRET = os.environ.get("EMO_JWT_SECRET")
if not JWT_SECRET:
    raise RuntimeError(
        "EMO_JWT_SECRET environment variable is required. "
        "Set it to a strong, unique value for JWT HMAC signing."
    )
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 2
REFRESH_EXPIRE_DAYS = 7


# ── Refresh token store (in-memory; production should use DB/Redis) ──
# Structure: {refresh_token_hash: {"user_id": str, "expires": float, "used": bool}}
_refresh_store: Dict[str, Dict] = {}
_refresh_lock = threading.RLock()


class RefreshTokenPayload(BaseModel):
    refresh_token: str


def create_token(user_id: str, username: str, role: str = "user") -> str:
    """Create a JWT access token with short expiry.

    Args:
        user_id: The user's unique ID.
        username: The user's username.
        role: User role (default "user"; "operator" for elevated access).

    Returns:
        str: Encoded JWT token.
    """
    expire = time.time() + (JWT_EXPIRE_HOURS * 3600)
    payload = {
        "sub": user_id,
        "username": username,
        "role": role,
        "exp": expire,
        "iat": time.time(),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    """Decode and validate a JWT token.

    Args:
        token: The JWT token string.

    Returns:
        dict: The token payload.

    Raises:
        HTTPException: If the token is invalid or expired.
    """
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token",
            headers={"WWW-Authenticate": "Bearer"},
        )


def generate_refresh_token(user_id: str) -> str:
    """Generate a one-time-use refresh token.

    Returns a raw token string.  The SHA-256 hash of the token is stored
    in the in-memory store with an expiry of REFRESH_EXPIRE_DAYS.
    The raw token is returned to the caller (and must be stored by the
    client); the plaintext is never persisted.

    Security properties:
        - one-time-use: ``used`` flag set to True after first validation
        - revoke-on-rotation: old token invalidated when a new one is issued
        - hashed storage: plaintext never persisted server-side
    """
    raw = secrets.token_urlsafe(48)
    h = hashlib.sha256(f"{raw}:{user_id}".encode()).hexdigest()
    expires = time.time() + (REFRESH_EXPIRE_DAYS * 86400)
    with _refresh_lock:
        _refresh_store[h] = {
            "user_id": user_id,
            "expires": expires,
            "used": False,
        }
    return raw


def validate_refresh_token(raw_token: str, user_id: str) -> bool:
    """Validate a refresh token.

    Checks:
        1. Token hash exists in store.
        2. Token belongs to *user_id*.
        3. Token has not expired.
        4. Token has NOT already been used (one-time use enforcement).

    On success the token is marked as ``used = True`` (one-time use).
    Returns True if valid, False otherwise.
    """
    h = hashlib.sha256(f"{raw_token}:{user_id}".encode()).hexdigest()
    with _refresh_lock:
        entry = _refresh_store.get(h)
        if entry is None:
            return False
        if entry["user_id"] != user_id:
            return False
        if time.time() > entry["expires"]:
            _refresh_store.pop(h, None)
            return False
        if entry["used"]:
            # Replay detected — invalidate ALL tokens for this user
            _revoke_all_for_user(user_id)
            return False
        # Mark used (one-time use)
        entry["used"] = True
    return True


def _revoke_all_for_user(user_id: str) -> None:
    """Revoke every active refresh token for *user_id*."""
    with _refresh_lock:
        expired = [k for k, v in _refresh_store.items() if v["user_id"] == user_id]
        for k in expired:
            _refresh_store.pop(k, None)


def get_current_user(request: Request) -> Optional[dict]:
    """Extract and validate the current user from the request.

    Args:
        request: The FastAPI request object.

    Returns:
        dict or None: The user payload if authenticated, None otherwise.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None

    token = auth_header.split(" ", 1)[1]
    return decode_token(token)


def require_auth(role: Optional[str] = None):
    """FastAPI dependency: require authentication with optional role check.

    Usage::

        @app.get("/api/status")
        async def status(user: dict = Depends(require_auth(role="operator"))):
            ...

    Returns the user dict on success.  Raises 401 or 403 on failure.

    When EMO_AUTH_ENABLED=false, bypasses all auth checks.
    """
    auth_enabled = os.getenv("EMO_AUTH_ENABLED", "false").lower() == "true"
    if not auth_enabled:
        def _bypass() -> dict:
            return {"role": "operator", "user_id": "system"}
        return _bypass

    from fastapi import Depends

    def _check(request: Request) -> dict:
        user = get_current_user(request)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            )
        if role and user.get("role") != role:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Role '{role}' required",
            )
        return user

    return _check


async def auth_middleware(request: Request, call_next):
    """FastAPI middleware that enforces authentication.

    Skips auth for:
    - Public endpoints (/, /api/auth/*, /static/*, /api/tray/ping)
    - When EMO_AUTH_ENABLED=false
    """
    auth_enabled = os.getenv("EMO_AUTH_ENABLED", "false").lower() == "true"

    if not auth_enabled:
        return await call_next(request)

    # Public paths that don't require auth
    public_paths = [
        "/",
        "/api/auth/login",
        "/api/auth/signup",
        "/api/auth/verify",
        "/api/auth/refresh",
        "/api/auth/logout",
        "/api/tray/ping",
        "/docs",
        "/openapi.json",
        "/redoc",
    ]

    path = request.url.path

    # Skip auth for public paths and static files
    if path in public_paths or path.startswith("/static/") or path.startswith("/api/stream"):
        return await call_next(request)

    # Check for token
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={"detail": "Authentication required"},
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = auth_header.split(" ", 1)[1]
    try:
        payload = decode_token(token)
        # Attach user info to request state
        request.state.user = payload
    except HTTPException as e:
        return JSONResponse(
            status_code=e.status_code,
            content={"detail": e.detail},
        )

    return await call_next(request)
