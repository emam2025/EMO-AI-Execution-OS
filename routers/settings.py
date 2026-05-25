import json
import os
from pathlib import Path
from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from brain import Brain

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
        if not k.endswith("_key") and k not in ("auth_password_hash", "telegram_token")
    }
    safe_settings["auth_enabled"] = os.getenv("EMO_AUTH_ENABLED", "false").lower() == "true"
    return JSONResponse(safe_settings)


@router.post("")
async def update_setting(req: SettingsUpdate):
    """Update a single setting."""
    settings = load_settings()
    settings[req.key] = req.value
    save_settings(settings)
    # Reload agents if system_instructions, provider, or model changed
    if req.key in ("system_instructions", "provider", "model"):
        try:
            from core.state import state
            state.reload_agents()
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
