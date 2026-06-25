# Exploration Report — EMO AI Orchestrator

| Item          | Value                                        |
|---------------|----------------------------------------------|
| **Date**      | 2026-05-17                                   |
| **Author**    | opencode AI Agent                            |
| **Status**    | Final — Awaiting approval                     |
| **Version**   | 1.0.0                                        |
| **Phase**     | Exploration                                  |

---

## 1. Market and Competitor Analysis

### 1.1 Product Category

EMO AI Orchestrator falls under **AI Agent Orchestration Platforms**.

### 1.2 Direct Competitors

| Competitor | Description | Strengths | Weaknesses | EMO AI Advantage |
|------------|-------------|-----------|------------|------------------|
| **OpenWebUI** | Web interface for Ollama | Open source, Ollama support | No multi-agent | Multiple agents + DevOps tools |
| **Dify** | AI application building platform | Drag-and-drop interface, cloud | Complex, not local-first | Local-first + simple |
| **LangChain** | AI chain framework | Flexible, large community | Requires heavy coding | Ready interface + built-in tools |
| **CrewAI** | Agent team orchestration | Good multi-agent | No web UI | Complete web UI + tools |
| **AutoGen (Microsoft)** | Multi-agent | Strong academic research | Complex setup | Easier to use |
| **Continue.dev** | AI code assistant | Integrated in IDE | Code-only specialization | Broader (DevOps + Projects + Conversations) |

### 1.3 Market Gap

| Gap | How EMO AI Fills It |
|-----|---------------------|
| No solution combining multi-agent + DevOps tools + Arabic interface | ✅ EMO AI combines all |
| Most solutions are cloud-only | ✅ EMO AI supports local (Ollama) and cloud |
| No open source solution with professional Arabic interface | ✅ EMO AI is open source + Arabic |
| Current solutions are complex for beginners | ✅ EMO AI is simple with easy interface |

### 1.4 Target Audience

| Segment | Approximate Size | Needs |
|---------|------------------|-------|
| Independent developers | Millions worldwide | DevOps tools + code generation + research |
| Small teams (3-10 people) | Hundreds of thousands | Task coordination + smart conversations |
| Students and educators | Millions | Arabic interface + free local models |
| AI enthusiasts | Growing | Local Ollama + easy interface |

---

## 2. Suitable Technologies

### 2.1 Current Technologies (Evaluated)

| Technology | Rating | Reason | Alternative |
|------------|--------|--------|-------------|
| **FastAPI** | ✅ Excellent | Fast, async, auto-docs, suitable for API | No replacement needed |
| **Uvicorn** | ✅ Excellent | Fast ASGI server | No replacement needed |
| **Pydantic** | ✅ Excellent | Built-in validation with FastAPI | No replacement needed |
| **TailwindCSS (CDN)** | ⚠️ Acceptable | Easy but CDN depends on internet | Local copy in production |
| **JSON files for data** | ⚠️ Limited | Simple but does not scale | SQLite for MVP |
| **Regular Threads** | ⚠️ Limited | Blocking in async app | asyncio + background tasks |
| **rumps (macOS only)** | ⚠️ Limited | Does not work on Windows | pystray (cross-platform) |

### 2.2 Proposed Technologies to Add

| Technology | Usage | Reason | Priority |
|------------|-------|--------|----------|
| **openai SDK** | Connect to LLM | Compatible with OpenRouter/Groq/Ollama | 🔴 Critical |
| **httpx** | Async HTTP client for Ollama | Async-native | 🔴 Critical |
| **aiosqlite** | Async SQLite database | Simple, local, no server needed | 🔴 Critical |
| **PyJWT** | JWT authentication | Industry standard | 🔴 Critical |
| **bcrypt** | Password encryption | Secure and trusted | 🔴 Critical |
| **python-telegram-bot** | Telegram Bot | Official library | 🟡 High |
| **pystray** | Cross-platform System Tray | Works on macOS + Windows | 🟡 High |
| **cryptography (Fernet)** | Data encryption | For GDPR/SOC2 | 🟡 High |
| **pytest + pytest-cov** | Tests | Industry standard | 🟡 High |
| **SSE-starlette** | Server-Sent Events | Dedicated SSE library for FastAPI | 🔴 Critical |

### 2.3 Deferred Technologies (Post-MVP)

| Technology | Usage | Why Deferred |
|------------|-------|--------------|
| **ChromaDB / Qdrant** | Vector DB for long-term memory | Not required in MVP |
| **Redis** | Cache + message queue | 3 users do not need it |
| **PostgreSQL** | Production database | SQLite sufficient for MVP |
| **Docker Compose** | Multi-service deployment | Dockerfile sufficient initially |
| **React/Vue** | Separate frontend | Current interface is sufficient |
| **WebSocket** | Bidirectional connection | SSE sufficient for streaming |

---

## 3. Proposed System Components

### 3.1 Current Architecture (As-Is)

```
┌─────────────────────────────────────────────────┐
│                  Web Browser                     │
│  (index.html — TailwindCSS + Vanilla JS)        │
└────────────────────┬────────────────────────────┘
                     │ HTTP
┌────────────────────▼────────────────────────────┐
│              FastAPI Server (main.py)            │
│                                                  │
│  ┌──────────────┐    ┌──────────────────────┐   │
│  │ chat_router  │    │  Static Files        │   │
│  │ (POST /chat) │    │  (templates/)        │   │
│  └──────┬───────┘    └──────────────────────┘   │
│         │                                        │
│  ┌──────▼──────────────────────────────────┐    │
│  │           AppState (state.py)           │    │
│  │  ┌─────┐ ┌──────┐ ┌─────┐ ┌─────────┐  │    │
│  │  │Brain│ │Tools │ │Memory│ │Agents   │  │    │
│  │  │STUB │ │STUB  │ │STUB  │ │STUBs    │  │    │
│  │  └─────┘ └──────┘ └─────┘ └─────────┘  │    │
│  │  ┌──────────────────────────────────┐   │    │
│  │  │     TaskManager (working)        │   │    │
│  │  └──────────────────────────────────┘   │    │
│  └─────────────────────────────────────────┘    │
└─────────────────────────────────────────────────┘

┌──────────────────┐  ┌──────────────────────────┐
│  Telegram Bot    │  │  System Tray (macOS)     │
│  (standalone)    │  │  tray.py (standalone)    │
└──────────────────┘  └──────────────────────────┘

┌─────────────────────────────────────────────────┐
│  Tools (standalone files, not connected):       │
│  project_tools.py | devops_tools.py             │
│  supabase_tools.py | firebase_tools.py          │
│  github_tools.py                                │
└─────────────────────────────────────────────────┘
```

### 3.2 Proposed Architecture (To-Be — MVP)

```
┌──────────────────────────────────────────────────────────┐
│                     Clients                               │
│  ┌────────────┐  ┌────────────┐  ┌──────────────────┐    │
│  │ Web Browser│  │ Telegram   │  │ System Tray      │    │
│  │ (responsive│  │ Bot        │  │ (pystray)        │    │
│  │  macOS/Win │  │            │  │ macOS + Windows  │    │
│  │  /Android) │  │            │  │                  │    │
│  └─────┬──────┘  └─────┬──────┘  └────────┬─────────┘    │
│        │               │                   │              │
└────────┼───────────────┼───────────────────┼──────────────┘
         │               │                   │
         ▼               ▼                   ▼
┌──────────────────────────────────────────────────────────┐
│              FastAPI Server (main.py)                     │
│                                                          │
│  ┌────────────────────────────────────────────────────┐  │
│  │              Middleware Layer                       │  │
│  │  • CORS         • Auth (JWT)       • Rate Limit    │  │
│  └────────────────────────┬───────────────────────────┘  │
│                           │                              │
│  ┌────────────────────────▼───────────────────────────┐  │
│  │              Router Layer                           │  │
│  │  ┌──────┐ ┌────────┐ ┌────────┐ ┌──────┐ ┌──────┐  │  │
│  │  │chat  │ │auth    │ │settings│ │tasks │ │stream│  │  │
│  │  │router│ │router  │ │router  │ │router│ │(SSE) │  │  │
│  │  └──────┘ └────────┘ └────────┘ └──────┘ └──────┘  │  │
│  └────────────────────────┬───────────────────────────┘  │
│                           │                              │
│  ┌────────────────────────▼───────────────────────────┐  │
│  │              Orchestrator Layer                     │  │
│  │  ┌──────────────────────────────────────────────┐  │  │
│  │  │  Task Dispatcher                             │  │  │
│  │  │  • Routes requests to appropriate agent      │  │  │
│  │  │  • Manages task lifecycle                    │  │  │
│  │  │  • Streams progress via SSE                  │  │  │
│  │  └──────────────────────────────────────────────┘  │  │
│  │                                                    │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐          │  │
│  │  │ Planner  │ │  Coder   │ │  Writer  │          │  │
│  │  │  Agent   │ │  Agent   │ │  Agent   │          │  │
│  │  └────┬─────┘ └────┬─────┘ └────┬─────┘          │  │
│  │       │            │            │                 │  │
│  │  ┌────▼────────────▼────────────▼─────┐           │  │
│  │  │         Brain (LLM Interface)       │          │  │
│  │  │  ┌────────┐ ┌──────┐ ┌────┐ ┌────┐ │          │  │
│  │  │  │OpenRtr │ │ Groq │ │Gem │ │Oll │ │          │  │
│  │  │  │ (API)  │ │(API) │ │(API)│ │ama │ │          │  │
│  │  │  └────────┘ └──────┘ └────┘ └────┘ │          │  │
│  │  └────────────────────────────────────┘           │  │
│  │                                                    │  │
│  │  ┌──────────────────────────────────────────────┐  │  │
│  │  │         Tool Executor                         │  │  │
│  │  │  • DevOps  • Projects  • GitHub  • Cloud     │  │  │
│  │  └──────────────────────────────────────────────┘  │  │
│  └────────────────────────────────────────────────────┘  │
│                           │                              │
│  ┌────────────────────────▼───────────────────────────┐  │
│  │              Data Layer                             │  │
│  │  ┌────────────┐  ┌────────────┐  ┌──────────────┐  │  │
│  │  │  SQLite    │  │  JSON      │  │  .env        │  │  │
│  │  │  (tasks,   │  │  (settings,│  │  (secrets)   │  │  │
│  │  │  convs)    │  │  history)  │  │              │  │  │
│  │  └────────────┘  └────────────┘  └──────────────┘  │  │
│  └────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────┘
```

### 3.3 Comparison: Current vs Proposed

| Component | Current | Proposed (MVP) | Change |
|-----------|---------|----------------|--------|
| Brain | stub (echo) | OpenRouter/Groq/Gemini/Ollama | 🔴 Full implementation |
| Agents | 3 stubs | 4 agents connected to LLM | 🔴 Add Coder + connect |
| Tools | Isolated files | Tool Executor connected to agents | 🔴 Connect |
| TaskManager | In-memory dict | SQLite + SSE | 🔴 Add DB + SSE |
| Auth | Disabled | JWT + bcrypt | 🔴 Implement |
| Data | JSON only | SQLite + JSON | 🟡 Add SQLite |
| Telegram | standalone | Integrated with orchestrator | 🟡 Integrate |
| System Tray | macOS only | pystray (cross-platform) | 🟡 Replace rumps |
| SSE | Not present | SSE-starlette | 🔴 Implement |

---

## 4. Initial Risks with Probabilities and Impacts

### 4.1 Technical Risks

| # | Risk | Probability | Impact | Score | Mitigation |
|---|------|-------------|--------|-------|------------|
| R-01 | API key leakage (currently in JSON) | High (90%) | Critical | 🔴 9.0 | Immediate move to .env + .gitignore |
| R-02 | External API instability (OpenRouter/Groq) | Medium (40%) | High | 🟡 6.0 | Fallback to local Ollama |
| R-03 | Ollama requires high resources (RAM/CPU) | High (70%) | Medium | 🟡 5.6 | Recommend 8GB RAM minimum |
| R-04 | SQLite cannot handle high concurrent writes | Medium (30%) | Medium | 🟢 3.0 | Only 3 users — sufficient |
| R-05 | Complexity of connecting tools to agents | High (60%) | High | 🟡 7.2 | Design simple Tool Executor first |
| R-06 | SSE does not work with current threading | Medium (50%) | High | 🟡 6.0 | Use SSE-starlette + asyncio |
| R-07 | Python 3.14 incompatibility with libraries | Low (15%) | Medium | 🟢 2.4 | Early testing + fallback to 3.11 |

### 4.2 Security Risks

| # | Risk | Probability | Impact | Score | Mitigation |
|---|------|-------------|--------|-------|------------|
| R-08 | GDPR non-compliance | Medium (40%) | Critical | 🔴 8.0 | Encryption + right to erasure + consent |
| R-09 | SOC2 non-compliance | Medium (35%) | Critical | 🔴 7.0 | Audit logs + access control |
| R-10 | Attack on endpoint without auth | High (60%) | High | 🔴 7.8 | JWT middleware on every endpoint |
| R-11 | SQL injection (when adding SQLite) | Low (10%) | High | 🟢 3.2 | Use parameterized queries |

### 4.3 Cost Risks

| # | Risk | Probability | Impact | Score | Mitigation |
|---|------|-------------|--------|-------|------------|
| R-12 | High API Key cost | Medium (40%) | Medium | 🟡 4.0 | Support free local Ollama |
| R-13 | Cloud hosting cost | Low (20%) | Low | 🟢 2.0 | Local-first = no hosting |
| R-14 | Multi-platform maintenance cost | High (65%) | Medium | 🟡 5.2 | web-responsive first |

### 4.4 Schedule Risks

| # | Risk | Probability | Impact | Score | Mitigation |
|---|------|-------------|--------|-------|------------|
| R-15 | SSE + async implementation complexity | Medium (45%) | High | 🟡 5.4 | Use ready SSE-starlette |
| R-16 | Code restructuring takes time | High (60%) | Medium | 🟡 4.8 | Gradual implementation without breaking |
| R-17 | GDPR/SOC2 testing takes time | Medium (35%) | High | 🟡 5.6 | Use ready checklist |

---

## 5. Summary and Recommendations

### 5.1 Architectural Decision

**Principle:** KISS (Keep It Simple, Stupid) + Future scalability

**Decisions:**
1. **FastAPI** remains the core framework — excellent, no replacement needed
2. **SQLite** as MVP database — simple, local, sufficient for 3 users
3. **SSE-starlette** for live streaming — ready and reliable library
4. **openai SDK** as unified LLM interface — compatible with all providers
5. **pystray** instead of rumps — cross-platform (macOS + Windows)
6. **JWT + bcrypt** for authentication — industry standard
7. **Current UI remains** — sufficient and professional

### 5.2 Implementation Priorities

| Priority | Task | Effort |
|----------|------|--------|
| 1 | Move API keys to .env | 30 minutes |
| 2 | Fix AppState.conversations bug | 15 minutes |
| 3 | Add Tool base class | 30 minutes |
| 4 | Connect Brain to OpenRouter API | 2-3 hours |
| 5 | Connect Brain to Ollama | 2-3 hours |
| 6 | Implement SSE stream | 3-4 hours |
| 7 | Enable JWT authentication | 4-6 hours |
| 8 | Add SQLite | 1-2 days |
| 9 | Dockerfile | 2 hours |
| 10 | Unit tests | 1 day |

### 5.3 Gateway to Design Phase

Before moving to architectural design phase:
- [x] Requirements document complete (10/10 decisions)
- [x] Exploration report complete
- [ ] **Required:** Written approval from stakeholder on core technologies
- [ ] **Required:** POC proving Brain + Ollama work together

---

**End of Report — Version 1.0.0**

*Ready to move to architectural design phase after approval.*
