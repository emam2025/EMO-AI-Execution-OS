# مستند التصميم المعماري — EMO AI Orchestrator MVP

| البند          | القيمة                                        |
|----------------|-----------------------------------------------|
| **التاريخ**    | 2026-05-17                                    |
| **المؤلف**     | opencode AI Agent                             |
| **الحالة**     | مسودة — بانتظار الموافقة                      |
| **الإصدار**    | 1.0.0-DRAFT                                   |
| **المرحلة**    | التحليل والتصميم (Architecture Design)        |

---

## 1. المخطط المعماري

### 1.1 طبقات النظام

```
┌─────────────────────────────────────────────────────────────────┐
│                        طبقة العملاء (Clients)                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────┐   │
│  │ Web Browser  │  │ Telegram Bot │  │ System Tray (pystray)│   │
│  │ macOS/Win/   │  │ python-      │  │ macOS + Windows      │   │
│  │ Android      │  │ telegram-bot │  │                      │   │
│  │ (responsive) │  │              │  │                      │   │
│  └──────┬───────┘  └──────┬───────┘  └──────────┬───────────┘   │
│         │                 │                      │               │
└─────────┼─────────────────┼──────────────────────┼───────────────┘
          │                 │                      │
          ▼                 ▼                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                   طبقة الخادم (FastAPI Server)                   │
│                                                                  │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │  Middleware Stack                                          │  │
│  │  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐  │  │
│  │  │ CORS     │→ │ Auth JWT │→ │ Rate     │→ │ Logging  │  │  │
│  │  │          │  │          │  │ Limit    │  │          │  │  │
│  │  └──────────┘  └──────────┘  └──────────┘  └──────────┘  │  │
│  └───────────────────────────┬───────────────────────────────┘  │
│                              │                                  │
│  ┌───────────────────────────▼───────────────────────────────┐  │
│  │  Router Layer (Endpoints)                                  │  │
│  │  ┌──────┐ ┌──────┐ ┌──────────┐ ┌──────┐ ┌──────┐        │  │
│  │  │chat  │ │auth  │ │settings  │ │tasks │ │stream│        │  │
│  │  │      │ │      │ │          │ │      │ │(SSE) │        │  │
│  │  └──┬───┘ └──┬───┘ └────┬─────┘ └──┬───┘ └──┬───┘        │  │
│  └─────┼────────┼──────────┼───────────┼────────┼────────────┘  │
│        │        │          │           │        │               │
│  ┌─────▼────────▼──────────▼───────────▼────────▼────────────┐  │
│  │              Orchestrator Layer                            │  │
│  │                                                            │  │
│  │  ┌──────────────────────────────────────────────────────┐ │  │
│  │  │  Task Dispatcher & Orchestrator                      │ │  │
│  │  │  • يصنف الطلب (classification)                       │ │  │
│  │  │  • يختار الوكيل المناسب (routing)                    │ │  │
│  │  │  • ينفذ الأدوات المطلوبة (tool execution)            │ │  │
│  │  │  • يبث التقدم عبر SSE (streaming)                    │ │  │
│  │  └──────────────────────────────────────────────────────┘ │  │
│  │                                                            │  │
│  │  ┌───────────┐  ┌───────────┐  ┌───────────┐             │  │
│  │  │ Planner   │  │  Coder    │  │  Writer   │             │  │
│  │  │  Agent    │  │  Agent    │  │  Agent    │             │  │
│  │  └─────┬─────┘  └─────┬─────┘  └─────┬─────┘             │  │
│  │        │              │              │                     │  │
│  │  ┌─────▼──────────────▼──────────────▼─────────────┐      │  │
│  │  │           Brain (LLM Interface)                  │      │  │
│  │  │  ┌──────────┐ ┌──────┐ ┌───────┐ ┌──────────┐  │      │  │
│  │  │  │OpenRouter│ │ Groq │ │Gemini │ │  Ollama  │  │      │  │
│  │  │  │  (API)   │ │(API) │ │ (API) │ │ (Local)  │  │      │  │
│  │  │  └──────────┘ └──────┘ └───────┘ └──────────┘  │      │  │
│  │  └─────────────────────────────────────────────────┘      │  │
│  │                                                            │  │
│  │  ┌──────────────────────────────────────────────────────┐ │  │
│  │  │  Tool Executor & Registry                             │ │  │
│  │  │  ┌────────┐ ┌──────────┐ ┌──────┐ ┌────────┐        │ │  │
│  │  │  │ DevOps │ │ Projects │ │GitHub│ │ Cloud  │        │ │  │
│  │  │  │ Tools  │ │  Tools   │ │Tools │ │ Tools  │        │ │  │
│  │  │  └────────┘ └──────────┘ └──────┘ └────────┘        │ │  │
│  │  └──────────────────────────────────────────────────────┘ │  │
│  └───────────────────────────┬───────────────────────────────┘  │
│                              │                                  │
│  ┌───────────────────────────▼───────────────────────────────┐  │
│  │  Data Layer                                                │  │
│  │  ┌──────────────┐  ┌──────────────┐  ┌────────────────┐  │  │
│  │  │   SQLite     │  │   JSON Files │  │   .env         │  │  │
│  │  │  • tasks     │  │  • settings  │  │   • API keys   │  │  │
│  │  │  • convs     │  │  • history   │  │   • secrets    │  │  │
│  │  │  • users     │  │  • telegram  │  │   • config     │  │  │
│  │  │              │  │    users     │  │                │  │  │
│  │  └──────────────┘  └──────────────┘  └────────────────┘  │  │
│  └───────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### 1.2 تدفق البيانات (Data Flow)

```
1. المستخدم → يرسل رسالة → POST /api/chat
2. Middleware → يتحقق من JWT (إذا auth_enabled)
3. Router → يُنشئ task في SQLite (status=pending)
4. Orchestrator → يصنف الطلب:
   ├─ إذا كود/برمجة → Coder Agent
   ├─ إذا كتابة/محتوى → Writer Agent
   ├─ إذا بحث/تحليل → Researcher Agent (post-MVP)
   └─ إذا عام/تخطيط → Planner Agent
5. Agent → يستدعي Brain.ask(system, user)
6. Brain → يختار المزود (provider) ويستدعي LLM:
   ├─ API: openai.OpenAI(base_url=..., api_key=...)
   └─ Local: httpx.post(ollama_url, ...)
7. LLM → يرجع الرد
8. Orchestrator → إذا يحتاج أدوات:
   ├─ ToolExecutor.find_tool(tool_name)
   ├─ tool.run(**params)
   └─ يدمج النتيجة في الرد
9. Orchestrator → يحفظ النتيجة في SQLite (status=complete)
10. SSE → يبث النتيجة للعميل
11. العميل → يعرض الرد في الواجهة
```

---

## 2. اختيارات التكنولوجيا مع المبررات

### 2.1 القرارات المعمارية

| القرار | الاختيار | البديل المرفوض | السبب |
|--------|---------|---------------|-------|
| إطار HTTP | **FastAPI** | Flask, Django | Async-native, auto-docs, Pydantic integration |
| قاعدة بيانات | **SQLite** | PostgreSQL, MongoDB | Local-first, zero-config, كافٍ لـ 3 مستخدمين |
| مصادقة | **JWT (PyJWT)** | Session-based, OAuth2 | Stateless, cross-platform, معيار صناعي |
| تشفير كلمات المرور | **bcrypt** | argon2, hashlib | معتمد ومختبر، سهل الاستخدام |
| بث مباشر | **SSE (sse-starlette)** | WebSocket | أبسط،unidirectional كافٍ، browser support ممتاز |
| عميل LLM | **openai SDK** | requests مباشرة | متوافق مع كل المزودين (OpenRouter/Groq/Ollama) |
| عميل Ollama | **httpx** | requests | Async-native, متوافق مع FastAPI |
| System Tray | **pystray** | rumps | Cross-platform (macOS + Windows) |
| اختبارات | **pytest + pytest-cov** | unittest | أسهل، fixtures، plugins كثيرة |
| نشر | **Docker** | bare metal | reproducible, portable |

### 2.2 البدائل المؤجلة

| البديل | متى ننتقل إليه | السبب |
|--------|---------------|-------|
| PostgreSQL | عند > 100 مستخدم متزامن | SQLite لا يتحمل كتابة متزامنة عالية |
| Redis cache | عند > 50 طلب/ثانية | تحسين الأداء |
| WebSocket | عند حاجة اتصال ثنائي | SSE كافٍ حالياً |
| React/Vue SPA | عند تعقيد الواجهة | الواجهة الحالية كافية |
| Vector DB (ChromaDB) | عند حاجة ذاكرة طويلة المدى | post-MVP feature |

---

## 3. مخطط قاعدة البيانات (SQLite)

### 3.1 الجداول

```sql
-- جدول المستخدمين
CREATE TABLE users (
    id            TEXT PRIMARY KEY,       -- UUID
    username      TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,          -- bcrypt hash
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now')),
    is_active     INTEGER NOT NULL DEFAULT 1
);

-- جدول المحادثات
CREATE TABLE conversations (
    id            TEXT PRIMARY KEY,       -- UUID
    user_id       TEXT REFERENCES users(id),
    name          TEXT NOT NULL DEFAULT 'محادثة جديدة',
    is_active     INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

-- جدول الرسائل
CREATE TABLE messages (
    id            TEXT PRIMARY KEY,       -- UUID
    conversation_id TEXT REFERENCES conversations(id) ON DELETE CASCADE,
    role          TEXT NOT NULL CHECK (role IN ('user', 'assistant', 'system')),
    content       TEXT NOT NULL,
    file_name     TEXT,
    file_type     TEXT,
    file_size     INTEGER,
    file_base64   TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

-- جدول المهام
CREATE TABLE tasks (
    id            TEXT PRIMARY KEY,       -- 8-char short UUID
    conversation_id TEXT REFERENCES conversations(id),
    message       TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'pending'
                  CHECK (status IN ('pending', 'running', 'complete', 'error')),
    result        TEXT,
    error         TEXT,
    agent         TEXT,                   -- planner, coder, writer
    tool_used     TEXT,                   -- اسم الأداة إن وُجدت
    progress      INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

-- جدول سجل التدقيق (Audit Log — لـ GDPR/SOC2)
CREATE TABLE audit_logs (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id       TEXT REFERENCES users(id),
    action        TEXT NOT NULL,          -- login, chat, settings_change, delete
    resource      TEXT,                   -- conversation_id, task_id, etc.
    details       TEXT,                   -- JSON details
    ip_address    TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

-- فهارس
CREATE INDEX idx_messages_conversation ON messages(conversation_id);
CREATE INDEX idx_tasks_status ON tasks(status);
CREATE INDEX idx_tasks_created ON tasks(created_at);
CREATE INDEX idx_audit_user ON audit_logs(user_id);
CREATE INDEX idx_audit_created ON audit_logs(created_at);
```

### 3.2 مخطط العلاقات (ERD)

```
users (1) ────< (N) conversations (1) ────< (N) messages
    │                                       │
    │                                       │
    └───< (N) tasks                         │
    │                                       │
    └───< (N) audit_logs                    │
```

---

## 4. واجهات API (Endpoints مع نماذج JSON)

### 4.1 المصادقة

#### `POST /api/auth/signup`
- **الوصف:** إنشاء حساب جديد
- **المدخلات:**
  ```json
  {
    "username": {"type": "string", "required": true, "min": 3, "max": 50},
    "password": {"type": "string", "required": true, "min": 8}
  }
  ```
- **الاستجابة (201):**
  ```json
  {
    "id": "uuid",
    "username": "string",
    "created_at": "2026-05-17T10:00:00Z"
  }
  ```
- **الأخطاء:** 409 (username موجود), 422 (validation)

#### `POST /api/auth/login`
- **الوصف:** تسجيل دخول
- **المدخلات:**
  ```json
  {
    "username": {"type": "string", "required": true},
    "password": {"type": "string", "required": true}
  }
  ```
- **الاستجابة (200):**
  ```json
  {
    "access_token": "jwt-token-string",
    "token_type": "bearer",
    "expires_in": 86400
  }
  ```
- **الأخطاء:** 401 (بيانات خاطئة)

#### `GET /api/auth/verify`
- **الوصف:** التحقق من token
- **الهيدر:** `Authorization: Bearer <token>`
- **الاستجابة (200):**
  ```json
  {
    "valid": true,
    "user_id": "uuid",
    "username": "string"
  }
  ```

### 4.2 المحادثات

#### `POST /api/chat`
- **الوصف:** إرسال رسالة وبدء مهمة
- **المدخلات:**
  ```json
  {
    "message": "اكتب دالة Python لحساب Fibonacci",
    "conversation_id": "uuid-or-empty"
  }
  ```
- **الاستجابة (202):**
  ```json
  {
    "task_id": "a1b2c3d4",
    "status": "started"
  }
  ```

#### `GET /api/stream/{task_id}` (SSE)
- **الوصف:** بث مباشر لتقدم المهمة
- **الأحداث:**
  ```
  event: step_start
  data: {"step": "classification", "agent": "planner"}

  event: step_complete
  data: {"step": "classification", "result": "code_generation"}

  event: step_start
  data: {"step": "tool_execution", "agent": "coder", "tool": "auto_debugger"}

  event: result
  data: {"content": "إليك الدالة:\n\ndef fibonacci(n):..."}

  event: done
  data: {"task_id": "a1b2c3d4"}
  ```

#### `GET /api/conversations`
- **الاستجابة (200):**
  ```json
  {
    "conversations": [
      {"id": "uuid", "name": "محادثة تجريبية", "message_count": 12, "updated_at": "2026-05-17T10:00:00Z"}
    ],
    "active": "uuid"
  }
  ```

#### `POST /api/conversations`
- **المدخلات:** `{"name": "مشروع جديد"}`
- **الاستجابة (201):**
  ```json
  {
    "id": "uuid",
    "name": "مشروع جديد",
    "created_at": "2026-05-17T10:00:00Z"
  }
  ```

#### `POST /api/conversations/{id}/activate`
- **الاستجابة (200):** `{"status": "activated", "conversation_id": "uuid"}`

#### `DELETE /api/conversations/{id}`
- **الاستجابة (200):** `{"status": "deleted", "conversation_id": "uuid"}`
- **ملاحظة GDPR:** يحذف جميع الرسائل والسجلات المرتبطة

#### `GET /api/history`
- **الاستجابة (200):**
  ```json
  {
    "messages": [
      {"role": "user", "content": "مرحبا", "timestamp": "2026-05-17T10:00:00Z"},
      {"role": "assistant", "content": "أهلاً!", "timestamp": "2026-05-17T10:00:05Z"}
    ]
  }
  ```

### 4.3 المهام

#### `GET /api/tasks`
- **Query:** `?limit=10&status=running`
- **الاستجابة (200):**
  ```json
  {
    "tasks": [
      {
        "id": "a1b2c3d4",
        "message": "اكتب دالة Fibonacci",
        "status": "complete",
        "agent": "coder",
        "progress": 100,
        "created_at": "2026-05-17T10:00:00Z"
      }
    ],
    "total": 1
  }
  ```

#### `GET /api/tasks/{task_id}`
- **الاستجابة (200):**
  ```json
  {
    "id": "a1b2c3d4",
    "message": "اكتب دالة Fibonacci",
    "status": "complete",
    "result": "def fibonacci(n):...",
    "agent": "coder",
    "progress": 100,
    "created_at": "2026-05-17T10:00:00Z",
    "updated_at": "2026-05-17T10:00:10Z"
  }
  ```

### 4.4 الإعدادات

#### `POST /api/settings`
- **المدخلات:**
  ```json
  {
    "key": "provider",
    "value": "ollama"
  }
  ```
- **الاستجابة (200):** `{"status": "saved", "key": "provider"}`

#### `GET /api/settings`
- **الاستجابة (200):**
  ```json
  {
    "lang": "ar",
    "theme": "dark",
    "provider": "ollama",
    "model": "llama3.2",
    "auth_enabled": false,
    "telegram_enabled": false,
    "project_dir": "."
  }
  ```
- **ملاحظة:** لا تُرجع مفاتيح API

#### `GET /api/status`
- **الاستجابة (200):**
  ```json
  {
    "connected": true,
    "provider": "ollama",
    "model": "llama3.2",
    "latency_ms": 150
  }
  ```

### 4.5 عام

#### `GET /api/global_stream` (SSE)
- **الأحداث:**
  ```
  event: task_update
  data: {"task_id": "a1b2c3d4", "status": "complete", "progress": 100}

  event: play_sound
  data: {"message": "task_complete"}
  ```

#### `GET /api/tray/ping`
- **الاستجابة (200):** `{"status": "ok", "timestamp": "2026-05-17T10:00:00Z"}`

#### `GET /api/project`
- **الاستجابة (200):**
  ```json
  {
    "name": "Emo AI Orchestrator",
    "path": "/Users/AI Workspace/Emo-AI",
    "file_count": 25
  }
  ```

---

## 5. هيكل الملفات المقترح (MVP)

```
Emo-AI/
│
├── 📄 main.py                          # نقطة الدخول (مُحدَّث)
├── 📄 brain.py                         # LLM Interface (مُنفَّذ)
├── 📄 agent.py                         # Agent System (مُنفَّذ)
├── 📄 memory.py                        # Memory System (مُنفَّذ)
├── 📄 tools.py                         # Tool base class + Registry (مُنفَّذ)
├── 📄 i18n.py                          # ✅ موجود
├── 📄 telegram_bot.py                  # ✅ موجود (يحتاج تكامل)
├── 📄 tray.py                          # يحتاج استبدال rumps → pystray
│
├── 📄 project_tools.py                 # ✅ موجود
├── 📄 devops_tools.py                  # ✅ موجود
├── 📄 supabase_tools.py                # ✅ موجود
├── 📄 firebase_tools.py                # ✅ موجود
├── 📄 github_tools.py                  # ✅ موجود
│
├── 📁 core/
│   ├── 📄 state.py                     # مُحدَّث (مع conversations + db)
│   ├── 📄 context_builder.py           # ✅ موجود
│   ├── 📄 task_manager.py              # مُحدَّث (مع SQLite)
│   ├── 📄 tasks.py                     # مُنفَّذ (cleanup logic)
│   ├── 📄 orchestrator.py              # جديد — Task Dispatcher
│   └── 📄 db.py                        # جديد — SQLite manager
│
├── 📁 routers/
│   ├── 📄 chat.py                      # مُحدَّث (مع SSE)
│   ├── 📄 auth.py                      # جديد — مصادقة
│   ├── 📄 settings.py                  # جديد — إعدادات
│   ├── 📄 tasks.py                     # جديد — مهام
│   ├── 📄 conversations.py             # جديد — محادثات
│   └── 📄 stream.py                    # جديد — SSE
│
├── 📁 middleware/
│   ├── 📄 auth.py                      # جديد — JWT middleware
│   └── 📄 logging.py                   # جديد — Audit logging
│
├── 📁 models/                          # جديد — Pydantic models
│   ├── 📄 task.py
│   ├── 📄 conversation.py
│   ├── 📄 message.py
│   ├── 📄 user.py
│   └── 📄 settings.py
│
├── 📁 migrations/                      # جديد — SQLite migrations
│   └── 📄 001_initial.sql
│
├── 📁 templates/                       # ✅ موجود
├── 📁 static/                          # ✅ موجود
│
├── 📄 requirements.txt                 # مُحدَّث
├── 📄 .env.example                     # جديد
├── 📄 Dockerfile                       # جديد
├── 📄 docker-compose.yml               # جديد (اختياري)
├── 📄 LICENSE                          # جديد (MIT)
│
├── 📁 tests/                           # جديد
│   ├── 📄 test_brain.py
│   ├── 📄 test_task_manager.py
│   ├── 📄 test_auth.py
│   └── 📄 test_chat.py
│
└── 📁 docs/                            # ✅ موجود
```

---

## 6. ملف المتطلبات المُحدَّث (requirements.txt)

```
# Core
fastapi>=0.115.0
uvicorn[standard]>=0.30.0
pydantic>=2.0.0
python-dotenv>=1.0.0

# LLM
openai>=1.0.0
httpx>=0.27.0

# Database
aiosqlite>=0.20.0

# Auth
PyJWT>=2.8.0
bcrypt>=4.1.0

# SSE
sse-starlette>=2.0.0

# System Tray (cross-platform)
pystray>=0.19.0
Pillow>=10.0.0

# Telegram
python-telegram-bot>=21.0

# Security (GDPR/SOC2)
cryptography>=42.0.0

# Testing
pytest>=8.0.0
pytest-cov>=5.0.0
pytest-asyncio>=0.23.0

# Utilities
psutil>=5.9.0
```

---

## 7. Dockerfile

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# نظام
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# متغيرات
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

# متطلبات
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# تطبيق
COPY . .

# استبعد ملفات التطوير
RUN rm -rf venv/ __pycache__/ tests/ docs/ *.save

# منفذ
EXPOSE 8080

# تشغيل
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
```

---

## 8. بوابة الانتقال للتنفيذ

قبل بدء التنفيذ:
- [x] وثيقة المتطلبات مكتملة ومُؤكَّدة
- [x] تقرير الاستكشاف مكتمل
- [x] مستند التصميم المعماري مكتمل
- [ ] **مطلوب:** موافقة خطية من صاحب القرار على:
  - [ ] التقنيات المختارة (القسم 2)
  - [ ] مخطط قاعدة البيانات (القسم 3)
  - [ ] واجهات API (القسم 4)
  - [ ] هيكل الملفات المقترح (القسم 5)
- [ ] **مطلوب:** POC يثبت Brain + Ollama يعملان معاً

---

**نهاية المستند — الإصدار 1.0.0-DRAFT**

*جاهز للانتقال لمرحلة التنفيذ بعد الموافقة.*
