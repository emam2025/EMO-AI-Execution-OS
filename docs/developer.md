# EMO AI Orchestrator — Developer Reference Guide

| Item                 | Value                                        |
|----------------------|----------------------------------------------|
| **Date**             | 2026-05-17                                   |
| **Author**           | opencode AI Agent                            |
| **Status**           | Final — Official Reference                   |
| **Version**          | 1.0.0                                        |
| **Project**          | EMO AI Orchestrator v4.0.0                   |
| **License**          | Open Source (MIT/Apache 2.0 — TBD)           |
| **Platforms**        | macOS + Windows + Android (web-responsive)   |
| **Target**           | 3 users in initial phase                     |
| **Compliance**       | GDPR + SOC2                                  |

---

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Project Structure](#2-project-structure)
3. [Dependency Map](#3-dependency-map)
4. [Core Components](#4-core-components)
5. [API Reference](#5-api-reference)
6. [Agent System](#6-agent-system)
7. [Tools System](#7-tools-system)
8. [Development Environment Setup](#8-development-environment-setup)
9. [Operation Guide](#9-operation-guide)
10. [Maintenance Guide](#10-maintenance-guide)
11. [Troubleshooting](#11-troubleshooting)
12. [Security and Compliance](#12-security-and-compliance)
13. [Data Models](#13-data-models)
14. [Contribution Guide](#14-contribution-guide)
15. [Changelog](#15-changelog)

---

## 1. Project Overview

### 1.1 What is EMO AI Orchestrator?

A Multi-Agent Intelligence Orchestration System that acts as an intermediary layer between the user and artificial intelligence models. The system manages multiple agents and routes tasks automatically via an interactive web interface and Telegram integration.

### 1.2 Key Features

| Feature | Description | Status |
|---------|-------------|--------|
| Smart Conversations | Chat with multiple AI agents | ⚠️ Partial (mock) |
| Multi-Agent | Planner, Coder, Writer, Researcher | ⚠️ stubs |
| Multiple Models | OpenRouter, Groq, Gemini (API) + Ollama (local) | ⚠️ stub |
| DevOps Tools | Vercel, Docker, Env Manager | ✅ Working |
| Project Tools | Debugger, Code Reviewer, Scaffold, Analyzer | ✅ Working |
| GitHub Integration | Repository management via API | ✅ Working |
| Supabase Integration | Database + Storage | ✅ Working |
| Firebase Integration | Firestore + Auth + Hosting | ✅ Working |
| Telegram Bot | Chat via Telegram | ✅ Working |
| Web UI | Glass Morphism + RTL/LTR + Dark/Light | ✅ Working |
| System Tray | Server monitoring (macOS) | ✅ Working |

### 1.3 Technologies Used

| Technology | Version | Usage |
|------------|---------|-------|
| Python | 3.14 | Core language |
| FastAPI | Latest | HTTP framework |
| Uvicorn | Latest | ASGI Server |
| Pydantic | Latest | Data validation |
| python-dotenv | Latest | Environment variable management |
| TailwindCSS | CDN | UI design |
| Font Awesome | 6.5.1 | Icons |
| python-telegram-bot | Optional | Telegram integration |
| rumps | Optional | System Tray (macOS) |
| psutil | Optional | Process monitoring |
| openai | Required | SDK for LLM communication |
| fpdf | Optional | PDF generation |

---

## 2. Project Structure

```
Emo-AI/
│
├── 📄 main.py                          # Entry point — FastAPI app
├── 📄 brain.py                         # LLM interface (STUB — needs implementation)
├── 📄 brain.py.save                    # Backup with real implementation (OpenAI SDK)
├── 📄 agent.py                         # Agent system (STUB)
├── 📄 memory.py                        # Memory system (STUB)
├── 📄 tools.py                         # Tool registry (STUB — needs Tool base class)
├── 📄 i18n.py                          # Translation (Arabic/English) — ✅ Complete
├── 📄 telegram_bot.py                  # Telegram bot — ✅ Working
├── 📄 tray.py                          # System Tray (macOS) — ✅ Working
├── 📄 generate_pdf.py                  # Documentation PDF generator — ✅ Working
│
├── 📄 project_tools.py                 # Project intelligence tools (8 classes, 1409 lines) — ✅ Working
├── 📄 devops_tools.py                  # DevOps tools (4 classes, 273 lines) — ✅ Working
├── 📄 supabase_tools.py                # Supabase tools (6 classes, 220 lines) — ✅ Working
├── 📄 firebase_tools.py                # Firebase tools (5 classes, 196 lines) — ✅ Working
├── 📄 github_tools.py                  # GitHub tools (7 classes, 193 lines) — ✅ Working
│
├── 📁 core/
│   ├── 📄 state.py                     # Application global state (Singleton) — ✅ Working
│   ├── 📄 context_builder.py           # Conversation context builder — ✅ Working
│   ├── 📄 task_manager.py              # Task management (thread-safe) — ✅ Working
│   └── 📄 tasks.py                     # Task cleanup loop (STUB)
│
├── 📁 routers/
│   └── 📄 chat.py                      # Chat API endpoint — ⚠️ Partial
│
├── 📁 templates/
│   ├── 📄 index.html                   # Main interface (1109 lines) — ✅ Complete
│   └── 📄 login.html                   # Login page (171 lines) — ✅ Complete
│
├── 📁 static/                          # Static files (CSS, JS, images)
│
├── 📁 docs/                            # Project documentation
│   ├── 📄 REQUIREMENTS_UNDERSTANDING.md # Requirements document
│   ├── 📄 core_features_api.json       # API specification
│   ├── 📄 PROGRESS.md                  # Progress log
│   └── 📄 developer.md                 # This file
│
├── 📄 requirements.txt                 # Core requirements (4 packages only!)
├── 📄 README.md                        # Brief README
│
├── 📄 .emo_settings.json               # App settings (⚠️ API keys exposed!)
├── 📄 .emo_conversations.json          # Conversation data
├── 📄 .emo_chat_history.json           # Chat history
│
├── 📄 .env                             # Environment variables (must be created — not yet present)
├── 📄 .gitignore                       # Files excluded from Git
│
├── 📁 venv/                            # Python virtual environment (excluded)
├── 📁 __pycache__/                     # Compiled Python files (excluded)
│
└── 📁 my-project/                      # Generated projects (scaffolded artifacts)
    📁 my_project/
    📁 test-app/
```

### 2.1 File Descriptions

#### Core Files

| File | Lines | Status | Description |
|------|-------|--------|-------------|
| `main.py` | 36 | ✅ Working | FastAPI entry point. Creates app, manages lifespan with background cleanup, runs Uvicorn on port 8080 |
| `brain.py` | 6 | ❌ STUB | LLM interface. Currently returns user text as-is. **Must be replaced with `brain.py.save`** |
| `brain.py.save` | 28 | ✅ Working | Real implementation using `openai.OpenAI` with OpenRouter/Groq support via `LLM_PROVIDER` env var |
| `agent.py` | 16 | ❌ STUB | Agent class and factory. Creates 3 agents (planner, writer, researcher) but with mock Brain |
| `memory.py` | 3 | ❌ STUB | Empty Memory class. `data = []` list with no logic |
| `tools.py` | 9 | ❌ STUB | Simple Registry. Does not contain `Tool` base class imported by other tools |

#### Tools

| File | Lines | Classes | Status | Description |
|------|-------|---------|--------|-------------|
| `project_tools.py` | 1409 | 8 | ✅ Working | AutoDebugger, AICodeReviewer, ProjectMonitor, ProjectScaffold, ProjectAnalyzer, DependencyManager, CodebaseRefactor, DeploymentBuilder |
| `devops_tools.py` | 273 | 4 | ✅ Working | VercelDeploy, DockerBuild, DockerRun, EnvManager |
| `supabase_tools.py` | 220 | 6 | ✅ Working | CreateProject, CreateTable, InsertData, Query, AuthSetup, StorageUpload |
| `firebase_tools.py` | 196 | 5 | ✅ Working | InitProject, AuthSetup, FirestoreWrite, FirestoreRead, Deploy |
| `github_tools.py` | 193 | 7 | ✅ Working | CreateRepo, CloneRepo, PushChanges, PullRepo, ReadFile, WriteFile, CreateBranch |

#### Core

| File | Lines | Status | Description |
|------|-------|--------|-------------|
| `core/state.py` | 17 | ⚠️ Bug | Singleton for global state. **Bug: does not define `conversations` but `chat.py` uses it** |
| `core/context_builder.py` | 63 | ✅ Working | Builds conversation context: last 12 messages, 1200 char/message limit, text cleaning |
| `core/task_manager.py` | 24 | ✅ Working | Thread-safe task management with dict. Basic CRUD without SSE |
| `core/tasks.py` | 5 | ❌ STUB | Task cleanup loop — sleeps 300 seconds doing nothing |

#### Integration

| File | Lines | Status | Description |
|------|-------|--------|-------------|
| `telegram_bot.py` | 197 | ✅ Working | Complete Telegram bot: authorization, commands, forwarding. Runs in separate thread |
| `tray.py` | 543 | ✅ Working | macOS system tray app: monitoring, restart, notifications. Fallback console mode |
| `i18n.py` | 262 | ✅ Working | ~130 translation keys per language (EN/AR). `t(key, lang)` function |

#### Templates

| File | Lines | Status | Description |
|------|-------|--------|-------------|
| `templates/index.html` | 1109 | ✅ Complete | Main interface: 3 panels (conversations/agents, chat, log/tasks). Glass Morphism + TailwindCSS |
| `templates/login.html` | 171 | ✅ Complete | Login/signup page with particle animation |

---

## 3. Dependency Map

### 3.1 Import Diagram

```
main.py
├── routers/chat.py
│   ├── core/state.py
│   │   ├── memory.py (STUB)
│   │   ├── tools.py (STUB)
│   │   ├── brain.py (STUB)
│   │   ├── agent.py (STUB)
│   │   └── core/task_manager.py
│   └── core/context_builder.py
└── core/tasks.py

tray.py (standalone — calls main.py via subprocess)
telegram_bot.py (standalone — needs on_message callback)

project_tools.py  ──┐
devops_tools.py     │
supabase_tools.py   ├──> tools.Tool (not found! use fallback)
firebase_tools.py   │
github_tools.py     ┘

i18n.py (not imported — used for server-side rendering)
generate_pdf.py (standalone utility)
```

### 3.2 External Dependencies (requirements.txt)

```
fastapi          # HTTP framework
uvicorn          # ASGI Server
pydantic         # Data validation
python-dotenv    # Environment variables
```

### 3.3 Required Uninstalled Dependencies

| Package | Reason | Priority |
|---------|--------|----------|
| `openai` | Connect Brain to real LLM | 🔴 Critical |
| `python-telegram-bot` | Telegram integration | 🟡 High |
| `rumps` | System Tray (macOS) | 🟡 High |
| `psutil` | Process monitoring | 🟢 Medium |
| `fpdf` | PDF generation | 🟢 Medium |
| `aiosqlite` | Async SQLite database | 🟡 High |
| `PyJWT` | JWT authentication | 🟡 High |
| `bcrypt` | Password encryption | 🟡 High |
| `httpx` | Async HTTP client for Ollama | 🟡 High |

---

## 4. Core Components

### 4.1 FastAPI Application (`main.py`)

```python
# Main entry point
app = FastAPI(
    title="Emo AI Orchestrator",
    version="4.0.0",
    lifespan=lifespan  # Manages cleanup_old_tasks_loop
)

# Registered routers
app.include_router(chat_router)  # /api/chat

# Current endpoints
GET  /          # Server status
POST /api/chat  # Send message

# Required endpoints (not present)
GET  /api/stream/{task_id}       # SSE for live streaming
GET  /api/tasks                  # Task list
GET  /api/conversations          # Conversation list
POST /api/conversations          # Create conversation
POST /api/conversations/{id}/activate  # Activate conversation
DELETE /api/conversations/{id}   # Delete conversation
POST /api/settings               # Update setting
GET  /api/status                 # LLM status
GET  /api/history                # Conversation history
GET  /api/global_stream          # Global SSE stream
GET  /api/project                # Project information
GET  /api/tray/ping              # Server health check
POST /api/auth/login             # Login
POST /api/auth/signup            # Create account
GET  /api/auth/verify            # Verify token
```

### 4.2 AppState (`core/state.py`)

```python
class AppState:
    tools: Registry          # ⚠️ stub
    memory: Memory           # ⚠️ stub
    task_manager: TaskManager # ✅ Working
    agents: dict             # ⚠️ stubs (planner, writer, researcher)
    conversations: dict      # ❌ Not defined (BUG!)

state = AppState()  # Global singleton
```

### 4.3 TaskManager (`core/task_manager.py`)

```python
class TaskManager:
    tasks: dict              # {task_id: {id, message, status, created_at}}
    lock: threading.Lock     # thread-safe

    create_task(task_id, message)   # → pending
    update_task(task_id, **kwargs)  # → running/complete/error
    get_task(task_id)               # → dict or None
```

### 4.4 ContextBuilder (`core/context_builder.py`)

```python
MAX_CONTEXT_MESSAGES = 12
MAX_MESSAGE_LENGTH = 1200

def _clean_text(text: str) -> str:
    # Removes extra spaces and truncates text

def build_conversation_context(messages: List[Dict]) -> str:
    # Takes last 12 messages, cleans them, returns "ROLE: content"
```

### 4.5 Brain (`brain.py`) — Needs Implementation

```python
# Current (STUB):
class Brain:
    def ask(self, system="", user="", **kwargs):
        return f"AI Response => {user}"  # ❌ echo only

    def test_connection(self):
        return True, "mock-model"  # ❌ mock

# Required (from brain.py.save):
class Brain:
    def __init__(self, provider="openrouter", model="", api_key=""):
        # Selects provider and creates openai.OpenAI client

    def ask(self, system="", user="", **kwargs):
        # Calls client.chat.completions.create()

    def test_connection(self):
        # Tests real connection
```

---

## 5. API Reference

### 5.1 Existing Endpoints

#### `GET /`
- **Description:** Server status
- **Response:** `{"name": "Emo AI Orchestrator", "version": "4.0.0", "status": "running"}`

#### `POST /api/chat`
- **Description:** Send message and start task
- **Input:**
  ```json
  {
    "message": "string (required)",
    "conversation_id": "string (optional)"
  }
  ```
- **Response:**
  ```json
  {
    "task_id": "string (8-char UUID)",
    "status": "started"
  }
  ```
- **Behavior:** Creates task, starts background thread, calls planner agent

### 5.2 Required Endpoints (Not Present)

All endpoints called by the frontend but not implemented in the server:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/stream/{task_id}` | GET (SSE) | Live task progress streaming |
| `/api/tasks` | GET | Task list |
| `/api/conversations` | GET | Conversation list |
| `/api/conversations` | POST | Create conversation |
| `/api/conversations/{id}/activate` | POST | Activate conversation |
| `/api/settings` | POST | Update setting |
| `/api/status` | GET | LLM status |
| `/api/history` | GET | Conversation history |
| `/api/global_stream` | GET (SSE) | Global event stream |
| `/api/project` | GET | Project information |
| `/api/tray/ping` | GET | Server health check |
| `/api/auth/login` | POST | Login |
| `/api/auth/signup` | POST | Create account |
| `/api/auth/verify` | GET | Verify token |
| `/api/speedtest` | GET | Speed test |

---

## 6. Agent System

### 6.1 Current Agents

| Agent | Role | Color | Status |
|-------|------|-------|--------|
| Planner | Task planning and distribution | Purple (#8b5cf6) | ❌ stub |
| Coder | Code writing and correction | Green (#10b981) | ❌ Not present |
| Writer | Document writing | Pink (#ec4899) | ❌ stub |
| Researcher | Research and verification | Orange (#f59e0b) | ❌ stub |

### 6.2 Task Lifecycle

```
1. User sends message → POST /api/chat
2. Server creates task_id
3. Creates background thread → process_task()
4. Creates conversation context → build_conversation_context()
5. Sends to Planner → planner.run(input)
6. Planner responds with result
7. Task status updated → complete
8. (Required) Result streamed via SSE
```

### 6.3 Required Implementation

```
1. Connect Brain to OpenRouter API (FR-03.01)
2. Connect Brain to Groq API (FR-03.02)
3. Connect Brain to Gemini API (FR-03.03)
4. Connect Brain to local Ollama (FR-03.07)
5. Add Coder Agent
6. Implement automatic task routing (FR-02.05)
7. Connect tools to agents (FR-04)
```

---

## 7. Tools System

### 7.1 Categories

| Category | Tool Count | Tools |
|----------|------------|-------|
| DevOps | 4 | VercelDeploy, DockerBuild, DockerRun, EnvManager |
| Project Intelligence | 8 | AutoDebugger, AICodeReviewer, ProjectMonitor, ProjectScaffold, ProjectAnalyzer, DependencyManager, CodebaseRefactor, DeploymentBuilder |
| GitHub | 7 | CreateRepo, CloneRepo, PushChanges, PullRepo, ReadFile, WriteFile, CreateBranch |
| Supabase | 6 | CreateProject, CreateTable, InsertData, Query, AuthSetup, StorageUpload |
| Firebase | 5 | InitProject, AuthSetup, FirestoreWrite, FirestoreRead, Deploy |
| System | 2 | shell, files (not implemented) |

### 7.2 Tool Base Class Issue

Tools try to import `Tool` from `tools.py` but the file does not define it:

```python
# Current tools.py — does not contain Tool!
class Registry:
    def categories(self):
        return {"system": ["shell", "files"], "ai": ["vision", "memory"]}

# All *_tools.py files use fallback:
try:
    from tools import Tool
except ImportError:
    class Tool:  # fallback
        name = ""
        description = ""
        category = ""
        icon = ""
        parameters = {}
```

**Required Solution:** Add `Tool` base class to `tools.py`:

```python
from abc import ABC, abstractmethod

class Tool(ABC):
    name: str = ""
    description: str = ""
    category: str = ""
    icon: str = ""
    parameters: dict = {}

    @abstractmethod
    def run(self, **kwargs) -> str:
        pass
```

---

## 8. Development Environment Setup

### 8.1 Prerequisites

| Requirement | Version | Installation Method |
|-------------|---------|---------------------|
| Python | 3.11+ | `brew install python` (macOS) |
| pip | Bundled with Python | — |
| Node.js | 18+ (for Vercel tools) | `brew install node` |
| Docker | Optional | Docker Desktop |
| Ollama | Optional (local LLM) | `brew install ollama` |
| Git | 2.40+ | `brew install git` |

### 8.2 Setup Steps

```bash
# 1. Clone the project
git clone <repo-url>
cd Emo-AI

# 2. Create virtual environment
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
# Or: venv\Scripts\activate  # Windows

# 3. Install core requirements
pip install -r requirements.txt

# 4. Install additional requirements
pip install openai aiosqlite PyJWT bcrypt httpx python-telegram-bot rumps psutil fpdf

# 5. Create .env file
cp .env.example .env
# Edit .env with your keys

# 6. Run server
python main.py
# Or: uvicorn main:app --host 0.0.0.0 --port 8080 --reload

# 7. Verify
curl http://localhost:8080/
# → {"name": "Emo AI Orchestrator", "version": "4.0.0", "status": "running"}
```

### 8.3 .env.example

```bash
# EMO AI Orchestrator — Environment Variables
# Copy this file to .env and fill in the values

# === LLM Providers (API) ===
OPENROUTER_API_KEY=
GROQ_API_KEY=
GEMINI_API_KEY=

# === LLM Provider (Local) ===
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.2

# === Active Provider ===
LLM_PROVIDER=openrouter  # openrouter | groq | gemini | ollama
LLM_MODEL=

# === Authentication ===
EMO_AUTH_ENABLED=false
EMO_AUTH_USERNAME=
EMO_AUTH_PASSWORD=
EMO_JWT_SECRET=change-me-to-random-string

# === Telegram ===
TELEGRAM_TOKEN=
TELEGRAM_ENABLED=false

# === Cloud Services ===
SUPABASE_URL=
SUPABASE_SERVICE_KEY=
SUPABASE_SERVICE_ROLE_KEY=
FIREBASE_API_KEY=
FIREBASE_PROJECT_ID=
GITHUB_TOKEN=

# === Server ===
PORT=8080
HOST=0.0.0.0
DEBUG=true

# === Project ===
EMO_AI_WORKSPACE_ROOT=.
EMO_PROJECT_DIR=.
```

### 8.4 .gitignore

```
# Python
__pycache__/
*.py[cod]
*.so
.Python
*.egg-info/
dist/
build/

# Virtual Environment
venv/
.venv/

# Environment
.env
*.env

# IDE
.vscode/
.idea/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db

# Node
node_modules/
npm-debug.log

# Emo AI Data
.emo_settings.json
.emo_conversations.json
.emo_chat_history.json
*.pdf

# Generated Projects
my-project/
my_project/
test-app/

# Logs
*.log
logs/
```

---

## 9. Operation Guide

### 9.1 Running the Server

```bash
# Basic method
python main.py

# With Uvicorn directly (with auto-reload for development)
uvicorn main:app --host 0.0.0.0 --port 8080 --reload

# In background (production)
nohup uvicorn main:app --host 0.0.0.0 --port 8080 > emo.log 2>&1 &

# With Docker (after creating Dockerfile)
docker build -t emo-ai .
docker run -p 8080:8080 --env-file .env emo-ai
```

### 9.2 Running Telegram Bot

```python
# Add to main.py:
from telegram_bot import TelegramBot

def telegram_callback(message):
    """Route Telegram message to orchestrator"""
    # Call chat endpoint
    ...

bot = TelegramBot(
    token=os.getenv("TELEGRAM_TOKEN", ""),
    on_message_callback=telegram_callback
)
if bot.token and bot.is_available:
    bot.start()
```

### 9.3 Running System Tray

```bash
# macOS
python tray.py

# With rumps not installed
pip install rumps psutil
python tray.py

# Console fallback mode (without rumps)
python tray.py  # Auto-switches to simple_mode()
```

### 9.4 Running Ollama (Local)

```bash
# Install Ollama
brew install ollama

# Run service
ollama serve &

# Download model
ollama pull llama3.2

# Verify
curl http://localhost:11434/api/tags

# Configure .env
LLM_PROVIDER=ollama
OLLAMA_MODEL=llama3.2
```

### 9.5 Generate Documentation PDF

```bash
pip install fpdf
python generate_pdf.py
# → Produces EMO_AI_ORCHESTRATOR_REFERENCE.pdf
```

---

## 10. Maintenance Guide

### 10.1 Daily Maintenance

| Task | Command | Frequency |
|------|---------|-----------|
| Check server status | `curl http://localhost:8080/` | Daily |
| Check logs | `tail -f emo.log` | Daily |
| Check disk space | `du -sh .emo_*.json` | Weekly |
| Update requirements | `pip list --outdated` | Weekly |

### 10.2 Weekly Maintenance

| Task | Description |
|------|-------------|
| Clean old conversations | Delete conversations > 30 days from `.emo_conversations.json` |
| Clean old tasks | TaskManager supposed to auto-clean (but it's a stub) |
| Review logs | Look for recurring errors |
| Update libraries | `pip install --upgrade -r requirements.txt` |

### 10.3 Monthly Maintenance

| Task | Description |
|------|-------------|
| Security review | Check `.env` and `.emo_settings.json` |
| Dependency review | `pip audit` to check for vulnerabilities |
| Backup | Copy `.emo_*.json` to a safe location |
| Update Ollama | `ollama pull <model>` for latest version |

### 10.4 Data Files

| File | Approximate Size | When it grows | How to clean |
|------|-----------------|---------------|--------------|
| `.emo_conversations.json` | 10KB-1MB | Each new conversation | Delete old conversations |
| `.emo_chat_history.json` | 10KB-5MB | Each message | Max 1000 messages |
| `.emo_settings.json` | <1KB | Rarely | No cleanup needed |

### 10.5 Backup

```bash
# Manual backup
tar czf emo-backup-$(date +%Y%m%d).tar.gz \
  .emo_settings.json \
  .emo_conversations.json \
  .emo_chat_history.json \
  docs/

# Restore
tar xzf emo-backup-YYYYMMDD.tar.gz
```

---

## 11. Troubleshooting

### 11.1 Common Errors

| Error | Cause | Solution |
|-------|-------|----------|
| `AttributeError: 'AppState' object has no attribute 'conversations'` | `state.py` does not define `conversations` | Add `self.conversations = {}` in `AppState.__init__` |
| `ImportError: cannot import name 'Tool' from 'tools'` | `tools.py` does not define `Tool` base class | Add `Tool` class as in section 7.2 |
| `ModuleNotFoundError: No module named 'openai'` | openai library not installed | `pip install openai` |
| `ModuleNotFoundError: No module named 'telegram'` | python-telegram-bot not installed | `pip install python-telegram-bot` |
| `ModuleNotFoundError: No module named 'rumps'` | rumps not installed (macOS only) | `pip install rumps` or use console mode |
| Server not responding | Port 8080 is busy | Change port: `PORT=8081 python main.py` |
| API keys not working | Not set in `.env` | Create `.env` and copy keys |
| Ollama not responding | Service not running | `ollama serve` |
| Telegram bot not working | Incorrect token or python-telegram-bot not installed | Check token and `pip install python-telegram-bot` |

### 11.2 Health Check

```bash
# 1. Check server
curl http://localhost:8080/
# → {"name": "Emo AI Orchestrator", "version": "4.0.0", "status": "running"}

# 2. Check Tray ping (if server is running)
curl http://localhost:8080/api/tray/ping

# 3. Check LLM
curl http://localhost:8080/api/status

# 4. Check conversations
curl http://localhost:8080/api/conversations

# 5. Check tasks
curl http://localhost:8080/api/tasks

# 6. Check Ollama connection
curl http://localhost:11434/api/tags
```

### 11.3 Debug Mode

```bash
# Run with verbose logging
DEBUG=true uvicorn main:app --host 0.0.0.0 --port 8080 --reload --log-level debug

# Check logs
tail -f emo.log | grep -i error

# Python debugger
python -m pdb main.py
```

### 11.4 Full Reset

```bash
# Delete everything and start fresh
rm -rf venv/
rm -rf __pycache__/
rm -rf *.egg-info/
rm -f .emo_conversations.json
rm -f .emo_chat_history.json

# Re-setup
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install openai aiosqlite PyJWT bcrypt httpx
cp .env.example .env
# Edit .env
python main.py
```

---

## 12. Security and Compliance

### 12.1 Secrets Management

| Rule | Description |
|------|-------------|
| ❌ Do not put API keys in code | Always use `.env` |
| ❌ Do not upload `.env` to Git | Ensure `.gitignore` |
| ❌ Do not expose keys in UI | Use `type="password"` in HTML |
| ✅ Use `python-dotenv` | To load `.env` automatically |
| ✅ Encrypt passwords | Use `bcrypt` |
| ✅ Use JWT for authentication | Tokens with limited expiry |

### 12.2 GDPR Requirements

| Requirement | Required Implementation |
|-------------|------------------------|
| Right of access | API endpoint to export user data |
| Right to erasure | API endpoint to permanently delete user data |
| Right to rectification | API endpoint to modify user data |
| Consent | Consent screen before data collection |
| Data minimization | Collect minimal data possible |
| Encryption | Encrypt sensitive data at rest |

### 12.3 SOC2 Requirements

| Requirement | Required Implementation |
|-------------|------------------------|
| Audit logs | Log every sensitive operation |
| Access control | Authentication + authorization for every endpoint |
| Encryption in transit | HTTPS (TLS 1.2+) |
| Encryption at rest | Encrypt data files |
| Incident response | Incident response plan |
| Regular testing | Periodic penetration tests |

### 12.4 Data Encryption

```python
# Password encryption
import bcrypt
password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt())

# Verification
bcrypt.checkpw(password.encode(), stored_hash)

# Sensitive data encryption (Example: Fernet)
from cryptography.fernet import Fernet
key = Fernet.generate_key()
f = Fernet(key)
encrypted = f.encrypt(secret_data.encode())
decrypted = f.decrypt(encrypted).decode()
```

---

## 13. Data Models

### 13.1 Task

```json
{
  "id": "a1b2c3d4",
  "message": "Original message text",
  "status": "pending | running | complete | error",
  "result": "string | null",
  "error": "string | null",
  "created_at": "2026-05-17T10:30:00Z",
  "updated_at": "2026-05-17T10:30:05Z",
  "conversation_id": "uuid | null"
}
```

### 13.2 Conversation

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "name": "Test conversation",
  "messages": [
    {
      "role": "user | assistant | system",
      "content": "Message text",
      "timestamp": "2026-05-17T10:30:00Z",
      "file_data": {
        "name": "image.png",
        "type": "image/png",
        "size": 102400,
        "base64": "..."
      }
    }
  ],
  "created_at": "2026-05-17T10:00:00Z"
}
```

### 13.3 Settings

```json
{
  "lang": "en | ar",
  "theme": "dark | light",
  "provider": "openrouter | groq | gemini | ollama",
  "model": "llama3.2",
  "openrouter_key": "***",
  "groq_key": "***",
  "gemini_key": "***",
  "system_instructions": "",
  "project_dir": ".",
  "auth_enabled": false,
  "auth_username": "",
  "auth_password_hash": "",
  "telegram_token": "***",
  "telegram_enabled": false,
  "permissions": {},
  "custom_providers": {}
}
```

### 13.4 Agent

```json
{
  "name": "planner | coder | writer | researcher",
  "status": "idle | busy | error",
  "current_task": "task_id | null",
  "brain": "Brain instance"
}
```

---

## 14. Contribution Guide

### 14.1 Code Standards

| Standard | Description |
|----------|-------------|
| PEP 8 | Official Python formatting guide |
| Type Hints | Use type hints in all functions |
| Docstrings | Every class and function must have docstring |
| SOLID | Follow SOLID principles |
| 12-Factor App | Follow 12-Factor principles |

### 14.2 Commit Structure

```
<type>(<scope>): <description>

Types: feat, fix, docs, style, refactor, test, chore
Examples:
  feat(brain): add Ollama local LLM support
  fix(chat): resolve missing conversations attribute
  docs(readme): update installation instructions
  refactor(tools): extract Tool base class
  test(task_manager): add unit tests for CRUD
```

### 14.3 Pull Request Process

1. Create new branch: `git checkout -b feat/feature-name`
2. Implement changes with clear commits
3. Test locally: `python main.py` + check endpoints
4. Open PR with clear description
5. Wait for code review
6. Revise according to feedback
7. Merge after approval

### 14.4 Testing Changes

```bash
# Basic check
python main.py
curl http://localhost:8080/

# Check conversation
curl -X POST http://localhost:8080/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "test"}'

# Check SSE
curl -N http://localhost:8080/api/stream/<task_id>
```

---

## 15. Changelog

### v4.0.0 (Current)
- Basic FastAPI structure
- Complete web UI (Glass Morphism)
- DevOps and Project Intelligence tools
- GitHub, Supabase, Firebase integration
- Telegram Bot
- System Tray (macOS)
- i18n (EN/AR)
- ⚠️ Brain/Agent/Memory/Tools = stubs

### v4.1.0 (Planned — MVP)
- [ ] Connect Brain to OpenRouter/Groq/Gemini/Ollama
- [ ] Implement SSE stream
- [ ] Enable authentication
- [ ] Move API keys to .env
- [ ] Add Tool base class
- [ ] Fix AppState.conversations bug
- [ ] Add SQLite
- [ ] Dockerfile
- [ ] Unit tests

### v5.0.0 (Planned — Post-MVP)
- [ ] Long-term memory (Vector DB)
- [ ] Custom agents
- [ ] Advanced permission system
- [ ] CI/CD pipeline
- [ ] Load tests
- [ ] Multi-tenant support

---

## Appendices

### A. Quick CLI Commands

```bash
# Run server
python main.py

# Run with auto-reload
uvicorn main:app --reload --port 8080

# Run Telegram bot
python -c "from telegram_bot import TelegramBot; b = TelegramBot(token='YOUR_TOKEN'); b.start()"

# Run System Tray
python tray.py

# Generate PDF
python generate_pdf.py

# Check dependencies
pip list --outdated
pip audit

# Cleanup
find . -type d -name __pycache__ -exec rm -rf {} +
find . -type f -name "*.pyc" -delete
```

### B. Useful Links

| Resource | Link |
|----------|------|
| FastAPI Docs | https://fastapi.tiangolo.com/ |
| OpenAI SDK | https://github.com/openai/openai-python |
| Ollama API | https://github.com/ollama/ollama/blob/main/docs/api.md |
| OpenRouter | https://openrouter.ai/docs |
| Groq API | https://console.groq.com/docs |
| Gemini API | https://ai.google.dev/docs |
| python-telegram-bot | https://docs.python-telegram-bot.org/ |
| rumps (macOS tray) | https://github.com/jaredks/rumps |
| TailwindCSS | https://tailwindcss.com/ |

### C. Urgent Task List

| # | Task | Priority | Effort |
|---|------|----------|--------|
| 1 | Move API keys to `.env` | 🔴 Critical | 30 minutes |
| 2 | Replace `brain.py` with `brain.py.save` | 🔴 Critical | 1 hour |
| 3 | Add `Tool` base class to `tools.py` | 🔴 Critical | 30 minutes |
| 4 | Fix `AppState.conversations` bug | 🔴 Critical | 15 minutes |
| 5 | Implement SSE stream | 🔴 Critical | 3-4 hours |
| 6 | Add `openai` to requirements.txt | 🟡 High | 5 minutes |
| 7 | Implement JWT authentication | 🟡 High | 4-6 hours |
| 8 | Create Dockerfile | 🟡 High | 2 hours |
| 9 | Add SQLite | 🟡 High | 1-2 days |
| 10 | Basic unit tests | 🟡 High | 1 day |

---

**End of Document — Version 1.0.0**

*This document is an official reference for developers. Any modifications should be updated here first.*

*For inquiries: Check "Troubleshooting" section or open an issue in the repository.*
