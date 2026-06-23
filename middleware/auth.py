import os
import time
import hashlib
import secrets
import threading
import logging
from typing import Dict, Optional
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
import jwt
from pydantic import BaseModel


logger = logging.getLogger("emo_ai.auth")


# ══════════════════════════════════════════════════════════════════════════════
# AUTH MODE — 3 states per DIRECTIVE-008
# ══════════════════════════════════════════════════════════════════════════════

class AuthMode:
    """Three authentication modes for gradual migration.

    OFF:       No auth checks (legacy default). All requests pass through.
    MIGRATION: Auth is optional. Requests WITHOUT auth get a migration bypass
               identity (SUPER_ADMIN). Requests WITH valid tokens get proper
               identity. This allows gradual endpoint protection.
    ENFORCED:  Auth is mandatory. All requests must have valid token.
    """
    OFF       = "off"
    MIGRATION = "migration"
    ENFORCED  = "enforced"


def get_auth_mode() -> str:
    """Get current auth mode from environment.

    Priority: EMO_AUTH_MODE > EMO_AUTH_ENABLED (backward compat)

    EMO_AUTH_ENABLED=true  -> ENFORCED
    EMO_AUTH_ENABLED=false + EMO_AUTH_MODE not set -> OFF
    EMO_AUTH_MODE=migration -> MIGRATION
    EMO_AUTH_MODE=enforced  -> ENFORCED
    EMO_AUTH_MODE=off       -> OFF
    """
    mode = os.getenv("EMO_AUTH_MODE", "").lower()
    if mode in (AuthMode.OFF, AuthMode.MIGRATION, AuthMode.ENFORCED):
        return mode

    # Backward compat: EMO_AUTH_ENABLED=true means ENFORCED
    if os.getenv("EMO_AUTH_ENABLED", "false").lower() == "true":
        return AuthMode.ENFORCED

    return AuthMode.OFF


# ══════════════════════════════════════════════════════════════════════════════
# JWT CONFIG
# ══════════════════════════════════════════════════════════════════════════════

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
_refresh_store: Dict[str, Dict] = {}
_refresh_lock = threading.RLock()


class RefreshTokenPayload(BaseModel):
    refresh_token: str


def create_token(user_id: str, username: str, role: str = "user") -> str:
    """Create a JWT access token with short expiry."""
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
    """Decode and validate a JWT token."""
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
    """Generate a one-time-use refresh token."""
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
    """Validate a refresh token."""
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
            _revoke_all_for_user(user_id)
            return False
        entry["used"] = True
    return True


def _revoke_all_for_user(user_id: str) -> None:
    """Revoke every active refresh token for *user_id*."""
    with _refresh_lock:
        expired = [k for k, v in _refresh_store.items() if v["user_id"] == user_id]
        for k in expired:
            _refresh_store.pop(k, None)


# ══════════════════════════════════════════════════════════════════════════════
# USER EXTRACTION
# ══════════════════════════════════════════════════════════════════════════════

def get_current_user(request: Request) -> Optional[dict]:
    """Extract and validate the current user from the request."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    token = auth_header.split(" ", 1)[1]
    return decode_token(token)


def get_identity(request: Request):
    """Get the Identity object from request state (set by middleware)."""
    return getattr(request.state, "identity", None)


# ══════════════════════════════════════════════════════════════════════════════
# require_auth — FastAPI dependency (updated for AUTH_MODE + Identity)
# ══════════════════════════════════════════════════════════════════════════════

def require_auth(role: Optional[str] = None):
    """FastAPI dependency: require authentication with optional role check.

    Behavior depends on AUTH_MODE:
    - OFF:       bypass (returns migration identity)
    - MIGRATION: bypass but log (returns migration identity)
    - ENFORCED:  require valid JWT token
    """
    auth_mode = get_auth_mode()

    if auth_mode == AuthMode.OFF:
        logger.critical("AUTH MODE IS 'OFF' — ALL REQUESTS ARE SUPER_ADMIN. Set EMO_AUTH_MODE=enforced for production.")
        def _bypass() -> dict:
            return {"role": "super_admin", "user_id": "system", "source": "auth_off"}
        return _bypass

    if auth_mode == AuthMode.MIGRATION:
        logger.critical("AUTH MODE IS 'MIGRATION' — ALL REQUESTS WITHOUT TOKEN ARE SUPER_ADMIN. Set EMO_AUTH_MODE=enforced for production.")
        def _migration_bypass() -> dict:
            logger.debug("AUTH_MIGRATION: bypass for role=%s", role)
            return {"role": "super_admin", "user_id": "migration", "source": "migration"}
        return _migration_bypass

    # ENFORCED mode
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
        user["source"] = "jwt"
        return user

    return _check


def require_permission(resource: str, action: str, scope: str = "own"):
    """FastAPI dependency: require a specific RBAC permission.

    Usage::

        @app.post("/api/tools")
        async def create_tool(user = Depends(require_permission("tool", "create", "org"))):
            ...

    Builds Identity from JWT and checks RBAC permission.
    """
    auth_mode = get_auth_mode()

    if auth_mode in (AuthMode.OFF, AuthMode.MIGRATION):
        def _bypass():
            return True
        return _bypass

    from fastapi import Depends
    from core.security.rbac import Resource, Action, Scope, get_rbac
    from core.security.identity import get_identity_builder

    def _check(request: Request) -> bool:
        user = get_current_user(request)
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authentication required",
            )
        # Build Identity from JWT
        builder = get_identity_builder()
        identity = builder.from_jwt(user, ip_address=request.client.host if request.client else "")
        request.state.identity = identity
        # Check RBAC
        rbac = get_rbac()
        decision = rbac.check(identity.role, Resource(resource), Action(action), Scope(scope))
        if not decision.allowed:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Permission denied: {resource}:{action}:{scope} (role={identity.role.value})",
            )
        return True

    return _check


# ══════════════════════════════════════════════════════════════════════════════
# AUTH MIDDLEWARE (updated for AUTH_MODE)
# ══════════════════════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════════════════════
# RATE LIMITER
# ══════════════════════════════════════════════════════════════════════════════

try:
    from core.rate_limiter import RateLimiter
    _rate_limiter = RateLimiter(
        max_requests=int(os.getenv("EMO_RATE_LIMIT_MAX", "100")),
        window_seconds=int(os.getenv("EMO_RATE_LIMIT_WINDOW", "60")),
    )
except ImportError:
    _rate_limiter = None


async def auth_middleware(request: Request, call_next):
    """FastAPI middleware that enforces authentication based on AUTH_MODE.

    OFF:       Skip all auth checks.
    MIGRATION: Skip auth but attach migration identity to request state.
    ENFORCED:  Validate JWT token on all non-public paths.
    """
    auth_mode = get_auth_mode()

    # Public paths that never require auth
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

    # Rate limit by client IP (applies to ALL paths including public)
    if _rate_limiter:
        client_ip = request.client.host if request.client else "unknown"
        allowed, count, limit = _rate_limiter.check(client_ip)
        if not allowed:
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"detail": f"Rate limit exceeded ({count}/{limit})"},
                headers={"Retry-After": str(_rate_limiter.window_seconds)},
            )

    # Skip auth for public paths and static files
    if path in public_paths or path.startswith("/static/") or path.startswith("/api/stream"):
        return await call_next(request)

    # OFF mode: no auth
    if auth_mode == AuthMode.OFF:
        return await call_next(request)

    # MIGRATION mode: attach bypass identity, let request through
    if auth_mode == AuthMode.MIGRATION:
        from core.security.identity import get_identity_builder
        builder = get_identity_builder()
        identity = builder.migration_bypass()
        request.state.user = {
            "role": "super_admin",
            "user_id": "migration",
            "source": "migration",
        }
        request.state.identity = identity
        request.state.identity_source = "migration"
        return await call_next(request)

    # ENFORCED mode: validate JWT
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
        payload["source"] = "jwt"
        request.state.user = payload
        request.state.identity_source = "jwt"
        # Build Identity from JWT payload
        from core.security.identity import get_identity_builder
        builder = get_identity_builder()
        identity = builder.from_jwt(payload, ip_address=request.client.host if request.client else "")
        request.state.identity = identity
    except HTTPException as e:
        return JSONResponse(
            status_code=e.status_code,
            content={"detail": e.detail},
        )

    # Rate limit by user_id (higher quota for authenticated users)
    if _rate_limiter and hasattr(request.state, "user") and request.state.user:
        uid = request.state.user.get("user_id")
        if uid:
            allowed, count, limit = _rate_limiter.check(f"user:{uid}")
            if not allowed:
                return JSONResponse(
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    content={"detail": f"User rate limit exceeded ({count}/{limit})"},
                    headers={"Retry-After": str(_rate_limiter.window_seconds)},
                )

    return await call_next(request)
