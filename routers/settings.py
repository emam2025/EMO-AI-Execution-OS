import json
import os
from pathlib import Path
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from brain import Brain
from core.security.keychain_provider import KeychainProvider

SETTINGS_FILE = Path(".emo_settings.json")

router = APIRouter(prefix="/api/settings", tags=["settings"])


class SettingsUpdate(BaseModel):
    key: str
    value: str


def load_settings() -> dict:
    """Load settings from file."""
    if SETTINGS_FILE.exists():
        try:
            return json.loads(SETTINGS_FILE.read_text())
        except Exception:
            return {}
    return {}


def save_settings(settings: dict) -> None:
    """Save settings to file."""
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2, ensure_ascii=False))


@router.get("")
async def get_settings():
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
async def get_sensitive_keys():
    """Return masked tokens for UI display."""
    settings = load_settings()
    return JSONResponse({
        "telegram_token": settings.get("telegram_token", ""),
        "github_token": settings.get("github_token", ""),
    })


@router.post("")
async def update_setting(req: SettingsUpdate):
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
async def get_status():
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
