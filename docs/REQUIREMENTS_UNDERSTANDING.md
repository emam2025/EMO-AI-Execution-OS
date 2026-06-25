# Requirements Understanding Document — EMO AI Orchestrator

| Item                 | Value                                        |
|----------------------|----------------------------------------------|
| **Date**             | 2026-05-17                                   |
| **Author**           | opencode agent (AI Software Engineer)        |
| **Status**           | Updated — Stakeholder decisions included     |
| **Version**          | 1.1.0-UPDATED                                |
| **Project**          | EMO AI Orchestrator                          |

---

## 1. Project Summary

EMO AI Orchestrator is a Multi-Agent Intelligence Orchestration System that acts as an intermediary layer between the user and various artificial intelligence models. The system manages multiple agents (Planner, Coder, Writer, Researcher) and routes tasks automatically, with an interactive web interface and integration with Telegram, DevOps tools, and cloud platforms (Supabase, Firebase, GitHub).

**Current Code State:** The project exists in version v4.0.0 with a FastAPI structure, but the core components (Brain, Agent, Memory, Tools Registry) are **stubs/mock** — meaning they do not actually connect to LLM models or execute real tools.

---

## 2. Functional Requirements

### FR-01: Chat & Conversations
| Item | Description | Priority |
|------|-------------|----------|
| FR-01.01 | Send a text message and receive a reply via API `/api/chat` | Must |
| FR-01.02 | Create/Activate/Delete conversations | Must |
| FR-01.03 | Save conversation history locally (JSON) | Must |
| FR-01.04 | Support file uploads (images, documents) | Should |
| FR-01.05 | Live progress streaming via Server-Sent Events (SSE) | Must |

### FR-02: Multi-Agent System
| Item | Description | Priority |
|------|-------------|----------|
| FR-02.01 | Planner Agent: Task planning and distribution | Must |
| FR-02.02 | Coder Agent: Code generation and correction | Must |
| FR-02.03 | Writer Agent: Document and content writing | Should |
| FR-02.04 | Researcher Agent: Research and fact-checking | Should |
| FR-02.05 | Automatic task routing to the appropriate agent | Must |
| FR-02.06 | Support for custom agents | Could |

### FR-03: LLM Model Integration
| Item | Description | Priority |
|------|-------------|----------|
| FR-03.01 | Support OpenRouter as primary provider (API) | Must |
| FR-03.02 | Support Groq as alternative provider (API) | Must |
| FR-03.03 | Support Gemini as alternative provider (API) | Should |
| FR-03.04 | Dynamic model selection from settings | Must |
| FR-03.05 | Test connection to model | Must |
| FR-03.06 | Support Custom Providers | Could |
| FR-03.07 | Support local models via Ollama | Must |
| FR-03.08 | Seamless switching between API and Ollama | Must |

### FR-04: Tools System
| Item | Description | Priority |
|------|-------------|----------|
| FR-04.01 | Register tools in categorized Registry | Must |
| FR-04.02 | DevOps tools: Vercel Deploy, Docker Build/Run, Env Manager | Must |
| FR-04.03 | Project Intelligence tools: AutoDebugger, CodeReviewer, ProjectMonitor, Scaffold, Analyzer, DependencyManager, Refactor, DeploymentBuilder | Must |
| FR-04.04 | GitHub tools: CreateRepo, Clone, Push, Pull, ReadFile, WriteFile, CreateBranch | Should |
| FR-04.05 | Supabase tools: CreateProject, CreateTable, InsertData, Query, Auth, Storage | Should |
| FR-04.06 | Firebase tools: Init, Auth, Firestore Read/Write, Deploy | Should |
| FR-04.07 | System tools: shell, files | Must |

### FR-05: Task Management
| Item | Description | Priority |
|------|-------------|----------|
| FR-05.01 | Create task and track its status (pending → running → complete/error) | Must |
| FR-05.02 | Query task status | Must |
| FR-05.03 | Stream task progress via SSE | Must |
| FR-05.04 | Automatic cleanup of old tasks | Should |

### FR-06: Memory & Context
| Item | Description | Priority |
|------|-------------|----------|
| FR-06.01 | Build conversation context with maximum message and length limits | Must |
| FR-06.02 | Save and retrieve past conversations | Must |
| FR-06.03 | Long-term Memory | Could |
| FR-06.04 | Clean noisy text before sending to LLM | Must |

### FR-07: Web UI
| Item | Description | Priority |
|------|-------------|----------|
| FR-07.01 | Interactive chat interface with Glass Morphism design | Must |
| FR-07.02 | Support Arabic and English (RTL/LTR) | Must |
| FR-07.03 | Support dark and light mode | Must |
| FR-07.04 | Settings panel (API keys, provider, model) | Must |
| FR-07.05 | View execution log and tasks | Must |
| FR-07.06 | View and search tools library | Should |
| FR-07.07 | Display agent status (Online/Busy/Idle) | Should |
| FR-07.08 | Desktop View with Vision Agent | Won't (MVP) |

### FR-08: Telegram Integration
| Item | Description | Priority |
|------|-------------|----------|
| FR-08.01 | Telegram bot receives and sends messages | Must |
| FR-08.02 | Authorize users via /start | Must |
| FR-08.03 | Commands: /chat, /status, /help | Must |
| FR-08.04 | Automatic notifications on task completion | Should |

### FR-09: System Tray / Monitor
| Item | Description | Priority |
|------|-------------|----------|
| FR-09.01 | Monitor server status (macOS via rumps) | Should |
| FR-09.02 | Restart server | Should |
| FR-09.03 | Status notifications | Could |
| FR-09.04 | Cross-platform alternative for Windows (pystray) | Should |
| FR-09.05 | Android: Notifications via Telegram Bot | Should |

### FR-10: Security & Authentication
| Item | Description | Priority |
|------|-------------|----------|
| FR-10.01 | Basic authentication (username/password hash) | Must |
| FR-10.02 | Protect API keys (do not display in UI) | Must |
| FR-10.03 | Permission system for dangerous tools | Should |
| FR-10.04 | Encrypt sensitive data in settings files | Should |

---

## 3. Non-Functional Requirements

| Item | Description | Measurable Criterion |
|------|-------------|---------------------|
| NFR-01 | Performance | API response time ≤ 300ms under 100 concurrent requests |
| NFR-02 | Availability | Uptime ≥ 99.5% monthly |
| NFR-03 | Scalability | Support up to 1000 concurrent users in second release |
| NFR-04 | Security | No API keys exposed in code; use .env |
| NFR-04b | Compliance | GDPR/SOC2: data encryption, right to erasure, consent, audit logs |
| NFR-07 | Compatibility | Python 3.11+; macOS, Windows, Android (web-responsive) |
| NFR-09 | Privacy | Encrypted data, right to erasure, consent management (GDPR) |
| NFR-10 | Monitoring | Visible execution log + notifications |

---

## 4. Current vs Required Analysis

### What Exists and Works:
| Component | Status | Notes |
|-----------|--------|-------|
| FastAPI Server | ✅ Working | main.py + routers/chat.py |
| Web UI | ✅ Exists | templates/index.html (professional design) |
| i18n (Arabic/English) | ✅ Exists | i18n.py |
| Task Management (TaskManager) | ⚠️ Partial | Works locally but without real SSE |
| Context Building (ContextBuilder) | ✅ Working | With message and length limits |
| DevOps Tools | ✅ Exists | devops_tools.py |
| Project Intelligence Tools | ✅ Exists | project_tools.py (1409 lines) |
| GitHub Tools | ✅ Exists | github_tools.py |
| Supabase Tools | ✅ Exists | supabase_tools.py |
| Firebase Tools | ✅ Exists | firebase_tools.py |
| Telegram Bot | ✅ Exists | telegram_bot.py |
| System Tray | ✅ Exists | tray.py (macOS) |
| Settings | ✅ Exists | .emo_settings.json |

### What Exists But **Does Not Actually Work** (Stubs/Mock):
| Component | Problem | Impact |
|-----------|---------|--------|
| Brain | Returns user text as-is without LLM | System does not generate intelligent responses |
| Agent | Only calls Brain.mock | Agents do not execute real tasks |
| Memory | Empty list with no implementation | No long-term memory |
| Tools Registry | Classifications only without real binding | Tools not connected to agents |
| SSE Stream | Not implemented in chat.py | Live streaming does not work |
| Authentication | auth_enabled=false | No interface protection |

### What is **Completely Missing**:
| Component | Description |
|-----------|-------------|
| `.env` file | API keys stored in `.emo_settings.json` as plain text — security risk |
| Dockerfile | No Docker file for deployment |
| CI/CD Pipeline | No GitHub Actions or any pipeline |
| Tests | No test files |
| API Documentation | No custom OpenAPI/Swagger |
| Database | Everything in-memory or local JSON |

---

## 5. Explicit Assumptions

| # | Assumption | Verification Method |
|---|------------|---------------------|
| A-01 | Project targets macOS + Windows + Android | ✅ Confirmed by stakeholder |
| A-02 | OpenRouter is the primary LLM provider | Present in settings |
| A-03 | End user is a software developer needing DevOps tools | Inferred from existing tools |
| A-04 | System runs locally (Local-first) in MVP stage | Inferred from current architecture |
| A-05 | Python 3.14 is the version used | Present in venv/__pycache__ |
| A-06 | Project is open source and available to all | ✅ Confirmed by stakeholder |
| A-07 | Models run via API or locally (Ollama) | ✅ Confirmed by stakeholder |
| A-08 | API keys are user responsibility (free/paid) | ✅ Confirmed by stakeholder |
| A-09 | No preferred database — SQLite by default | ✅ Confirmed by stakeholder |
| A-07 | Expected users in MVP: 1-10 | **Missing information** — needs confirmation |
| A-08 | Monthly budget for API Keys: unspecified | **Missing information** — needs confirmation |

---

## 6. Constraints

| # | Constraint | Impact |
|---|------------|--------|
| C-01 | API keys in unencrypted JSON file | High security risk — must move to .env |
| C-02 | No real database | Limited scalability and sharing — SQLite as interim solution |
| C-03 | Processing in regular threads (not async) | Limited concurrency handling |
| C-04 | No test system | Quality assurance difficulty |
| C-05 | No Docker | Difficulty deploying in multiple environments |
| C-06 | tray.py works on macOS only (rumps) | Must be replaced with cross-platform (system-tray or web-based) |
| C-07 | Android needs responsive interface or app | web-responsive as initial MVP solution |
| C-08 | GDPR/SOC2 requires encryption + right to erasure + consent | Adds security and legal complexity |

---

## 7. Feature Priorities (MoSCoW)

### Must Have (MVP cannot work without):
1. Connect Brain to real LLM model (OpenRouter/Groq API)
2. Support local models via Ollama
3. Implement SSE for live streaming
4. Enable basic authentication
5. Move API keys to `.env`
6. Implement Task Manager with SSE
7. Actually connect tools to agents
8. Dockerfile for deployment
9. Open source license (MIT/Apache 2.0)
10. Platform support: macOS + Windows + Android (web-responsive)
11. Integrated Telegram Bot
12. GDPR/SOC2 compliance (data encryption, right to erasure, consent)

### Should Have (Important but can be deferred a week):
1. Integrated Telegram Bot
2. Tool permission system
3. Basic unit tests
4. GitHub Actions CI/CD
5. Performance monitoring and optimization

### Could Have (Additional enhancements):
1. Long-term memory (Vector DB)
2. Custom provider support
3. Vision Agent
4. Advanced notification system
5. Custom agents

### Won't Have (In MVP):
1. Full Desktop View
2. Multi-tenant system
3. Admin dashboard
4. Bidirectional WebSocket support
5. Billing/usage tracking system

---

## 8. Missing Information — Needs Stakeholder Confirmation

| # | Information | Impact | Default Value | Status |
|---|-------------|--------|---------------|--------|
| M-01 | Is the project open source or private? | Determines license and documentation level | **Open source — available to all** | ✅ Confirmed |
| M-02 | Number of target users in MVP | Determines scalability requirements | **3 users in initial phase** | ✅ Confirmed |
| M-03 | Monthly budget for API Keys | Determines model selection | **User dependent — free or paid** | ✅ Confirmed |
| M-04 | Target platforms | Determines tray.py and alternative | **macOS + Windows + Android** | ✅ Confirmed |
| M-05 | Is there a preferred database? | Determines DB choice | **No preference — SQLite by default** | ✅ Confirmed |
| M-06 | Is Telegram Bot required in MVP? | Determines priority | **Absolutely — Must** | ✅ Confirmed |
| M-07 | Which specific models are required? | Determines settings | **Ollama for local + OpenRouter/Groq/Gemini for API** | ✅ Confirmed |
| M-08 | Are there compliance requirements (GDPR, SOC2)? | Determines security requirements | **Yes — must comply** | ✅ Confirmed |
| M-09 | Who is the final decision maker? | Determines approval chain | ✅ **You (the stakeholder)** | ✅ Confirmed |
| M-10 | Is there a specific deadline for MVP launch? | Determines timeline | **Task-driven** | ✅ Confirmed |

---

## 9. Initial Risks with Mitigation

| # | Risk | Probability | Impact | Mitigation |
|---|------|-------------|--------|------------|
| R-01 | API key leakage (currently in JSON) | High | Critical | Immediate move to .env + add .env to .gitignore |
| R-02 | External LLM model instability | Medium | High | Support multiple providers + fallback + local Ollama |
| R-03 | Performance under load | Medium | Medium | Load tests + async optimization |
| R-04 | Current code complexity (1409 lines in one file) | High | Medium | Gradual restructuring |
| R-05 | Python 3.14 incompatibility with some libraries | Low | Medium | Early compatibility testing |
| R-06 | Loss of conversation data (local JSON) | Medium | High | Add SQLite as database |
| R-07 | GDPR/SOC2 non-compliance | Medium | Critical | Data encryption + right to erasure + consent management + audit logs |
| R-08 | Complexity of supporting 3 platforms (macOS/Windows/Android) | High | High | web-responsive as initial MVP solution + Electron for desktop later |

---

## 10. Acceptance Criteria — Templates

### AC-01: Request Routing to ML Model
```json
{
  "feature": "Route requests to appropriate ML model",
  "priority": "Must",
  "acceptance_criteria": [
    "Route text requests to 'NLP-v1' model when request size < 1k tokens",
    "Routing time ≤ 50ms",
    "On primary provider failure, switch to alternative provider within 200ms"
  ]
}
```

### AC-02: Live Progress Streaming
```json
{
  "feature": "Live task progress streaming via SSE",
  "priority": "Must",
  "acceptance_criteria": [
    "Client receives 'step_start', 'step_complete', 'result', 'error' events",
    "Latency between event and receipt ≤ 100ms",
    "Auto-reconnection on connection loss within 3 seconds"
  ]
}
```

### AC-03: Authentication
```json
{
  "feature": "User interface authentication",
  "priority": "Must",
  "acceptance_criteria": [
    "Login request with username + password",
    "Return token valid for 24 hours",
    "Reject requests without token with 401 response",
    "Encrypt password with bcrypt or equivalent"
  ]
}
```

---

## 11. KPIs for Initial Phase

| Indicator | Target | Measurement Method |
|-----------|--------|--------------------|
| MVP development time | ≤ 8 weeks | Git commit tracking |
| Critical test pass rate | ≥ 95% | pytest output |
| Average API response time | ≤ 300ms (100 concurrent) | Apache Bench / k6 |
| Unit test coverage | ≥ 60% | pytest-cov |
| Number of critical production errors | 0 | Sentry/logs |
| User satisfaction (subjective) | ≥ 4/5 | Survey |

---

## 12. JSON Output — Core Features and Interfaces

### 12.1 Core Features (JSON)

```json
{
  "document": "EMO AI Core Features",
  "version": "1.0.0",
  "date": "2026-05-17",
  "features": [
    {
      "id": "FR-01",
      "name": "Chat & Conversations",
      "priority": "Must",
      "status": "partial",
      "endpoints": ["POST /api/chat", "GET /api/conversations", "POST /api/conversations", "POST /api/conversations/{id}/activate"]
    },
    {
      "id": "FR-02",
      "name": "Multi-Agent System",
      "priority": "Must",
      "status": "stub",
      "agents": ["planner", "coder", "writer", "researcher"]
    },
    {
      "id": "FR-03",
      "name": "LLM Model Integration",
      "priority": "Must",
      "status": "stub",
      "providers": ["openrouter", "groq", "gemini"]
    },
    {
      "id": "FR-04",
      "name": "Tools System",
      "priority": "Must",
      "status": "exists-not-connected",
      "categories": ["DevOps", "Project Intelligence", "GitHub", "Supabase", "Firebase", "System"]
    },
    {
      "id": "FR-05",
      "name": "Task Management",
      "priority": "Must",
      "status": "partial",
      "states": ["pending", "running", "complete", "error"]
    },
    {
      "id": "FR-06",
      "name": "Memory & Context",
      "priority": "Must",
      "status": "partial"
    },
    {
      "id": "FR-07",
      "name": "Web UI",
      "priority": "Must",
      "status": "exists",
      "languages": ["en", "ar"],
      "themes": ["dark", "light"]
    },
    {
      "id": "FR-10",
      "name": "Security & Authentication",
      "priority": "Must",
      "status": "disabled"
    }
  ]
}
```

### 12.2 Core API Interfaces (JSON)

```json
{
  "api_spec": "EMO AI Orchestrator API v1",
  "base_url": "http://localhost:8080",
  "endpoints": {
    "GET /": {
      "description": "Server status",
      "response": {
        "name": "string",
        "version": "string",
        "status": "string"
      }
    },
    "POST /api/chat": {
      "description": "Send a message and start a task",
      "input": {
        "message": {"type": "string", "required": true, "description": "Message text"},
        "conversation_id": {"type": "string", "required": false, "description": "Conversation ID"},
        "file_name": {"type": "string", "required": false},
        "file_type": {"type": "string", "required": false},
        "base64": {"type": "string", "required": false}
      },
      "response": {
        "task_id": {"type": "string", "description": "Task ID"},
        "status": {"type": "string", "enum": ["started"]}
      }
    },
    "GET /api/stream/{task_id}": {
      "description": "Live task progress streaming (SSE)",
      "events": [
        {"type": "step_start", "data": {"step": "string", "agent": "string", "tool": "string"}},
        {"type": "step_complete", "data": {"step": "string", "result": "string"}},
        {"type": "result", "data": {"content": "string"}},
        {"type": "error", "data": {"message": "string"}}
      ]
    },
    "GET /api/tasks": {
      "description": "Task list",
      "query_params": {"limit": {"type": "integer", "default": 10}},
      "response": {
        "tasks": [{"id": "string", "status": "string", "message": "string", "created_at": "string"}]
      }
    },
    "GET /api/conversations": {
      "description": "Conversation list",
      "response": {
        "conversations": [{"id": "string", "name": "string", "message_count": "integer"}],
        "active": "string"
      }
    },
    "POST /api/conversations": {
      "description": "Create a new conversation",
      "input": {"name": {"type": "string", "required": true}},
      "response": {"id": "string", "name": "string"}
    },
    "POST /api/settings": {
      "description": "Update a setting",
      "input": {"key": {"type": "string"}, "value": {"type": "string"}},
      "response": {"status": "string", "enum": ["saved"]}
    },
    "GET /api/status": {
      "description": "LLM connection status",
      "response": {
        "connected": "boolean",
        "provider": "string",
        "model": "string",
        "latency_ms": "integer"
      }
    },
    "GET /api/history": {
      "description": "Active conversation history",
      "response": {
        "messages": [{"role": "string", "content": "string", "file_data": "object?"}]
      }
    },
    "GET /api/global_stream": {
      "description": "Global event stream (SSE)",
      "events": [
        {"type": "task_update", "data": {"task_id": "string", "status": "string"}},
        {"type": "play_sound", "data": {"message": "string"}}
      ]
    }
  }
}
```

### 12.3 Data Model (JSON)

```json
{
  "data_models": {
    "Task": {
      "id": "string (UUID short)",
      "message": "string",
      "status": "enum[pending, running, complete, error]",
      "result": "string?",
      "error": "string?",
      "created_at": "ISO8601",
      "updated_at": "ISO8601?",
      "conversation_id": "string?"
    },
    "Conversation": {
      "id": "string (UUID)",
      "name": "string",
      "messages": [
        {
          "role": "enum[user, assistant, system]",
          "content": "string",
          "timestamp": "ISO8601",
          "file_data": {
            "name": "string",
            "type": "string",
            "size": "integer",
            "base64": "string"
          }?
        }
      ],
      "created_at": "ISO8601"
    },
    "Settings": {
      "lang": "enum[en, ar]",
      "theme": "enum[dark, light]",
      "provider": "string",
      "model": "string",
      "openrouter_key": "string (secret)",
      "groq_key": "string (secret)",
      "gemini_key": "string (secret)",
      "system_instructions": "string",
      "project_dir": "string",
      "auth_enabled": "boolean",
      "auth_username": "string",
      "auth_password_hash": "string",
      "telegram_token": "string (secret)",
      "telegram_enabled": "boolean"
    },
    "Agent": {
      "name": "string",
      "status": "enum[idle, busy, error]",
      "brain": "Brain instance",
      "current_task": "string?"
    }
  }
}
```

---

## 13. Implementation Steps Within 24 Hours (Immediately Actionable)

### Step 1: Secure API Keys (Immediate — 30 minutes)

```bash
# 1. Create .env file
cat > /Users/AI\ Workspace/Emo-AI/.env << 'EOF'
OPENROUTER_API_KEY=sk-or-placeholder-rotated
GROQ_API_KEY=gsk-placeholder-rotated
GEMINI_API_KEY=gemini-placeholder-rotated
TELEGRAM_TOKEN=telegram-token-placeholder-rotated
SUPABASE_SERVICE_KEY=
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=
GITHUB_TOKEN=
FIREBASE_API_KEY=
FIREBASE_PROJECT_ID=
EOF

# 2. Ensure .env is in .gitignore
echo ".env" >> /Users/AI\ Workspace/Emo-AI/.gitignore

# 3. Remove keys from .emo_settings.json (replace with "")
# Done manually or via script
```

### Step 2: Install Requirements and Run Server (30 minutes)

```bash
cd /Users/AI\ Workspace/Emo-AI
source venv/bin/activate  # Or: python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python main.py
# Verify: curl http://localhost:8080/
```

### Step 3: Create Project Configuration File (JSON)

```bash
cat > /Users/AI\ Workspace/Emo-AI/emo_config.json << 'EOF'
{
  "project_name": "Emo AI Orchestrator",
  "version": "4.0.0",
  "python_version": "3.14",
  "framework": "fastapi",
  "mvp_deadline": "2026-07-12",
  "target_platforms": ["macOS"],
  "llm_providers": ["openrouter", "groq", "gemini"],
  "auth_enabled": false,
  "database": "json-file",
  "stubs_to_fix": ["brain.py", "agent.py", "memory.py", "tools.py", "sse_stream"]
}
EOF
```

### Step 4: Create Tracking Log

```bash
cat > /Users/AI\ Workspace/Emo-AI/docs/PROGRESS.md << 'EOF'
# Progress Log — EMO AI Orchestrator

## Week 1 (2026-05-17 to 2026-05-24)
- [x] Requirements Understanding Document (v1.0-DRAFT)
- [ ] Secure API keys
- [ ] Connect Brain to OpenRouter API
- [ ] Implement SSE stream
- [ ] Enable basic authentication

## Decisions Required from Stakeholder:
1. M-01: Is the project open source or private?
2. M-02: Number of target users?
3. M-03: Monthly budget for API Keys?
4. M-09: Who is the final decision maker?
5. M-10: Is there a specific deadline?
EOF
```

---

## 14. Recommendations Summary

### Confirmed Stakeholder Decisions (10/10 — Complete):
| Decision | Status |
|----------|--------|
| M-01: Open source | ✅ Confirmed |
| M-02: 3 users in initial phase | ✅ Confirmed |
| M-03: API keys user dependent (free/paid) | ✅ Confirmed |
| M-04: macOS + Windows + Android | ✅ Confirmed |
| M-05: No preferred database — SQLite by default | ✅ Confirmed |
| M-06: Telegram Bot definitely required | ✅ Confirmed |
| M-07: Ollama for local + API for cloud | ✅ Confirmed |
| M-08: Yes — GDPR/SOC2 compliance requirements | ✅ Confirmed |
| M-09: Stakeholder = you | ✅ Confirmed |
| M-10: Task-driven deadline | ✅ Confirmed |

| # | Recommendation | Priority | Effort |
|---|---------------|----------|--------|
| 1 | Move API keys from `.emo_settings.json` to `.env` | Critical | 30 minutes |
| 2 | Connect `brain.py` to real OpenRouter API | Critical | 2-3 hours |
| 3 | Implement SSE stream in `routers/chat.py` | Critical | 3-4 hours |
| 4 | Enable basic authentication | High | 4-6 hours |
| 5 | Create Dockerfile | High | 2 hours |
| 6 | Add basic unit tests | High | 1 day |
| 7 | Actually connect tools to agents | Medium | 2-3 days |
| 8 | Add SQLite as database | Medium | 1-2 days |
| 9 | Create CI/CD pipeline | Medium | 1 day |
| 10 | Restructure `project_tools.py` | Low | 2-3 days |

---

**End of Document — Version 1.0.0-DRAFT**

*This document is a draft and requires review and approval from the stakeholder before moving to the exploration and design phase.*

*For approval or modification: Review the "Missing Information" section (Table 8) and provide clear answers.*
