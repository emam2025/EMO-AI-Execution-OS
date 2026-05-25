import os
import time
from typing import Optional
from fastapi import Request, HTTPException, status
from fastapi.responses import JSONResponse
import jwt

JWT_SECRET = os.getenv("EMO_JWT_SECRET", "jwt-secret-placeholder-rotated")
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 24


def create_token(user_id: str, username: str) -> str:
    """Create a JWT token for a user.

    Args:
        user_id: The user's unique ID.
        username: The user's username.

    Returns:
        str: Encoded JWT token.
    """
    expire = time.time() + (JWT_EXPIRE_HOURS * 3600)
    payload = {
        "sub": user_id,
        "username": username,
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
