import functools
import json
import os
import time
from pathlib import Path
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from brain import Brain
from core.security.keychain_provider import KeychainProvider
from middleware.auth import require_auth

SETTINGS_FILE = Path(".emo_settings.json")
_SETTINGS_CACHE_TTL = 2.0  # seconds
_last_settings_load: float = 0.0
_cached_settings: dict = {}

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SettingsUpdate(BaseModel):
    key: str
    value: str


def load_settings() -> dict:
    """Load settings from file with in-memory caching (2s TTL)."""
    global _last_settings_load, _cached_settings
    now = time.time()
    if now - _last_settings_load < _SETTINGS_CACHE_TTL and _cached_settings:
        return _cached_settings
    if SETTINGS_FILE.exists():
        try:
            _cached_settings = json.loads(SETTINGS_FILE.read_text())
            _last_settings_load = now
            return _cached_settings
        except Exception:
            return {}
    return {}


def save_settings(settings: dict) -> None:
    """Save settings to file and invalidate cache."""
    global _last_settings_load
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2, ensure_ascii=False))
    _last_settings_load = 0.0  # invalidate cache


@router.get("")
async def get_settings(user: dict = Depends(require_auth())):
    """Get current settings (without sensitive keys)."""
    settings = load_settings()
    # Don't return sensitive keys
    safe_settings = {
        k: v for k, v in settings.items()
        if not k.endswith("_key") and k not in ("auth_password_hash", "telegram_token", "github_token")
    }
    safe_settings["auth_enabled"] = os.getenv("EMO_AUTH_ENABLED", "false").lower() == "true"
    return JSONResponse(safe_settings)


@router.get("/keys")
async def get_sensitive_keys(user: dict = Depends(require_auth())):
    """Return masked tokens for UI display."""
    settings = load_settings()
    return JSONResponse({
        "telegram_token": settings.get("telegram_token", ""),
        "github_token": settings.get("github_token", ""),
    })


@router.post("")
async def update_setting(req: SettingsUpdate, user: dict = Depends(require_auth())):
    """Update a single setting.
    
    If the key ends with '_key', it's an API key — store in system Keychain,
    not in the settings JSON file (which is git-visible).
    """
    if req.key.endswith("_key") and req.value:
        # Store in system Keychain
        provider_name = req.key.replace("_key", "")
        try:
            kp = KeychainProvider()
            kp.set(provider_name, req.value)
        except Exception:
            pass
        # Still save to file for backward compatibility
        settings = load_settings()
        settings[req.key] = req.value
        save_settings(settings)
        return JSONResponse({"status": "saved", "key": req.key, "stored_in": "keychain"})
    
    if req.key in ("telegram_token", "github_token") and req.value:
        settings = load_settings()
        settings[req.key] = req.value
        save_settings(settings)
        return JSONResponse({"status": "saved", "key": req.key})
    
    settings = load_settings()
    settings[req.key] = req.value
    save_settings(settings)
    # Reload agents if system_instructions, provider, or model changed
    if req.key in ("system_instructions", "provider", "model"):
        try:
            from core.runtime.data_providers import get_state
            get_state().reload_agents()
        except Exception:
            pass
    return JSONResponse({"status": "saved", "key": req.key})


@router.get("/status")
async def get_status(user: dict = Depends(require_auth())):
    """Get LLM connection status."""
    settings = load_settings()
    provider = settings.get("provider", os.getenv("LLM_PROVIDER", "openrouter"))
    model = settings.get("model", os.getenv("LLM_MODEL", ""))
    try:
        brain = Brain(provider=provider, model=model)
        connected, message = brain.test_connection()
        return JSONResponse({
            "connected": connected,
            "provider": provider,
            "model": model,
            "latency_ms": 0,
            "message": message,
        })
    except Exception as e:
        return JSONResponse({
            "connected": False,
            "provider": provider,
            "model": model,
            "message": str(e),
        })
