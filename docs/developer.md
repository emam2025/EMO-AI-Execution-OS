# EMO AI Orchestrator — Developer Reference Guide

| البند          | القيمة                                        |
|----------------|-----------------------------------------------|
| **التاريخ**    | 2026-05-17                                    |
| **المؤلف**     | opencode AI Agent                             |
| **الحالة**     | نهائي — مرجع رسمي                             |
| **الإصدار**    | 1.0.0                                         |
| **المشروع**    | EMO AI Orchestrator v4.0.0                    |
| **الترخيص**    | Open Source (MIT/Apache 2.0 — TBD)            |
| **المنصات**    | macOS + Windows + Android (web-responsive)    |
| **الهدف**      | 3 مستخدمين في المرحلة الأولى                  |
| **الامتثال**   | GDPR + SOC2                                   |

---

## فهرس المحتويات

1. [نظرة عامة على المشروع](#1-نظرة-عامة-على-المشروع)
2. [هيكل المشروع](#2-هيكل-المشروع)
3. [خريطة الاعتماديات (Dependency Map)](#3-خريطة-الاعتماديات-dependency-map)
4. [المكونات الأساسية](#4-المكونات-الأساسية)
5. [واجهة البرمجة (API Reference)](#5-واجهة-البرمجة-api-reference)
6. [نظام الوكلاء](#6-نظام-الوكلاء)
7. [نظام الأدوات](#7-نظام-الأدوات)
8. [إعداد بيئة التطوير](#8-إعداد-بيئة-التطوير)
9. [دليل التشغيل](#9-دليل-التشغيل)
10. [دليل الصيانة](#10-دليل-الصيانة)
11. [استكشاف الأخطاء](#11-استكشاف-الأخطاء)
12. [الأمان والامتثال](#12-الأمان-والامتثال)
13. [نماذج البيانات](#13-نماذج-البيانات)
14. [دليل المساهمة](#14-دليل-المساهمة)
15. [سجل التغييرات](#15-سجل-التغييرات)

---

## 1. نظرة عامة على المشروع

### 1.1 ما هو EMO AI Orchestrator؟

نظام تنسيق ذكي متعدد الوكلاء (Multi-Agent Intelligence Orchestration System) يعمل كطبقة وسيطة بين المستخدم ونماذج الذكاء الاصطناعي. النظام يُدير وكلاء متعددين ويوجّه المهام تلقائياً عبر واجهة ويب تفاعلية وتكامل مع Telegram.

### 1.2 المزايا الأساسية

| الميزة | الوصف | الحالة |
|--------|-------|--------|
| محادثات ذكية | دردشة مع وكلاء AI متعددين | ⚠️ جزئي (mock) |
| وكلاء متعددون | Planner, Coder, Writer, Researcher | ⚠️ stubs |
| نماذج متعددة | OpenRouter, Groq, Gemini (API) + Ollama (محلي) | ⚠️ stub |
| أدوات DevOps | Vercel, Docker, Env Manager | ✅ يعمل |
| أدوات مشاريع | Debugger, Code Reviewer, Scaffold, Analyzer | ✅ يعمل |
| تكامل GitHub | إدارة المستودعات عبر API | ✅ يعمل |
| تكامل Supabase | قاعدة بيانات + Storage | ✅ يعمل |
| تكامل Firebase | Firestore + Auth + Hosting | ✅ يعمل |
| بوت Telegram | دردشة عبر Telegram | ✅ يعمل |
| واجهة ويب | Glass Morphism + RTL/LTR + Dark/Light | ✅ يعمل |
| System Tray | مراقبة الخادم (macOS) | ✅ يعمل |

### 1.3 التقنيات المستخدمة

| التقنية | الإصدار | الاستخدام |
|---------|---------|-----------|
| Python | 3.14 | اللغة الأساسية |
| FastAPI | أحدث | إطار عمل HTTP |
| Uvicorn | أحدث | ASGI Server |
| Pydantic | أحدث | التحقق من البيانات |
| python-dotenv | أحدث | إدارة المتغيرات البيئية |
| TailwindCSS | CDN | تصميم الواجهة |
| Font Awesome | 6.5.1 | الأيقونات |
| python-telegram-bot | اختياري | تكامل Telegram |
| rumps | اختياري | System Tray (macOS) |
| psutil | اختياري | مراقبة العمليات |
| openai | مطلوب | SDK للتواصل مع LLM |
| fpdf | اختياري | توليد PDF |

---

## 2. هيكل المشروع

```
Emo-AI/
│
├── 📄 main.py                          # نقطة الدخول — FastAPI app
├── 📄 brain.py                         # واجهة LLM (STUB — يحتاج تنفيذ)
├── 📄 brain.py.save                    # نسخة احتياطية بتنفيذ حقيقي (OpenAI SDK)
├── 📄 agent.py                         # نظام الوكلاء (STUB)
├── 📄 memory.py                        # نظام الذاكرة (STUB)
├── 📄 tools.py                         # تسجيل الأدوات (STUB — يحتاج Tool base class)
├── 📄 i18n.py                          # الترجمة (عربي/إنجليزي) — ✅ كامل
├── 📄 telegram_bot.py                  # بوت Telegram — ✅ يعمل
├── 📄 tray.py                          # System Tray (macOS) — ✅ يعمل
├── 📄 generate_pdf.py                  # مولّد PDF توثيقي — ✅ يعمل
│
├── 📄 project_tools.py                 # أدوات ذكاء المشاريع (8 أصناف, 1409 سطر) — ✅ يعمل
├── 📄 devops_tools.py                  # أدوات DevOps (4 أصناف, 273 سطر) — ✅ يعمل
├── 📄 supabase_tools.py                # أدوات Supabase (6 أصناف, 220 سطر) — ✅ يعمل
├── 📄 firebase_tools.py                # أدوات Firebase (5 أصناف, 196 سطر) — ✅ يعمل
├── 📄 github_tools.py                  # أدوات GitHub (7 أصناف, 193 سطر) — ✅ يعمل
│
├── 📁 core/
│   ├── 📄 state.py                     # حالة التطبيق العامة (Singleton) — ✅ يعمل
│   ├── 📄 context_builder.py           # بناء سياق المحادثة — ✅ يعمل
│   ├── 📄 task_manager.py              # إدارة المهام (thread-safe) — ✅ يعمل
│   └── 📄 tasks.py                     # حلقة تنظيف المهام (STUB)
│
├── 📁 routers/
│   └── 📄 chat.py                      # نقطة_chat API — ⚠️ جزئي
│
├── 📁 templates/
│   ├── 📄 index.html                   # الواجهة الرئيسية (1109 سطر) — ✅ كامل
│   └── 📄 login.html                   # صفحة تسجيل الدخول (171 سطر) — ✅ كامل
│
├── 📁 static/                          # ملفات ثابتة (CSS, JS, صور)
│
├── 📁 docs/                            # وثائق المشروع
│   ├── 📄 REQUIREMENTS_UNDERSTANDING.md # وثيقة المتطلبات
│   ├── 📄 core_features_api.json        # مواصفات API
│   ├── 📄 PROGRESS.md                   # سجل التقدم
│   └── 📄 developer.md                  # هذا الملف
│
├── 📄 requirements.txt                 # المتطلبات الأساسية (4 حزم فقط!)
├── 📄 README.md                        # README مختصر
│
├── 📄 .emo_settings.json               # إعدادات التطبيق (⚠️ مفاتيح API مكشوفة!)
├── 📄 .emo_conversations.json          # بيانات المحادثات
├── 📄 .emo_chat_history.json           # سجل المحادثات
│
├── 📄 .env                             # المتغيرات البيئية (يجب إنشاؤه — غير موجود حالياً)
├── 📄 .gitignore                       # ملفات مستبعدة من Git
│
├── 📁 venv/                            # بيئة Python الافتراضية (مستبعدة)
├── 📁 __pycache__/                     # ملفات Python المترجمة (مستبعدة)
│
└── 📁 my-project/                      # مشاريع مولّدة (scaffolded artifacts)
    📁 my_project/
    📁 test-app/
```

### 2.1 وصف كل ملف

#### الملفات الأساسية

| الملف | الأسطر | الحالة | الوصف |
|-------|--------|--------|-------|
| `main.py` | 36 | ✅ يعمل | نقطة دخول FastAPI. يُنشئ التطبيق، يدير lifespan مع خلفية cleanup، ويشغّل Uvicorn على المنفذ 8080 |
| `brain.py` | 6 | ❌ STUB | واجهة LLM. حالياً يرجع نص المستخدم كما هو. **يجب استبداله بـ `brain.py.save`** |
| `brain.py.save` | 28 | ✅ يعمل | تنفيذ حقيقي يستخدم `openai.OpenAI` مع دعم OpenRouter/Groq عبر `LLM_PROVIDER` env var |
| `agent.py` | 16 | ❌ STUB | صنف Agent ومُصنّع. يُنشئ 3 وكلاء (planner, writer, researcher) لكن بـ mock Brain |
| `memory.py` | 3 | ❌ STUB | صنف Memory فارغ. قائمة `data = []` بدون أي منطق |
| `tools.py` | 9 | ❌ STUB | Registry بسيطة. لا تحتوي على `Tool` base class الذي تستورده الأدوات الأخرى |

#### الأدوات (Tools)

| الملف | الأسطر | الأصناف | الحالة | الوصف |
|-------|--------|---------|--------|-------|
| `project_tools.py` | 1409 | 8 | ✅ يعمل | AutoDebugger, AICodeReviewer, ProjectMonitor, ProjectScaffold, ProjectAnalyzer, DependencyManager, CodebaseRefactor, DeploymentBuilder |
| `devops_tools.py` | 273 | 4 | ✅ يعمل | VercelDeploy, DockerBuild, DockerRun, EnvManager |
| `supabase_tools.py` | 220 | 6 | ✅ يعمل | CreateProject, CreateTable, InsertData, Query, AuthSetup, StorageUpload |
| `firebase_tools.py` | 196 | 5 | ✅ يعمل | InitProject, AuthSetup, FirestoreWrite, FirestoreRead, Deploy |
| `github_tools.py` | 193 | 7 | ✅ يعمل | CreateRepo, CloneRepo, PushChanges, PullRepo, ReadFile, WriteFile, CreateBranch |

#### النواة (Core)

| الملف | الأسطر | الحالة | الوصف |
|-------|--------|--------|-------|
| `core/state.py` | 17 | ⚠️ خطأ | Singleton للحالة العامة. **خطأ: لا يُعرّف `conversations` لكن `chat.py` يستخدمه** |
| `core/context_builder.py` | 63 | ✅ يعمل | يبني سياق المحادثة: آخر 12 رسالة، حد 1200 حرف/رسالة، تنظيف نصوص |
| `core/task_manager.py` | 24 | ✅ يعمل | إدارة مهام thread-safe مع dict. CRUD أساسي بدون SSE |
| `core/tasks.py` | 5 | ❌ STUB | حلقة تنظيف مهام — تنام 300 ثانية بلا فعل |

#### التكامل

| الملف | الأسطر | الحالة | الوصف |
|-------|--------|--------|-------|
| `telegram_bot.py` | 197 | ✅ يعمل | بوت Telegram كامل: تفويض، أوامر، إعادة توجيه. يعمل في thread منفصل |
| `tray.py` | 543 | ✅ يعمل | تطبيق macOS system tray: مراقبة، إعادة تشغيل، إشعارات. fallback console mode |
| `i18n.py` | 262 | ✅ يعمل | ~130 مفتاح ترجمة لكل لغة (EN/AR). دالة `t(key, lang)` |

#### القوالب

| الملف | الأسطر | الحالة | الوصف |
|-------|--------|--------|-------|
| `templates/index.html` | 1109 | ✅ كامل | واجهة رئيسية: 3 ألواح (محادثات/وكلاء، دردشة، سجل/مهام). Glass Morphism + TailwindCSS |
| `templates/login.html` | 171 | ✅ كامل | صفحة تسجيل دخول/إنشاء حساب مع particle animation |

---

## 3. خريطة الاعتماديات (Dependency Map)

### 3.1 مخطط الاستيرادات

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

tray.py (standalone — يستدعي main.py عبر subprocess)
telegram_bot.py (standalone — يحتاج on_message callback)

project_tools.py  ──┐
devops_tools.py     │
supabase_tools.py   ├──> tools.Tool (غير موجود! يستخدمون fallback)
firebase_tools.py   │
github_tools.py     ┘

i18n.py (غير مُستورد — يُستخدم server-side rendering)
generate_pdf.py (standalone utility)
```

### 3.2 الاعتماديات الخارجية (requirements.txt)

```
fastapi          # إطار عمل HTTP
uvicorn          # ASGI Server
pydantic         # التحقق من البيانات
python-dotenv    # متغيرات بيئية
```

### 3.3 الاعتماديات المطلوبة غير المُثبَّتة

| الحزمة | السبب | الأولوية |
|--------|-------|----------|
| `openai` | ربط Brain بـ LLM حقيقي | 🔴 حرجة |
| `python-telegram-bot` | تكامل Telegram | 🟡 عالية |
| `rumps` | System Tray (macOS) | 🟡 عالية |
| `psutil` | مراقبة العمليات | 🟢 متوسطة |
| `fpdf` | توليد PDF | 🟢 متوسطة |
| `aiosqlite` | قاعدة بيانات SQLite async | 🟡 عالية |
| `PyJWT` | مصادقة JWT | 🟡 عالية |
| `bcrypt` | تشفير كلمات المرور | 🟡 عالية |
| `httpx` | عميل HTTP async لـ Ollama | 🟡 عالية |

---

## 4. المكونات الأساسية

### 4.1 FastAPI Application (`main.py`)

```python
# نقطة الدخول الرئيسية
app = FastAPI(
    title="Emo AI Orchestrator",
    version="4.0.0",
    lifespan=lifespan  # يدير cleanup_old_tasks_loop
)

# المسجلات المسجَّلة
app.include_router(chat_router)  # /api/chat

# نقاط النهاية الحالية
GET  /          # حالة الخادم
POST /api/chat  # إرسال رسالة

# المسجل المطلوب (غير موجود)
GET  /api/stream/{task_id}       # SSE للبث المباشر
GET  /api/tasks                  # قائمة المهام
GET  /api/conversations          # قائمة المحادثات
POST /api/conversations          # إنشاء محادثة
POST /api/conversations/{id}/activate  # تفعيل محادثة
DELETE /api/conversations/{id}   # حذف محادثة
POST /api/settings               # تحديث إعداد
GET  /api/status                 # حالة LLM
GET  /api/history                # سجل المحادثة
GET  /api/global_stream          # بث عام SSE
GET  /api/project                # معلومات المشروع
GET  /api/tray/ping              # فحص صحة الخادم
POST /api/auth/login             # تسجيل دخول
POST /api/auth/signup            # إنشاء حساب
GET  /api/auth/verify            # التحقق من token
```

### 4.2 AppState (`core/state.py`)

```python
class AppState:
    tools: Registry          # ⚠️ stub
    memory: Memory           # ⚠️ stub
    task_manager: TaskManager # ✅ يعمل
    agents: dict             # ⚠️ stubs (planner, writer, researcher)
    conversations: dict      # ❌ غير مُعرَّف (BUG!)

state = AppState()  # singleton عالمي
```

### 4.3 TaskManager (`core/task_manager.py`)

```python
class TaskManager:
    tasks: dict              # {task_id: {id, message, status, created_at}}
    lock: threading.Lock     # thread-safe

    create_task(task_id, message)   # → pending
    update_task(task_id, **kwargs)  # → running/complete/error
    get_task(task_id)               # → dict أو None
```

### 4.4 ContextBuilder (`core/context_builder.py`)

```python
MAX_CONTEXT_MESSAGES = 12
MAX_MESSAGE_LENGTH = 1200

def _clean_text(text: str) -> str:
    # يزيل المسافات الزائدة ويقص النص

def build_conversation_context(messages: List[Dict]) -> str:
    # يأخذ آخر 12 رسالة، ينظفها، يُرجع "ROLE: content"
```

### 4.5 Brain (`brain.py`) — يحتاج تنفيذ

```python
# الحالي (STUB):
class Brain:
    def ask(self, system="", user="", **kwargs):
        return f"AI Response => {user}"  # ❌ echo فقط

    def test_connection(self):
        return True, "mock-model"  # ❌ mock

# المطلوب (من brain.py.save):
class Brain:
    def __init__(self, provider="openrouter", model="", api_key=""):
        # يختار المزود ويُنشئ openai.OpenAI client

    def ask(self, system="", user="", **kwargs):
        # يستدعي client.chat.completions.create()

    def test_connection(self):
        # يختبر الاتصال الحقيقي
```

---

## 5. واجهة البرمجة (API Reference)

### 5.1 النقاط الموجودة

#### `GET /`
- **الوصف:** حالة الخادم
- **الاستجابة:** `{"name": "Emo AI Orchestrator", "version": "4.0.0", "status": "running"}`

#### `POST /api/chat`
- **الوصف:** إرسال رسالة وبدء مهمة
- **المدخلات:**
  ```json
  {
    "message": "string (required)",
    "conversation_id": "string (optional)"
  }
  ```
- **الاستجابة:**
  ```json
  {
    "task_id": "string (8-char UUID)",
    "status": "started"
  }
  ```
- **السلوك:** يُنشئ مهمة، يُشغّل thread خلفية، يستدعي planner agent

### 5.2 النقاط المطلوبة (غير موجودة)

كل النقاط التي تستدعيها الواجهة الأمامية لكن غير مُنفَّذة في الخادم:

| النقطة | الطريقة | الوصف |
|--------|---------|-------|
| `/api/stream/{task_id}` | GET (SSE) | بث مباشر لتقدم المهمة |
| `/api/tasks` | GET | قائمة المهام |
| `/api/conversations` | GET | قائمة المحادثات |
| `/api/conversations` | POST | إنشاء محادثة |
| `/api/conversations/{id}/activate` | POST | تفعيل محادثة |
| `/api/settings` | POST | تحديث إعداد |
| `/api/status` | GET | حالة LLM |
| `/api/history` | GET | سجل المحادثة |
| `/api/global_stream` | GET (SSE) | بث عام للأحداث |
| `/api/project` | GET | معلومات المشروع |
| `/api/tray/ping` | GET | فحص صحة الخادم |
| `/api/auth/login` | POST | تسجيل دخول |
| `/api/auth/signup` | POST | إنشاء حساب |
| `/api/auth/verify` | GET | التحقق من token |
| `/api/speedtest` | GET | اختبار السرعة |

---

## 6. نظام الوكلاء

### 6.1 الوكلاء الحاليون

| الوكيل | الدور | اللون | الحالة |
|--------|-------|-------|--------|
| Planner | تخطيط وتوزيع المهام | بنفسجي (#8b5cf6) | ❌ stub |
| Coder | كتابة وتصحيح الأكواد | أخضر (#10b981) | ❌ غير موجود |
| Writer | كتابة المستندات | وردي (#ec4899) | ❌ stub |
| Researcher | بحث وتحقق | برتقالي (#f59e0b) | ❌ stub |

### 6.2 دورة حياة المهمة

```
1. المستخدم يرسل رسالة → POST /api/chat
2. الخادم يُنشئ task_id
3. يُنشئ thread خلفية → process_task()
4. يُنشئ سياق المحادثة → build_conversation_context()
5. يُرسل إلى Planner → planner.run(input)
6. Planner يرد بالنتيجة
7. تُحدَّث حالة المهمة → complete
8. (مطلوب) تُبَث النتيجة عبر SSE
```

### 6.3 المطلوب تنفيذه

```
1. ربط Brain بـ OpenRouter API (FR-03.01)
2. ربط Brain بـ Groq API (FR-03.02)
3. ربط Brain بـ Gemini API (FR-03.03)
4. ربط Brain بـ Ollama المحلي (FR-03.07)
5. إضافة وكيل Coder
6. تنفيذ توجيه المهام تلقائياً (FR-02.05)
7. ربط الأدوات بالوكلاء (FR-04)
```

---

## 7. نظام الأدوات

### 7.1 التصنيفات

| التصنيف | عدد الأدوات | الأدوات |
|---------|-------------|---------|
| DevOps | 4 | VercelDeploy, DockerBuild, DockerRun, EnvManager |
| Project Intelligence | 8 | AutoDebugger, AICodeReviewer, ProjectMonitor, ProjectScaffold, ProjectAnalyzer, DependencyManager, CodebaseRefactor, DeploymentBuilder |
| GitHub | 7 | CreateRepo, CloneRepo, PushChanges, PullRepo, ReadFile, WriteFile, CreateBranch |
| Supabase | 6 | CreateProject, CreateTable, InsertData, Query, AuthSetup, StorageUpload |
| Firebase | 5 | InitProject, AuthSetup, FirestoreWrite, FirestoreRead, Deploy |
| System | 2 | shell, files (غير مُنفَّذة) |

### 7.2 مشكلة Tool Base Class

الأدوات تحاول استيراد `Tool` من `tools.py` لكن الملف لا يُعرّفه:

```python
# tools.py الحالي — لا يحتوي على Tool!
class Registry:
    def categories(self):
        return {"system": ["shell", "files"], "ai": ["vision", "memory"]}

# كل أدوات *_tools.py تستخدم fallback:
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

**الحل المطلوب:** إضافة `Tool` base class إلى `tools.py`:

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

## 8. إعداد بيئة التطوير

### 8.1 المتطلبات المسبقة

| المتطلب | الإصدار | طريقة التثبيت |
|---------|---------|---------------|
| Python | 3.11+ | `brew install python` (macOS) |
| pip | مرفق مع Python | — |
| Node.js | 18+ (لأدوات Vercel) | `brew install node` |
| Docker | اختياري | Docker Desktop |
| Ollama | اختياري (محلي LLM) | `brew install ollama` |
| Git | 2.40+ | `brew install git` |

### 8.2 خطوات الإعداد

```bash
# 1. استنساخ المشروع
git clone <repo-url>
cd Emo-AI

# 2. إنشاء بيئة افتراضية
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
# أو: venv\Scripts\activate  # Windows

# 3. تثبيت المتطلبات الأساسية
pip install -r requirements.txt

# 4. تثبيت المتطلبات الإضافية
pip install openai aiosqlite PyJWT bcrypt httpx python-telegram-bot rumps psutil fpdf

# 5. إنشاء ملف .env
cp .env.example .env
# تعديل .env بالمفاتيح الخاصة بك

# 6. تشغيل الخادم
python main.py
# أو: uvicorn main:app --host 0.0.0.0 --port 8080 --reload

# 7. التحقق
curl http://localhost:8080/
# → {"name": "Emo AI Orchestrator", "version": "4.0.0", "status": "running"}
```

### 8.3 ملف .env.example

```bash
# EMO AI Orchestrator — Environment Variables
# انسخ هذا الملف إلى .env واملأ القيم

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

### 8.4 ملف .gitignore

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

## 9. دليل التشغيل

### 9.1 تشغيل الخادم

```bash
# الطريقة الأساسية
python main.py

# مع Uvicorn مباشرة (مع auto-reload للتطوير)
uvicorn main:app --host 0.0.0.0 --port 8080 --reload

# في الخلفية (production)
nohup uvicorn main:app --host 0.0.0.0 --port 8080 > emo.log 2>&1 &

# مع Docker (بعد إنشاء Dockerfile)
docker build -t emo-ai .
docker run -p 8080:8080 --env-file .env emo-ai
```

### 9.2 تشغيل Telegram Bot

```python
# إضافة إلى main.py:
from telegram_bot import TelegramBot

def telegram_callback(message):
    """توجيه رسالة Telegram إلى orchestrator"""
    # استدعاء chat endpoint
    ...

bot = TelegramBot(
    token=os.getenv("TELEGRAM_TOKEN", ""),
    on_message_callback=telegram_callback
)
if bot.token and bot.is_available:
    bot.start()
```

### 9.3 تشغيل System Tray

```bash
# macOS
python tray.py

# مع rumps غير مثبت
pip install rumps psutil
python tray.py

# Console fallback mode (بدون rumps)
python tray.py  # يتحول تلقائياً لـ simple_mode()
```

### 9.4 تشغيل Ollama (محلي)

```bash
# تثبيت Ollama
brew install ollama

# تشغيل الخدمة
ollama serve &

# تحميل نموذج
ollama pull llama3.2

# التحقق
curl http://localhost:11434/api/tags

# إعداد .env
LLM_PROVIDER=ollama
OLLAMA_MODEL=llama3.2
```

### 9.5 توليد PDF التوثيقي

```bash
pip install fpdf
python generate_pdf.py
# → يُنتج EMO_AI_ORCHESTRATOR_REFERENCE.pdf
```

---

## 10. دليل الصيانة

### 10.1 الصيانة اليومية

| المهمة | الأمر | التكرار |
|--------|-------|---------|
| فحص حالة الخادم | `curl http://localhost:8080/` | يومياً |
| فحص السجلات | `tail -f emo.log` | يومياً |
| فحص المساحة | `du -sh .emo_*.json` | أسبوعياً |
| تحديث المتطلبات | `pip list --outdated` | أسبوعياً |

### 10.2 الصيانة الأسبوعية

| المهمة | الوصف |
|--------|-------|
| تنظيف المحادثات القديمة | حذف محادثات > 30 يوم من `.emo_conversations.json` |
| تنظيف المهام القديمة | TaskManager يُفترض أن ينظف تلقائياً (لكنه stub) |
| مراجعة السجلات | البحث عن أخطاء متكررة |
| تحديث المكتبات | `pip install --upgrade -r requirements.txt` |

### 10.3 الصيانة الشهرية

| المهمة | الوصف |
|--------|-------|
| مراجعة الأمان | فحص `.env` و `.emo_settings.json` |
| مراجعة التبعيات | `pip audit` لفحص الثغرات |
| نسخ احتياطي | نسخ `.emo_*.json` إلى موقع آمن |
| تحديث Ollama | `ollama pull <model>` لأحدث إصدار |

### 10.4 ملفات البيانات

| الملف | الحجم التقريبي | متى ينمو | كيف يُنظَّف |
|-------|----------------|----------|-------------|
| `.emo_conversations.json` | 10KB-1MB | كل محادثة جديدة | حذف المحادثات القديمة |
| `.emo_chat_history.json` | 10KB-5MB | كل رسالة | حد أقصى 1000 رسالة |
| `.emo_settings.json` | <1KB | نادر | لا يحتاج تنظيف |

### 10.5 النسخ الاحتياطي

```bash
# نسخ احتياطي يدوي
tar czf emo-backup-$(date +%Y%m%d).tar.gz \
  .emo_settings.json \
  .emo_conversations.json \
  .emo_chat_history.json \
  docs/

# استعادة
tar xzf emo-backup-YYYYMMDD.tar.gz
```

---

## 11. استكشاف الأخطاء

### 11.1 الأخطاء الشائعة

| الخطأ | السبب | الحل |
|-------|-------|------|
| `AttributeError: 'AppState' object has no attribute 'conversations'` | `state.py` لا يُعرّف `conversations` | أضف `self.conversations = {}` في `AppState.__init__` |
| `ImportError: cannot import name 'Tool' from 'tools'` | `tools.py` لا يُعرّف `Tool` base class | أضف `Tool` class كما في القسم 7.2 |
| `ModuleNotFoundError: No module named 'openai'` | مكتبة openai غير مُثبَّتة | `pip install openai` |
| `ModuleNotFoundError: No module named 'telegram'` | python-telegram-bot غير مُثبَّت | `pip install python-telegram-bot` |
| `ModuleNotFoundError: No module named 'rumps'` | rumps غير مُثبَّت (macOS فقط) | `pip install rumps` أو استخدم console mode |
| الخادم لا يستجيب | المنفذ 8080 مشغول | غيّر المنفذ: `PORT=8081 python main.py` |
| مفاتيح API لا تعمل | غير مُعيَّنة في `.env` | أنشئ `.env` وانسخ المفاتيح |
| Ollama لا يستجيب | الخدمة لا تعمل | `ollama serve` |
| Telegram bot لا يعمل | token غير صحيح أو python-telegram-bot غير مُثبَّت | تحقق من token و `pip install python-telegram-bot` |

### 11.2 فحص الصحة

```bash
# 1. فحص الخادم
curl http://localhost:8080/
# → {"name": "Emo AI Orchestrator", "version": "4.0.0", "status": "running"}

# 2. فحص Tray ping (إذا كان الخادم يعمل)
curl http://localhost:8080/api/tray/ping

# 3. فحص LLM
curl http://localhost:8080/api/status

# 4. فحص المحادثات
curl http://localhost:8080/api/conversations

# 5. فحص المهام
curl http://localhost:8080/api/tasks

# 6. فحص الاتصال بـ Ollama
curl http://localhost:11434/api/tags
```

### 11.3 وضع التصحيح (Debug Mode)

```bash
# تشغيل مع verbose logging
DEBUG=true uvicorn main:app --host 0.0.0.0 --port 8080 --reload --log-level debug

# فحص logs
tail -f emo.log | grep -i error

# Python debugger
python -m pdb main.py
```

### 11.4 إعادة تعيين كاملة

```bash
# حذف كل شيء والبدء من جديد
rm -rf venv/
rm -rf __pycache__/
rm -rf *.egg-info/
rm -f .emo_conversations.json
rm -f .emo_chat_history.json

# إعادة الإعداد
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
pip install openai aiosqlite PyJWT bcrypt httpx
cp .env.example .env
# تعديل .env
python main.py
```

---

## 12. الأمان والامتثال

### 12.1 إدارة الأسرار

| القاعدة | الوصف |
|---------|-------|
| ❌ لا تضع مفاتيح API في الكود | استخدم `.env` دائماً |
| ❌ لا ترفع `.env` لـ Git | تأكد من `.gitignore` |
| ❌ لا تعرض المفاتيح في الواجهة | استخدم `type="password"` في HTML |
| ✅ استخدم `python-dotenv` | لتحميل `.env` تلقائياً |
| ✅ شفر كلمات المرور | استخدم `bcrypt` |
| ✅ استخدم JWT للمصادقة | tokens بمدة صلاحية محددة |

### 12.2 متطلبات GDPR

| المتطلب | التنفيذ المطلوب |
|---------|-----------------|
| حق الوصول | API endpoint لتصدير بيانات المستخدم |
| حق المسح | API endpoint لحذف بيانات المستخدم نهائياً |
| حق التصحيح | API endpoint لتعديل بيانات المستخدم |
| Consent | شاشة موافقة قبل جمع البيانات |
| Data minimization | جمع أقل بيانات ممكنة |
| Encryption | تشفير البيانات الحساسة في الراحة |

### 12.3 متطلبات SOC2

| المتطلب | التنفيذ المطلوب |
|---------|-----------------|
| Audit logs | تسجيل كل عملية حساسة |
| Access control | مصادقة + تفويض لكل endpoint |
| Encryption in transit | HTTPS (TLS 1.2+) |
| Encryption at rest | تشفير ملفات البيانات |
| Incident response | خطة استجابة للحوادث |
| Regular testing | اختبارات اختراق دورية |

### 12.4 تشفير البيانات

```python
# تشفير كلمات المرور
import bcrypt
password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt())

# التحقق
bcrypt.checkpw(password.encode(), stored_hash)

# تشفير البيانات الحساسة (مثال: Fernet)
from cryptography.fernet import Fernet
key = Fernet.generate_key()
f = Fernet(key)
encrypted = f.encrypt(secret_data.encode())
decrypted = f.decrypt(encrypted).decode()
```

---

## 13. نماذج البيانات

### 13.1 Task

```json
{
  "id": "a1b2c3d4",
  "message": "نص الرسالة الأصلية",
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
  "name": "محادثة تجريبية",
  "messages": [
    {
      "role": "user | assistant | system",
      "content": "نص الرسالة",
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

## 14. دليل المساهمة

### 14.1 معايير الكود

| المعيار | الوصف |
|---------|-------|
| PEP 8 | دليل تنسيق Python الرسمي |
| Type Hints | استخدم type hints في كل الدوال |
| Docstrings | كل صنف ودالة يجب أن تحتوي docstring |
| Solids | اتبع مبادئ SOLID |
| 12-Factor App | اتبع مبادئ 12-Factor |

### 14.2 هيكلية commits

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

### 14.3 عملية Pull Request

1. أنشئ فرع جديد: `git checkout -b feat/feature-name`
2. نفّذ التغييرات مع commits واضحة
3. اختبر محلياً: `python main.py` + فحص endpoints
4. افتح PR مع وصف واضح
5. انتظر مراجعة الكود
6. عدّل حسب الملاحظات
7. دمج بعد الموافقة

### 14.4 اختبار التغييرات

```bash
# فحص أساسي
python main.py
curl http://localhost:8080/

# فحص المحادثة
curl -X POST http://localhost:8080/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "test"}'

# فحص SSE
curl -N http://localhost:8080/api/stream/<task_id>
```

---

## 15. سجل التغييرات

### v4.0.0 (الحالي)
- هيكل FastAPI أساسي
- واجهة ويب كاملة (Glass Morphism)
- أدوات DevOps و Project Intelligence
- تكامل GitHub, Supabase, Firebase
- بوت Telegram
- System Tray (macOS)
- i18n (EN/AR)
- ⚠️ Brain/Agent/Memory/Tools = stubs

### v4.1.0 (المخطط — MVP)
- [ ] ربط Brain بـ OpenRouter/Groq/Gemini/Ollama
- [ ] تنفيذ SSE stream
- [ ] تفعيل المصادقة
- [ ] نقل مفاتيح API إلى .env
- [ ] إضافة Tool base class
- [ ] إصلاح AppState.conversations bug
- [ ] إضافة SQLite
- [ ] Dockerfile
- [ ] اختبارات وحدة

### v5.0.0 (المخطط — Post-MVP)
- [ ] ذاكرة طويلة المدى (Vector DB)
- [ ] وكلاء مخصصون
- [ ] نظام صلاحيات متقدم
- [ ] CI/CD pipeline
- [ ] اختبارات تحميل
- [ ] دعم multi-tenant

---

## ملاحق

### أ. أوامر CLI سريعة

```bash
# تشغيل الخادم
python main.py

# تشغيل مع auto-reload
uvicorn main:app --reload --port 8080

# تشغيل Telegram bot
python -c "from telegram_bot import TelegramBot; b = TelegramBot(token='YOUR_TOKEN'); b.start()"

# تشغيل System Tray
python tray.py

# توليد PDF
python generate_pdf.py

# فحص التبعيات
pip list --outdated
pip audit

# تنظيف
find . -type d -name __pycache__ -exec rm -rf {} +
find . -type f -name "*.pyc" -delete
```

### ب. روابط مفيدة

| المورد | الرابط |
|--------|--------|
| FastAPI Docs | https://fastapi.tiangolo.com/ |
| OpenAI SDK | https://github.com/openai/openai-python |
| Ollama API | https://github.com/ollama/ollama/blob/main/docs/api.md |
| OpenRouter | https://openrouter.ai/docs |
| Groq API | https://console.groq.com/docs |
| Gemini API | https://ai.google.dev/docs |
| python-telegram-bot | https://docs.python-telegram-bot.org/ |
| rumps (macOS tray) | https://github.com/jaredks/rumps |
| TailwindCSS | https://tailwindcss.com/ |

### ج. قائمة المهام العاجلة

| # | المهمة | الأولوية | الجهد |
|---|--------|----------|-------|
| 1 | نقل مفاتيح API إلى `.env` | 🔴 حرجة | 30 دقيقة |
| 2 | استبدال `brain.py` بـ `brain.py.save` | 🔴 حرجة | 1 ساعة |
| 3 | إضافة `Tool` base class لـ `tools.py` | 🔴 حرجة | 30 دقيقة |
| 4 | إصلاح `AppState.conversations` bug | 🔴 حرجة | 15 دقيقة |
| 5 | تنفيذ SSE stream | 🔴 حرجة | 3-4 ساعات |
| 6 | إضافة `openai` لـ requirements.txt | 🟡 عالية | 5 دقائق |
| 7 | تنفيذ mصادقة JWT | 🟡 عالية | 4-6 ساعات |
| 8 | إنشاء Dockerfile | 🟡 عالية | 2 ساعة |
| 9 | إضافة SQLite | 🟡 عالية | 1-2 يوم |
| 10 | اختبارات وحدة أساسية | 🟡 عالية | 1 يوم |

---

**نهاية الوثيقة — الإصدار 1.0.0**

*هذه الوثيقة مرجع رسمي للمطورين. أي تعديل يجب أن يُحدَّث هنا أولاً.*

*للاستفسارات: راجع قسم "استكشاف الأخطاء" أو افتح issue في المستودع.*
