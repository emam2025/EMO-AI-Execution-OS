import uuid
import bcrypt
from fastapi import APIRouter, HTTPException, status, Request
from pydantic import BaseModel
from fastapi.responses import JSONResponse

from core.db import db
from middleware.auth import create_token, decode_token

router = APIRouter(prefix="/api/auth", tags=["auth"])


class SignupRequest(BaseModel):
    username: str
    password: str


class LoginRequest(BaseModel):
    username: str
    password: str


def hash_password(password: str) -> str:
    """Hash a password using bcrypt.

    Args:
        password: Plain text password.

    Returns:
        str: bcrypt hashed password string.
    """
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed: str) -> bool:
    """Verify a password against its bcrypt hash.

    Args:
        password: Plain text password.
        hashed: bcrypt hashed password string.

    Returns:
        bool: True if the password matches.
    """
    return bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


@router.post("/signup")
async def signup(req: SignupRequest):
    """Create a new user account.

    Args:
        req: SignupRequest with username and password.

    Returns:
        JSONResponse with user info.

    Raises:
        409: Username already exists.
        422: Validation error.
    """
    # Validate input
    if len(req.username) < 3:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Username must be at least 3 characters",
        )
    if len(req.password) < 8:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Password must be at least 8 characters",
        )

    # Check if user exists
    existing = await db.get_user(req.username)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Username already exists",
        )

    # Create user
    user_id = str(uuid.uuid4())
    password_hash = hash_password(req.password)
    await db.create_user(user_id, req.username, password_hash)

    # Log the action
    await db.log_action("signup", user_id=user_id, details=f"User {req.username} created")

    return JSONResponse({
        "id": user_id,
        "username": req.username,
        "message": "Account created successfully",
    })


@router.post("/login")
async def login(req: LoginRequest):
    """Authenticate a user and return a JWT token.

    Args:
        req: LoginRequest with username and password.

    Returns:
        JSONResponse with access_token.

    Raises:
        401: Invalid credentials.
    """
    user = await db.get_user(req.username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not verify_password(req.password, user["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    # Create token
    token = create_token(user["id"], user["username"])

    # Log the action
    await db.log_action("login", user_id=user["id"])

    return JSONResponse({
        "access_token": token,
        "token_type": "bearer",
        "expires_in": 86400,  # 24 hours
        "username": user["username"],
    })


@router.get("/verify")
async def verify_token(request: Request):
    """Verify a JWT token and return user info.

    Returns:
        JSONResponse with user info if token is valid.

    Raises:
        401: Invalid or expired token.
    """
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="No token provided",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = auth_header.split(" ", 1)[1]
    try:
        payload = decode_token(token)
        return JSONResponse({
            "valid": True,
            "user_id": payload["sub"],
            "username": payload["username"],
        })
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )
