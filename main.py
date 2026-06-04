import os
import uuid
import asyncio
import json
import traceback
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional
from dotenv import load_dotenv
from core.security.keychain_provider import KeychainProvider
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi import Depends
from starlette.middleware.base import BaseHTTPMiddleware

# Load environment variables
load_dotenv()

# Setup logging
from core.logging_config import setup_logging, get_logger, log_audit
setup_logging(level=os.getenv("EMO_LOG_LEVEL", "INFO"))
logger = get_logger("main")

from routers.chat import router as chat_router
from routers.stream import router as stream_router
from routers.auth import router as auth_router
from routers.tasks import router as tasks_router
from routers.conversations import router as conversations_router
from routers.settings import router as settings_router
from routers.history import router as history_router
from routers.project import router as project_router
from core.state import state
from core.tasks import cleanup_old_tasks_loop
from core.db import db
from middleware.auth import auth_middleware, require_auth
from brain import Brain

# Global Telegram bot instance
telegram_bot = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global telegram_bot

    # Initialize database
    await db.initialize()
    logger.info("Database initialized")

    # Initialize AI Code Intelligence Layer
    try:
        from core.ai_init import initialize_ai_layer
        ai_config = initialize_ai_layer()
        if ai_config:
            logger.info("AI Code Intelligence Layer initialized")
        else:
            logger.warning("Failed to initialize AI Code Intelligence Layer")
    except ImportError:
        logger.warning("AI Code Intelligence Layer not available")
    except Exception as e:
        logger.error(f"Error initializing AI Code Intelligence Layer: {e}")

    # Initialize AI component state for the AI API router
    try:
        from pathlib import Path as _Path
        from core.graph_query import GraphQuery as _GQ
        from core.graph_retrieval import GraphRetrievalEngine as _GRE
        from core.ai_agent import CodeIntelligenceAgent as _Agent
        from core.ai_context_engine import AIContextEngine as _Ctx
        from core.hybrid_retriever import HybridRetriever as _HR
        from core.metrics_store import MetricsStore as _Metrics
        from core.execution_memory import ExecutionMemory as _Mem
        from core.unified_runtime import UnifiedRuntime as _RT
        from core.feedback_intel import FeedbackIntelligence as _Feedback
        from core.replay import ReplayEngine as _Replay
        from routers.ai import ai_state as _ai_state

        _ai_index = str(_Path(".ai") / "index")
        _gq = _GQ(str(_Path(_ai_index) / "repository.db"))
        _gre = _GRE(_gq)
        _agent = _Agent(_gq, _gre)
        _ctx = _Ctx(_gq)
        _metrics = _Metrics(str(_Path(_ai_index) / "metrics.db"))
        _mem = _Mem(str(_Path(_ai_index) / "execution_memory.db"))

        # Execution feedback intelligence (was latent — now connected)
        _feedback = _Feedback(db_path=str(_Path(_ai_index) / "feedback.db"))

        # Semantic layer is optional
        _hybrid: Optional[Any] = None
        _ee: Optional[Any] = None
        _ss: Optional[Any] = None
        try:
            from core.embedding_engine import EmbeddingEngine as _EE
            from core.semantic_store import SemanticStore as _SS
            from core.hybrid_retriever import WeightsAdvisor as _WA, RepoStats as _RS
            from core.query_replay import QueryReplay as _QR
            from core.adaptive_weights import AdaptiveWeightEngine as _AWE
            from core.feedback_loop import RankingFeedbackLoop as _Loop

            _ss_path = str(_Path(_ai_index) / "semantic.index")
            _qr_path = str(_Path(_ai_index) / "query_logs.db")
            _ee = _EE()
            _ss = _SS(_ss_path)
            _qr = _QR(_qr_path)
            _loop = _Loop()
            _awe = _AWE(_loop, metrics_store=_metrics)
            _wa = _WA(_RS(size=100, total_symbols=10, languages=["python"]))
            _hybrid = _HR(_gre, _ss, _ee, weights_advisor=_wa,
                          query_replay=_qr, adaptive_engine=_awe,
                          metrics_store=_metrics)
        except Exception as e:
            logger.warning("Semantic layer not available: %s", e)

        from core.execution_cache import ExecutionCache as _Cache

        _exec_cache = _Cache(
            db_path=str(_Path(_ai_index) / "execution_cache.db"),
            max_entries=2000, default_ttl_seconds=3600,
        )

        _rt = _RT(_gq, _gre, _agent, _ctx, hybrid=_hybrid, metrics=_metrics, memory=_mem,
                  cache=_exec_cache, worker_pool_size=4, feedback_intel=_feedback)
        _replay = _Replay(_mem)

        # Store in shared state
        _ai_state.initialized = True
        _ai_state.gq = _gq
        _ai_state.gre = _gre
        _ai_state.agent = _agent
        _ai_state.ctx = _ctx
        _ai_state.hybrid = _hybrid
        _ai_state.runtime = _rt
        _ai_state.memory = _mem
        _ai_state.metrics = _metrics
        _ai_state.replay = _replay
        _ai_state.cache = _exec_cache
        _ai_state.service_registry = None

        logger.info("AI API Router: all components initialized")
    except Exception as e:
        logger.error("AI API Router initialization failed: %s\n%s", e, traceback.format_exc())
        from routers.ai import ai_state as _ai_state
        _ai_state.initialized = False
        _ai_state.error = str(e)

    # Create default admin user if auth is enabled and no users exist
    auth_enabled = os.getenv("EMO_AUTH_ENABLED", "false").lower() == "true"
    if auth_enabled:
        existing_users = await db.get_users_count()
        if existing_users == 0:
            import bcrypt
            admin_id = str(uuid.uuid4())
            admin_username = os.getenv("EMO_AUTH_USERNAME", "admin")
            admin_password = os.getenv("EMO_AUTH_PASSWORD")
            if not admin_password:
                raise RuntimeError(
                    "EMO_AUTH_PASSWORD environment variable is required when auth is enabled"
                )
            password_hash = bcrypt.hashpw(
                admin_password.encode("utf-8"), bcrypt.gensalt()
            ).decode("utf-8")
            await db.create_user(admin_id, admin_username, password_hash)
            logger.info(f"Default admin created: {admin_username}")

    # Initialize Telegram bot if enabled
    telegram_enabled = os.getenv("TELEGRAM_ENABLED", "false").lower() == "true"
    telegram_token = os.getenv("TELEGRAM_TOKEN", "")
    if telegram_enabled and telegram_token:
        try:
            from telegram_bot import TelegramBot
            brain = Brain()
            telegram_bot = TelegramBot(token=telegram_token, brain=brain)
            if telegram_bot.is_available:
                telegram_bot.start()
                logger.info("Telegram bot started successfully")
            else:
                logger.warning("python-telegram-bot not installed")
        except Exception as e:
            logger.error(f"Failed to start Telegram bot: {e}")

    # Start background cleanup
    cleanup_task = asyncio.create_task(cleanup_old_tasks_loop(state.task_manager))

    yield

    # Cleanup
    if telegram_bot:
        telegram_bot.stop()
    cleanup_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass


# ── Security Headers Middleware ────────────────────────────────
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
            "font-src 'self'; connect-src 'self'"
        )
        response.headers["Strict-Transport-Security"] = (
            "max-age=31536000; includeSubDomains"
        )
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response


app = FastAPI(
    title="Emo AI Orchestrator",
    version="4.2.0",
    description=(
        "Multi-Agent Intelligence Orchestration System\n\n"
        "EMO AI orchestrate multiple AI agents (Planner, Coder, Writer, Researcher) "
        "with support for 4 LLM providers (OpenRouter, Groq, Gemini, Ollama) and 30+ tools.\n\n"
        "**Features:**\n"
        "- Multi-agent AI orchestration\n"
        "- Real-time SSE streaming\n"
        "- 30+ integrated tools\n"
        "- Telegram bot integration\n"
        "- JWT authentication\n"
        "- SQLite database\n"
        "- Cross-platform system tray"
    ),
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
    contact={
        "name": "EMO AI Contributors",
        "url": "https://github.com/emo-ai/emo-ai",
    },
    license_info={
        "name": "MIT License",
        "url": "https://opensource.org/licenses/MIT",
    },
)

# Add security headers middleware (applied before auth)
app.add_middleware(SecurityHeadersMiddleware)

# Add auth middleware
app.middleware("http")(auth_middleware)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Templates
templates = Jinja2Templates(directory="templates")

# Include routers
app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(stream_router)
app.include_router(tasks_router)
app.include_router(conversations_router)
app.include_router(settings_router)
app.include_router(history_router)
app.include_router(project_router)

# AI Code Intelligence API
try:
    from routers.ai import router as ai_router
    app.include_router(ai_router)
    logger.info("AI API router registered")
except Exception as e:
    logger.error(f"Failed to register AI router: {e}")

# E2E Pipeline API
try:
    from routers.e2e import router as e2e_router
    app.include_router(e2e_router)
    logger.info("E2E pipeline router registered")
except Exception as e:
    logger.error(f"Failed to register E2E router: {e}")

# Observability Dashboard
try:
    from routers.observability import router as obs_router
    app.include_router(obs_router)
    logger.info("Observability dashboard router registered")
except Exception as e:
    logger.error(f"Failed to register observability router: {e}")


@app.get("/api/status")
async def api_status(user: dict = Depends(require_auth(role="operator"))):
    """Get server status.  Requires operator role."""
    from routers.settings import load_settings
    settings = load_settings()
    kp = KeychainProvider()
    current_provider = settings.get("provider", "openrouter")
    key = kp.get(current_provider)
    return JSONResponse({
        "name": "Emo AI Orchestrator",
        "version": "4.1.0",
        "status": "running",
        "provider": current_provider,
        "model": settings.get("model", ""),
        "connected": bool(key or os.getenv(f"{current_provider.upper()}_API_KEY")),
    })


@app.get("/")
async def root(request: Request):
    """Render the main web UI."""
    settings = {}
    settings_file = Path(".emo_settings.json")
    if settings_file.exists():
        try:
            settings = json.loads(settings_file.read_text())
        except Exception:
            pass

    lang = settings.get("lang", "ar")
    theme = settings.get("theme", "dark")
    is_rtl = "rtl" if lang == "ar" else "ltr"
    provider = settings.get("provider", "openrouter")
    model = settings.get("model", "")

    from i18n import t, T
    tr = lambda key: t(key, lang)

    # Build tr_json for the frontend
    tr_json = T.get(lang, T["en"])

    # Build tools_json
    tools_list = state.tools.to_list() if hasattr(state.tools, 'to_list') else []
    tools_json_str = json.dumps(tools_list, ensure_ascii=False)

    # Build providers_json
    kp = KeychainProvider()
    providers_json = {
        "openrouter": {"name": "OpenRouter", "api_key_env": "OPENROUTER_API_KEY", "in_keychain": kp.get("openrouter") is not None},
        "groq": {"name": "Groq", "api_key_env": "GROQ_API_KEY", "in_keychain": kp.get("groq") is not None},
        "gemini": {"name": "Gemini", "api_key_env": "GEMINI_API_KEY", "in_keychain": kp.get("gemini") is not None},
        "ollama": {"name": "Ollama (Local)", "api_key_env": "", "in_keychain": True},
    }
    providers_json_str = json.dumps(providers_json, ensure_ascii=False)
    settings_json_str = json.dumps(settings, ensure_ascii=False)
    tr_json_str = json.dumps(tr_json, ensure_ascii=False)

    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "lang": lang,
            "is_rtl": is_rtl,
            "theme": theme,
            "tr": type('Tr', (), {'__getitem__': lambda s, k: tr(k)})(),
            "proj_name": "Emo AI",
            "proj_dir": str(Path.cwd()),
            "cur_model": model,
            "provider_sel": provider,
            "tr_json": tr_json_str,
            "tools_json": tools_json_str,
            "settings_json": settings_json_str,
            "providers_json": providers_json_str,
            "selected_en": "selected" if lang == "en" else "",
            "selected_ar": "selected" if lang == "ar" else "",
            "placeholder_send": tr("send_placeholder"),
        }
    )


@app.get("/api/models/{provider}")
async def list_models(provider: str):
    """Fetch available models from a provider with pricing info."""
    default_models = {
        "openrouter": [
            {"id": "openai/gpt-4o", "name": "GPT-4o", "free": False},
            {"id": "openai/gpt-4o-mini", "name": "GPT-4o Mini", "free": False},
            {"id": "openai/gpt-4.1", "name": "GPT-4.1", "free": False},
            {"id": "openai/o3-mini", "name": "o3 Mini", "free": False},
            {"id": "anthropic/claude-sonnet-4", "name": "Claude Sonnet 4", "free": False},
            {"id": "anthropic/claude-haiku-4", "name": "Claude Haiku 4", "free": False},
            {"id": "google/gemini-2.0-flash-001", "name": "Gemini 2.0 Flash", "free": True},
            {"id": "google/gemini-2.5-flash-preview", "name": "Gemini 2.5 Flash", "free": True},
            {"id": "mistralai/mistral-small-3.1", "name": "Mistral Small 3.1", "free": False},
            {"id": "mistralai/mistral-large-2411", "name": "Mistral Large", "free": False},
            {"id": "meta-llama/llama-3.3-70b-instruct", "name": "Llama 3.3 70B", "free": True},
            {"id": "meta-llama/llama-3.1-8b-instruct", "name": "Llama 3.1 8B", "free": True},
            {"id": "deepseek/deepseek-r1", "name": "DeepSeek R1", "free": False},
            {"id": "deepseek/deepseek-chat", "name": "DeepSeek V3", "free": False},
            {"id": "qwen/qwq-32b", "name": "QwQ 32B", "free": False},
            {"id": "microsoft/phi-4", "name": "Phi-4", "free": True},
        ],
        "groq": [
            {"id": "llama-3.3-70b-versatile", "name": "Llama 3.3 70B", "free": True},
            {"id": "llama-3.1-8b-instant", "name": "Llama 3.1 8B", "free": True},
            {"id": "mixtral-8x7b-32768", "name": "Mixtral 8x7B", "free": True},
            {"id": "gemma2-9b-it", "name": "Gemma 2 9B", "free": True},
            {"id": "deepseek-r1-distill-llama-70b", "name": "DeepSeek R1 70B", "free": True},
        ],
        "gemini": [
            {"id": "gemini-2.0-flash", "name": "Gemini 2.0 Flash", "free": True},
            {"id": "gemini-2.5-flash-preview", "name": "Gemini 2.5 Flash", "free": True},
            {"id": "gemini-2.5-pro-preview", "name": "Gemini 2.5 Pro", "free": False},
            {"id": "gemini-1.5-flash", "name": "Gemini 1.5 Flash", "free": True},
            {"id": "gemini-1.5-pro", "name": "Gemini 1.5 Pro", "free": False},
        ],
        "ollama": [
            {"id": "llama3.2", "name": "Llama 3.2", "free": True},
            {"id": "llama3.1", "name": "Llama 3.1", "free": True},
            {"id": "mistral", "name": "Mistral", "free": True},
            {"id": "codellama", "name": "CodeLlama", "free": True},
            {"id": "gemma2", "name": "Gemma 2", "free": True},
            {"id": "deepseek-r1", "name": "DeepSeek R1", "free": True},
            {"id": "phi4", "name": "Phi-4", "free": True},
        ],
    }

    # Try fetching real models from OpenRouter API
    if provider == "openrouter":
        kp = KeychainProvider()
        key = kp.get("openrouter")
        if key:
            try:
                import httpx
                async with httpx.AsyncClient(timeout=10) as client:
                    r = await client.get(
                        "https://openrouter.ai/api/v1/models",
                        headers={"Authorization": f"Bearer {key}"}
                    )
                    if r.status_code == 200:
                        data = r.json()
                        models = []
                        for m in data.get("data", []):
                            pricing = m.get("pricing", {})
                            # Free if both prompt and completion cost < $0.00001
                            prompt_cost = float(pricing.get("prompt", 1))
                            compl_cost = float(pricing.get("completion", 1))
                            is_free = prompt_cost < 0.00001 and compl_cost < 0.00001
                            models.append({
                                "id": m["id"],
                                "name": m.get("name", m["id"]),
                                "free": is_free,
                            })
                        if models:
                            return {"models": models}
            except Exception:
                pass

    models = default_models.get(provider, [{"id": "unknown", "name": "Unknown", "free": False}])
    return {"models": models}


@app.get("/api/test-connection")
async def test_connection(provider: str = "openrouter"):
    """Test actual connection to a model provider."""
    kp = KeychainProvider()
    key = kp.get(provider)
    if not key and provider != "ollama":
        return {"connected": False, "error": f"No API key in Keychain for {provider}"}

    try:
        import time
        start = time.time()
        b = Brain(provider=provider)
        response = b.ask(user="Reply with the word OK", max_tokens=10)
        latency = int((time.time() - start) * 1000)
        is_ok = 'OK' in response.strip().upper()
        if is_ok:
            return {"connected": True, "latency": latency}
        else:
            return {"connected": True, "latency": latency, "note": f"Unexpected response: {response.strip()[:50]}"}
    except Exception as e:
        err = str(e)
        return {"connected": False, "error": err}


@app.get("/api/tray/ping")
async def tray_ping():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8080"))
    host = os.getenv("HOST", "0.0.0.0")
    uvicorn.run(app, host=host, port=port)

