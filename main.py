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
from routers.security import router as security_router
from routers.workflow import router as workflow_router
from routers.workspace import router as workspace_router
from core.state import state
from core.tasks import cleanup_old_tasks_loop
from core.db import db
from middleware.auth import auth_middleware, require_auth
from brain import Brain
from core.runtime.observability.exporters import PrometheusExporter, OpenTelemetryExporter

# Global Telegram bot instance
telegram_bot = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global telegram_bot

    async def _init_db():
        await db.initialize()
        logger.info("Database initialized")

    async def _seed_agents():
        try:
            await db.seed_default_agents()
            logger.info("Default agents seeded")
        except Exception as e:
            logger.warning(f"Agent seeding skipped: {e}")

    async def _seed_enterprise():
        try:
            await db.seed_default_enterprise()
            logger.info("Default enterprise seeded")
        except Exception as e:
            logger.warning(f"Enterprise seeding skipped: {e}")

    async def _init_gateway():
        try:
            from core.gateway.provider_gateway import ProviderGateway
            from core.gateway.models import ProviderType, ProviderPolicy, ProviderConfig, UsageQuota

            policies = {
                ProviderType.OPENAI: ProviderPolicy(provider=ProviderType.OPENAI, allowed_models=["gpt-4", "gpt-3.5-turbo"], max_requests_per_minute=60),
                ProviderType.ANTHROPIC: ProviderPolicy(provider=ProviderType.ANTHROPIC, allowed_models=["claude-3"], max_requests_per_minute=30),
                ProviderType.GEMINI: ProviderPolicy(provider=ProviderType.GEMINI, allowed_models=["gemini-pro"], max_requests_per_minute=60),
                ProviderType.LOCAL: ProviderPolicy(provider=ProviderType.LOCAL, allowed_models=["*"], max_requests_per_minute=9999),
            }
            configs = {
                ProviderType.OPENAI: ProviderConfig(provider=ProviderType.OPENAI, api_key_env="OPENAI_API_KEY", timeout_seconds=30),
                ProviderType.ANTHROPIC: ProviderConfig(provider=ProviderType.ANTHROPIC, api_key_env="ANTHROPIC_API_KEY", timeout_seconds=30),
                ProviderType.GEMINI: ProviderConfig(provider=ProviderType.GEMINI, api_key_env="GEMINI_API_KEY", timeout_seconds=30),
                ProviderType.LOCAL: ProviderConfig(provider=ProviderType.LOCAL, api_key_env="", base_url="http://localhost:11434", timeout_seconds=60),
            }
            quotas = {
                ProviderType.OPENAI: UsageQuota(provider=ProviderType.OPENAI, requests_limit=1000, tokens_limit=1000000),
                ProviderType.ANTHROPIC: UsageQuota(provider=ProviderType.ANTHROPIC, requests_limit=500, tokens_limit=500000),
                ProviderType.GEMINI: UsageQuota(provider=ProviderType.GEMINI, requests_limit=1000, tokens_limit=1000000),
                ProviderType.LOCAL: UsageQuota(provider=ProviderType.LOCAL, requests_limit=999999, tokens_limit=999999999),
            }

            gateway = ProviderGateway(policies=policies, configs=configs, quotas=quotas)
            app.state.provider_gateway = gateway
            logger.info("ProviderGateway initialized and activated")
        except Exception as e:
            logger.warning(f"ProviderGateway init skipped: {e}")
            app.state.provider_gateway = None

    async def _init_runtime():
        try:
            from core.runtime.bootstrap import EmoRuntime
            runtime = EmoRuntime()
            await runtime.initialize()
            app.state.runtime = runtime
            app.state.facade = runtime.facade
            logger.info("EmoRuntime initialized via CompositionRoot")
            return runtime
        except Exception as e:
            logger.error("EmoRuntime initialization failed: %s\n%s", e, traceback.format_exc())
            app.state.runtime = None
            app.state.facade = None
            return None

    async def _init_ai_state(runtime=None):
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
            _ctx = _Ctx(_gq)
            _gre = _GRE(_gq, ctx=_ctx)
            _agent = _Agent(_gq, _gre)
            _metrics = _Metrics(str(_Path(_ai_index) / "metrics.db"))
            _mem = _Mem(str(_Path(_ai_index) / "execution_memory.db"))

            try:
                _feedback = _Feedback(db_path=_Path(_ai_index) / "feedback.db")
            except Exception as ex:
                logger.warning(f"Feedback intelligence init skipped: {ex}")
                _feedback = None

            _hybrid: Optional[Any] = None
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

            try:
                _exec_cache = _Cache(
                    db_path=str(_Path(_ai_index) / "execution_cache.db"),
                    max_entries=2000, default_ttl_seconds=3600,
                )
            except Exception as cache_ex:
                logger.warning(f"Cache init failed: {cache_ex}")
                _exec_cache = None

            try:
                _rt = _RT(_gq, _gre, _agent, _ctx, hybrid=_hybrid, memory=_mem,
                          feedback_intel=_feedback)
            except Exception as rt_ex:
                logger.warning(f"UnifiedRuntime init failed: {rt_ex}")
                _rt = None
            try:
                _replay = _Replay(_mem)
            except Exception as replay_ex:
                logger.warning(f"Replay init failed: {replay_ex}")
                _replay = None

            _ai_state.initialized = True
            _ai_state.gq = _gq
            _ai_state.gre = _gre
            _ai_state.agent = _agent
            _ai_state.ctx = _ctx
            _ai_state.hybrid = _hybrid
            _ai_state.memory = _mem
            _ai_state.metrics = _metrics
            _ai_state.replay = _replay
            _ai_state.cache = _exec_cache
            _ai_state.service_registry = None
            if runtime is not None:
                _ai_state.facade = runtime.facade
            else:
                _ai_state.facade = None
            _ai_state.runtime = _rt or (runtime.unified_runtime if runtime else None)

            from core.runtime.facade import EmoRuntimeFacade as _Facade
            _ai_state.facade = _Facade(
                unified_runtime=_rt,
                execution_memory=_mem,
                metrics_store=_metrics,
                graph_query=_gq,
                graph_retrieval=_gre,
                hybrid_retriever=_hybrid,
                replayer=_replay,
                agent=_agent,
                context_engine=_ctx,
            )

            logger.info("AI API Router: all components initialized")
        except Exception as e:
            logger.error("AI API Router initialization failed: %s\n%s", e, traceback.format_exc())
            from routers.ai import ai_state as _ai_state
            _ai_state.initialized = False
            _ai_state.error = str(e)

    async def _init_admin():
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

    async def _init_audit_trail():
        audit_signing_key = os.getenv("EMO_AUDIT_SIGNING_KEY")
        if not audit_signing_key:
            logger.critical(
                "EMO_AUDIT_SIGNING_KEY not set — audit trail signatures will be FORGEABLE. "
                "Set EMO_AUDIT_SIGNING_KEY in production."
            )
            return
        from core.governance.audit_trail import AuditTrail
        audit_trail = AuditTrail(db=db, signing_key=audit_signing_key)
        try:
            count = await audit_trail.load_from_db()
            logger.info("Audit trail initialized (loaded %d records from DB)", count)
        except Exception:
            logger.info("Audit trail initialized with signing key")
        app.state.audit_trail = audit_trail

    async def _init_telegram():
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

    async def _init_ai_layer():
        try:
            from core.ai_init import initialize_ai_layer
            ai_config = await asyncio.to_thread(initialize_ai_layer)
            if ai_config:
                logger.info("AI Code Intelligence Layer initialized")
            else:
                logger.warning("Failed to initialize AI Code Intelligence Layer")
        except ImportError:
            logger.warning("AI Code Intelligence Layer not available")
        except Exception as e:
            logger.error(f"Error initializing AI Code Intelligence Layer: {e}")

    # Run independent initialization steps in parallel
    await asyncio.gather(
        _init_db(),
        _init_gateway(),
        _init_ai_layer(),
        _init_audit_trail(),
        return_exceptions=True,
    )

    # Sequential steps that depend on db
    await asyncio.gather(
        _seed_agents(),
        _seed_enterprise(),
        return_exceptions=True,
    )

    # Initialize EmoRuntime (F2/F3/I1/I2/I3 subsystems)
    emo_runtime = await _init_runtime()

    # ── Prometheus exporter ───────────────────────────────────────
    prometheus = PrometheusExporter()
    app.state.prometheus_exporter = prometheus
    logger.info("Prometheus metrics exporter initialized at /metrics")

    # ── OpenTelemetry exporter (optional) ─────────────────────────
    otel_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    if otel_endpoint:
        otel_service = os.getenv("OTEL_SERVICE_NAME", "emo-ai")
        otel = OpenTelemetryExporter(
            endpoint=otel_endpoint, service_name=otel_service
        )
        app.state.otel_exporter = otel
        logger.info("OpenTelemetry traces exporting to %s", otel_endpoint)
    else:
        app.state.otel_exporter = None
        logger.info(
            "OpenTelemetry not configured "
            "(set OTEL_EXPORTER_OTLP_ENDPOINT to enable)"
        )

    # AI state and admin depend on DB + gateway
    await asyncio.gather(
        _init_ai_state(runtime=emo_runtime),
        _init_admin(),
        return_exceptions=True,
    )

    # Telegram is fully independent
    await _init_telegram()

    # Start background cleanup
    cleanup_task = asyncio.create_task(cleanup_old_tasks_loop(state.task_manager))

    try:
        yield
    finally:
        # Cleanup
        try:
            if telegram_bot:
                telegram_bot.stop()
        except NameError:
            pass
        cleanup_task.cancel()
        try:
            await cleanup_task
        except asyncio.CancelledError:
            pass
        except Exception:
            pass


# ── Security Headers Middleware ────────────────────────────────
class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline' https://cdnjs.cloudflare.com; "
            "img-src 'self' data:; "
            "font-src 'self' https://cdnjs.cloudflare.com; connect-src 'self'"
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

# Multi-key provider management (Settings → Models redesign)
try:
    from routers.providers import router as providers_router
    app.include_router(providers_router)
    logger.info("Providers router registered")
except Exception as e:
    logger.error(f"Failed to register providers router: {e}")

# Tool Marketplace (v1.1 Phase 1)
try:
    from routers.tools import router as tools_router
    app.include_router(tools_router)
    logger.info("Tools router registered")
except Exception as e:
    logger.error(f"Failed to register tools router: {e}")

# Agent Control Center (v1.1 Phase 3)
try:
    from routers.agents import router as agents_router
    app.include_router(agents_router)
    logger.info("Agents router registered")
except Exception as e:
    logger.error(f"Failed to register agents router: {e}")

# Security Dashboard (RC12.5)
try:
    app.include_router(security_router)
    logger.info("Security router registered")
except Exception as e:
    logger.error(f"Failed to register security router: {e}")

# Workflow Management (Phase P Batch 3 + Batch 5)
try:
    app.include_router(workflow_router)
    logger.info("Workflow router registered")
except Exception as e:
    logger.error(f"Failed to register workflow router: {e}")

# Workspace Management (Phase P Batch 2 — Multi-Tenant Isolation)
try:
    app.include_router(workspace_router)
    logger.info("Workspace router registered")
except Exception as e:
    logger.error(f"Failed to register workspace router: {e}")

# Human Approval Layer (v1.1 Phase 4.5.10)
try:
    from routers.approvals import router as approvals_router
    app.include_router(approvals_router)
    logger.info("Approvals router registered")
except Exception as e:
    logger.error(f"Failed to register approvals router: {e}")

# Industrial Control Plane (v1.1 Phase 5)
try:
    from routers.enterprise import router as enterprise_router
    app.include_router(enterprise_router)
    logger.info("Enterprise router registered")
except Exception as e:
    logger.error(f"Failed to register enterprise router: {e}")

# Digital Twin + Industrial Profiles (RC12.6)
try:
    from routers.digital_twin import router as digital_twin_router
    app.include_router(digital_twin_router)
    logger.info("Digital Twin router registered")
except Exception as e:
    logger.error(f"Failed to register Digital Twin router: {e}")

# Connectors Framework (RC12.7)
try:
    from routers.connectors import router as connectors_router
    app.include_router(connectors_router)
    logger.info("Connectors router registered")
except Exception as e:
    logger.error(f"Failed to register Connectors router: {e}")

# AI Code Intelligence API
try:
    from routers.ai import router as ai_router
    app.include_router(ai_router)
    logger.info("AI API router registered")
except Exception as e:
    logger.error(f"Failed to register AI router: {e}")

# Runtime API (Phase F1)
try:
    from routers.runtime_api import router as runtime_api_router
    app.include_router(runtime_api_router)
    logger.info("Runtime API router registered")
except Exception as e:
    logger.error(f"Failed to register Runtime API router: {e}")

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

from fastapi.responses import Response


@app.get("/metrics")
async def metrics():
    """Prometheus metrics endpoint for scraping."""
    exporter = getattr(app.state, "prometheus_exporter", None)
    if exporter:
        return Response(
            exporter.generate_metrics(),
            media_type=exporter.CONTENT_TYPE,
        )
    return Response(b"", media_type="text/plain; version=1.0.0; charset=utf-8")


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


PROVIDERS_INFO = {
    "openrouter": {"name": "OpenRouter"},
    "groq": {"name": "Groq"},
    "gemini": {"name": "Gemini"},
    "ollama": {"name": "Ollama (Local)"},
}


@app.get("/api/providers/status")
async def providers_status():
    """Get status of all providers (key saved, model, connection)."""
    from routers.settings import load_settings
    settings = load_settings()
    kp = KeychainProvider()
    active_provider = settings.get("provider", "openrouter")
    active_model = settings.get("model", "")

    result = {}
    for pid, info in PROVIDERS_INFO.items():
        key = kp.get(pid) or (settings.get(f"{pid}_key") if pid in ("openrouter", "gemini", "groq") else None)
        model = settings.get(f"{pid}_model", "")
        if not model and pid == active_provider:
            model = active_model
        result[pid] = {
            "name": info["name"],
            "key_saved": bool(key),
            "model": model,
            "status": "connected" if (bool(key) or pid == "ollama") else "no_key",
        }
        # Mark Ollama as offline if no local response
        if pid == "ollama" and bool(key):
            result[pid]["status"] = "unknown"

    return JSONResponse({
        "providers": result,
        "active": active_provider,
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

    response = templates.TemplateResponse(
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
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


DEFAULT_MODELS = {
    "openrouter": [
        {"id": "openai/gpt-4o", "name": "GPT-4o", "free": False},
        {"id": "openai/gpt-4o-mini", "name": "GPT-4o Mini", "free": False},
        {"id": "google/gemini-2.0-flash-001", "name": "Gemini 2.0 Flash", "free": True},
        {"id": "google/gemini-2.5-flash-preview", "name": "Gemini 2.5 Flash", "free": True},
        {"id": "meta-llama/llama-3.3-70b-instruct", "name": "Llama 3.3 70B", "free": True},
        {"id": "mistralai/mistral-small-3.1", "name": "Mistral Small 3.1", "free": False},
        {"id": "deepseek/deepseek-chat", "name": "DeepSeek V3", "free": False},
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


async def _fetch_openrouter_models(key: str) -> list | None:
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
                    prompt_cost = float(pricing.get("prompt", 1))
                    compl_cost = float(pricing.get("completion", 1))
                    is_free = prompt_cost < 0.00001 and compl_cost < 0.00001
                    models.append({
                        "id": m["id"],
                        "name": m.get("name", m["id"]),
                        "free": is_free,
                    })
                return models if models else None
    except Exception:
        return None


async def _fetch_gemini_models(key: str) -> list | None:
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                "https://generativelanguage.googleapis.com/v1beta/models",
                params={"key": key}
            )
            if r.status_code == 200:
                data = r.json()
                models = []
                supported_prefixes = ("models/gemini-", "models/gpt-")
                for m in data.get("models", []):
                    name = m.get("name", "")
                    if not any(name.startswith(p) for p in ("models/gemini-",)):
                        continue
                    supported = m.get("supportedGenerationMethods", [])
                    if "generateContent" not in supported:
                        continue
                    display_name = m.get("displayName", name.replace("models/", ""))
                    is_free = "pro" not in name.lower()
                    models.append({
                        "id": name.replace("models/", ""),
                        "name": display_name,
                        "free": is_free,
                    })
                return models if models else None
    except Exception:
        return None


async def _fetch_groq_models(key: str) -> list | None:
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(
                "https://api.groq.com/openai/v1/models",
                headers={"Authorization": f"Bearer {key}"}
            )
            if r.status_code == 200:
                data = r.json()
                models = []
                for m in data.get("data", []):
                    gid = m.get("id", "")
                    models.append({
                        "id": gid,
                        "name": m.get("name", gid) if m.get("name") else gid,
                        "free": "free" in m.get("owned_by", "").lower() or "groq" in gid.lower(),
                    })
                if models:
                    models.sort(key=lambda x: (not x["free"], x["id"]))
                return models if models else None
    except Exception:
        return None


@app.get("/api/models/{provider}")
async def list_models(provider: str, key: str = ""):
    """Fetch available models from a provider with pricing info.

    Accepts optional ?key= to use a freshly entered key.
    Falls back to Keychain, then to static defaults.
    """
    # Resolve key: parameter > Keychain
    api_key = key.strip() if key else None
    if not api_key:
        kp = KeychainProvider()
        api_key = kp.get(provider)

    live_models = None
    if api_key:
        if provider == "openrouter":
            live_models = await _fetch_openrouter_models(api_key)
        elif provider == "gemini":
            live_models = await _fetch_gemini_models(api_key)
        elif provider == "groq":
            live_models = await _fetch_groq_models(api_key)

    if live_models:
        return {"models": live_models, "source": "live"}

    fallback = DEFAULT_MODELS.get(provider, [])
    return {"models": fallback, "source": "default"}


@app.get("/api/test-connection")
async def test_connection(provider: str = "openrouter", key: str = "", model: str = ""):
    """Test actual connection to a model provider with optional model (async)."""
    api_key = key.strip() if key else None
    if not api_key:
        kp = KeychainProvider()
        api_key = kp.get(provider)
    if not api_key and provider != "ollama":
        return {"connected": False, "error": f"No API key for {provider}"}

    try:
        import time
        start = time.time()
        b = Brain(provider=provider, api_key=api_key, model=model or None)
        response = await b.ask_async(user="Write the word OK and nothing else", max_tokens=10)
        latency = int((time.time() - start) * 1000)
        is_ok = 'OK' in response.strip().upper()
        if is_ok:
            return {"connected": True, "latency": latency}
        else:
            return {"connected": True, "latency": latency, "note": f"Unexpected response: {response.strip()[:50]}"}
    except Exception as e:
        err = str(e)
        safe_err = err.encode('ascii', errors='replace').decode('ascii')
        return {"connected": False, "error": safe_err, "model_tested": model or "default"}


@app.get("/api/test-telegram")
async def test_telegram(token: str = ""):
    """Test Telegram bot token via direct API call."""
    if not token:
        return {"connected": False, "error": "No token provided"}
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"https://api.telegram.org/bot{token}/getMe")
            if r.status_code == 200:
                data = r.json()
                if data.get("ok"):
                    bot_user = data["result"]
                    return {"connected": True, "bot_name": bot_user.get("username", bot_user.get("first_name", "ok"))}
                else:
                    return {"connected": False, "error": data.get("description", "Invalid token")}
            else:
                return {"connected": False, "error": f"HTTP {r.status_code}"}
    except Exception as e:
        return {"connected": False, "error": str(e)}


@app.get("/api/test-github")
async def test_github(token: str = ""):
    """Test GitHub personal access token."""
    if not token:
        return {"connected": False, "error": "No token provided"}
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get("https://api.github.com/user", headers={"Authorization": f"Bearer {token}", "User-Agent": "EmoAI"})
            if r.status_code == 200:
                data = r.json()
                return {"connected": True, "user": data.get("login", "ok")}
            else:
                return {"connected": False, "error": f"HTTP {r.status_code}: {r.text[:100]}"}
    except Exception as e:
        return {"connected": False, "error": str(e)}


@app.get("/api/tray/ping")
async def tray_ping():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", "8080"))
    host = os.getenv("HOST", "0.0.0.0")
    uvicorn.run(app, host=host, port=port, log_config=None)

