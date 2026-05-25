# وثيقة فهم المتطلبات — EMO AI Orchestrator

| البند          | القيمة                                        |
|----------------|-----------------------------------------------|
| **التاريخ**    | 2026-05-17                                    |
| **المؤلف**     | وكيل opencode (AI Software Engineer)          |
| **الحالة**     | مُحدَّث — قرارات صاحب القرار مُضمَّنة     |
| **الإصدار**    | 1.1.0-UPDATED                               |
| **المشروع**    | EMO AI Orchestrator                           |

---

## 1. ملخص المشروع

EMO AI Orchestrator هو نظام تنسيق ذكي متعدد الوكلاء (Multi-Agent Intelligence Orchestration System) يعمل كطبقة وسيطة بين المستخدم ونماذج الذكاء الاصطناعي المختلفة. النظام يُدير وكلاء متعددين (Planner, Coder, Writer, Researcher) ويوجّه المهام تلقائياً، مع واجهة ويب تفاعلية وتكامل مع Telegram وأدوات DevOps ومنصات سحابية (Supabase, Firebase, GitHub).

**حالة الكود الحالي:** المشروع موجود بنسخة v4.0.0 مع هيكل FastAPI، لكن المكونات الأساسية (Brain, Agent, Memory, Tools Registry) هي **stubs/mock** — أي أنها لا تتصل فعلياً بنماذج LLM ولا تنفذ أدوات حقيقية.

---

## 2. الاحتياجات الوظيفية (Functional Requirements)

### FR-01: إدارة المحادثات (Chat & Conversations)
| البند | الوصف | الأولوية |
|-------|-------|----------|
| FR-01.01 | إرسال رسالة نصية واستقبال رد عبر API `/api/chat` | Must |
| FR-01.02 | إنشاء/تفعيل/حذف المحادثات | Must |
| FR-01.03 | حفظ سجل المحادثات محلياً (JSON) | Must |
| FR-01.04 | دعم رفع الملفات (صور، مستندات) | Should |
| FR-01.05 | بث مباشر للتقدم عبر Server-Sent Events (SSE) | Must |

### FR-02: نظام الوكلاء المتعددين (Multi-Agent System)
| البند | الوصف | الأولوية |
|-------|-------|----------|
| FR-02.01 | وكيل Planner: تخطيط وتوزيع المهام | Must |
| FR-02.02 | وكيل Coder: توليد وتصحيح الأكواد | Must |
| FR-02.03 | وكيل Writer: كتابة المستندات والمحتوى | Should |
| FR-02.04 | وكيل Researcher: بحث وتحقق من الحقائق | Should |
| FR-02.05 | توجيه تلقائي للمهمة للوكيل المناسب | Must |
| FR-02.06 | دعم إضافة وكلاء مخصصين | Could |

### FR-03: التكامل مع نماذج LLM
| البند | الوصف | الأولوية |
|-------|-------|----------|
| FR-03.01 | دعم OpenRouter كمزود أساسي (API) | Must |
| FR-03.02 | دعم Groq كمزود بديل (API) | Must |
| FR-03.03 | دعم Gemini كمزود بديل (API) | Should |
| FR-03.04 | اختيار النموذج ديناميكياً من الإعدادات | Must |
| FR-03.05 | اختبار الاتصال بالنموذج | Must |
| FR-03.06 | دعم مزودين مخصصين (Custom Providers) | Could |
| FR-03.07 | دعم النماذج المحلية عبر Ollama | Must |
| FR-03.08 | التبديل السلس بين API و Ollama | Must |

### FR-04: نظام الأدوات (Tools System)
| البند | الوصف | الأولوية |
|-------|-------|----------|
| FR-04.01 | تسجيل الأدوات في Registry مصنّفة | Must |
| FR-04.02 | أدوات DevOps: Vercel Deploy, Docker Build/Run, Env Manager | Must |
| FR-04.03 | أدوات Project Intelligence: AutoDebugger, CodeReviewer, ProjectMonitor, Scaffold, Analyzer, DependencyManager, Refactor, DeploymentBuilder | Must |
| FR-04.04 | أدوات GitHub: CreateRepo, Clone, Push, Pull, ReadFile, WriteFile, CreateBranch | Should |
| FR-04.05 | أدوات Supabase: CreateProject, CreateTable, InsertData, Query, Auth, Storage | Should |
| FR-04.06 | أدوات Firebase: Init, Auth, Firestore Read/Write, Deploy | Should |
| FR-04.07 | أدوات نظام: shell, files | Must |

### FR-05: إدارة المهام (Task Management)
| البند | الوصف | الأولوية |
|-------|-------|----------|
| FR-05.01 | إنشاء مهمة وتتبع حالتها (pending → running → complete/error) | Must |
| FR-05.02 | استعلام عن حالة المهمة | Must |
| FR-05.03 | بث تقدم المهمة عبر SSE | Must |
| FR-05.04 | تنظيف المهام القديمة تلقائياً | Should |

### FR-06: الذاكرة والسياق (Memory & Context)
| البند | الوصف | الأولوية |
|-------|-------|----------|
| FR-06.01 | بناء سياق المحادثة مع حد أقصى للرسائل والطول | Must |
| FR-06.02 | حفظ واسترجاع المحادثات السابقة | Must |
| FR-06.03 | ذاكرة طويلة المدى (Long-term Memory) | Could |
| FR-06.04 | تنظيف النصوص الصاخبة قبل الإرسال للـ LLM | Must |

### FR-07: الواجهة الأمامية (Web UI)
| البند | الوصف | الأولوية |
|-------|-------|----------|
| FR-07.01 | واجهة دردشة تفاعلية بتصميم Glass Morphism | Must |
| FR-07.02 | دعم اللغتين العربية والإنجليزية (RTL/LTR) | Must |
| FR-07.03 | دعم الوضع الداكن والفاتح | Must |
| FR-07.04 | لوحة إعدادات (مفاتيح API، المزود، النموذج) | Must |
| FR-07.05 | عرض سجل التنفيذ والمهام | Must |
| FR-07.06 | عرض مكتبة الأدوات والبحث فيها | Should |
| FR-07.07 | عرض حالة الوكلاء (Online/Busy/Idle) | Should |
| FR-07.08 | Desktop View مع Vision Agent | Won't (MVP) |

### FR-08: تكامل Telegram
| البند | الوصف | الأولوية |
|-------|-------|----------|
| FR-08.01 | بوت Telegram يستقبل ويرسل رسائل | Must |
| FR-08.02 | تفويض المستخدمين عبر /start | Must |
| FR-08.03 | أوامر: /chat, /status, /help | Must |
| FR-08.04 | إشعارات تلقائية عند اكتمال المهام | Should |

### FR-09: تطبيق System Tray / Monitor
| البند | الوصف | الأولوية |
|-------|-------|----------|
| FR-09.01 | مراقبة حالة الخادم (macOS عبر rumps) | Should |
| FR-09.02 | إعادة تشغيل الخادم | Should |
| FR-09.03 | إشعارات الحالة | Could |
| FR-09.04 | بديل cross-platform لـ Windows (pystray) | Should |
| FR-09.05 | Android: إشعارات عبر Telegram Bot | Should |

### FR-10: الأمان والمصادقة
| البند | الوصف | الأولوية |
|-------|-------|----------|
| FR-10.01 | مصادقة أساسية (username/password hash) | Must |
| FR-10.02 | حماية مفاتيح API (عدم عرضها في الواجهة) | Must |
| FR-10.03 | نظام صلاحيات للأدوات الخطرة | Should |
| FR-10.04 | تشفير البيانات الحساسة في ملفات الإعدادات | Should |

---

## 3. الاحتياجات غير الوظيفية (Non-Functional Requirements)

| البند | الوصف | المعيار القابل للقياس |
|-------|-------|----------------------|
| NFR-01 | الأداء | زمن استجابة API ≤ 300ms تحت 100 طلب متزامن |
| NFR-02 | التوفر | وقت تشغيل ≥ 99.5% شهرياً |
| NFR-03 | التوسع | دعم حتى 1000 مستخدم متزامن في الإصدار الثاني |
| NFR-04 | الأمان | لا مفاتيح API مكشوفة في الكود؛ استخدام .env |
| NFR-04b | الامتثال | GDPR/SOC2: تشفير بيانات، حق المسح، consent, audit logs |
| NFR-07 | التوافق | Python 3.11+؛ macOS, Windows, Android (web-responsive) |
| NFR-09 | الخصوصية | بيانات مشفرة، حق المسح، consent management (GDPR) |
| NFR-10 | المراقبة | سجل تنفيذ مرئي + إشعارات |

---

## 4. تحليل الوجود الحالي مقابل المطلوب

### ما هو موجود ويعمل:
| المكون | الحالة | الملاحظات |
|--------|--------|-----------|
| FastAPI Server | ✅ يعمل | main.py + routers/chat.py |
| واجهة الويب | ✅ موجودة | templates/index.html (تصميم احترافي) |
| i18n (عربي/إنجليزي) | ✅ موجود | i18n.py |
| إدارة المهام (TaskManager) | ⚠️ جزئي | يعمل محلياً لكن بدون SSE حقيقي |
| بناء السياق (ContextBuilder) | ✅ يعمل | مع حدود رسائل وطول |
| أدوات DevOps | ✅ موجودة | devops_tools.py |
| أدوات Project Intelligence | ✅ موجودة | project_tools.py (1409 سطر) |
| أدوات GitHub | ✅ موجودة | github_tools.py |
| أدوات Supabase | ✅ موجودة | supabase_tools.py |
| أدوات Firebase | ✅ موجودة | firebase_tools.py |
| Telegram Bot | ✅ موجود | telegram_bot.py |
| System Tray | ✅ موجود | tray.py (macOS) |
| إعدادات | ✅ موجودة | .emo_settings.json |

### ما هو موجود لكن **لا يعمل فعلياً** (Stubs/Mock):
| المكون | المشكلة | التأثير |
|--------|---------|---------|
| Brain | يرجع نص المستخدم كما هو بدون LLM | النظام لا يولّد ردود ذكية |
| Agent | يستدعي Brain.mock فقط | الوكلاء لا ينفذون مهام حقيقية |
| Memory | قائمة فارغة بدون تنفيذ | لا ذاكرة طويلة المدى |
| Tools Registry | تصنيفات فقط بدون ربط حقيقي | الأدوات غير متصلة بالوكلاء |
| SSE Stream | غير مُنفّذ في chat.py | البث المباشر لا يعمل |
| المصادقة | auth_enabled=false | لا حماية للواجهة |

### ما هو **مفقود تماماً**:
| المكون | الوصف |
|--------|-------|
| ملف `.env` | مفاتيح API مخزنة في `.emo_settings.json` بشكل نصي — خطر أمني |
| Dockerfile | لا يوجد ملف Docker للنشر |
| CI/CD Pipeline | لا GitHub Actions أو أي pipeline |
| اختبارات | لا ملفات اختبار |
| توثيق API | لا OpenAPI/Swagger مخصص |
| قاعدة بيانات | كل شيء في-memory أو JSON محلي |

---

## 5. الافتراضات الصريحة (Explicit Assumptions)

| # | الافتراض | وسيلة التحقق |
|---|----------|-------------|
| A-01 | المشروع يستهدف macOS + Windows + Android | ✅ مؤكَّد من صاحب القرار |
| A-02 | OpenRouter هو المزود الأساسي لـ LLM | موجود في الإعدادات |
| A-03 | المستخدم النهائي هو مطور برمجيات يحتاج أدوات DevOps | استنتاج من الأدوات الموجودة |
| A-04 | النظام يعمل محلياً (Local-first) في مرحلة MVP | استنتاج من البنية الحالية |
| A-05 | Python 3.14 هو الإصدار المستخدم | موجود في venv/__pycache__ |
| A-06 | المشروع مفتوح المصدر ومتاح للجميع | ✅ مؤكَّد من صاحب القرار |
| A-07 | النماذج تعمل بـ API أو محلياً (Ollama) | ✅ مؤكَّد من صاحب القرار |
| A-08 | مفاتيح API مسؤولية المستخدم (مجاني/مدفوع) | ✅ مؤكَّد من صاحب القرار |
| A-09 | لا قاعدة بيانات مفضلة — SQLite افتراضياً | ✅ مؤكَّد من صاحب القرار |
| A-07 | عدد المستخدمين المتوقع في MVP: 1-10 | **معلومة مفقودة** — يحتاج تأكيد |
| A-08 | الميزانية الشهرية للـ API Keys: غير محددة | **معلومة مفقودة** — يحتاج تأكيد |

---

## 6. القيود (Constraints)

| # | القيد | التأثير |
|---|-------|---------|
| C-01 | مفاتيح API موجودة في ملف JSON غير مشفر | خطر أمني عالي — يجب نقلها لـ .env |
| C-02 | لا قاعدة بيانات حقيقية | محدودية في التوسع والمشاركة — SQLite كحل أولي |
| C-03 | processing في threads عادية (not async) | محدودية في التعامل المتزامن |
| C-04 | لا نظام اختبارات | صعوبة ضمان الجودة |
| C-05 | لا Docker | صعوبة النشر في بيئات متعددة |
| C-06 | tray.py يعمل على macOS فقط (rumps) | يجب استبداله بـ cross-platform (system-tray أو web-based) |
| C-07 | Android يحتاج واجهة متجاوبة أو تطبيق | web-responsive كحل MVP أولي |
| C-08 | GDPR/SOC2 يتطلب تشفير + حق المسح + consent | يضيف تعقيد أمني وقانوني |

---

## 7. أولويات المزايا (MoSCoW)

### Must Have (لا يعمل MVP بدونها):
1. ربط Brain بنموذج LLM حقيقي (OpenRouter/Groq API)
2. دعم النماذج المحلية عبر Ollama
3. تنفيذ SSE للبث المباشر
4. تفعيل المصادقة الأساسية
5. نقل مفاتيح API إلى `.env`
6. تنفيذ Task Manager مع SSE
7. ربط الأدوات بالوكلاء فعلياً
8. Dockerfile للنشر
9. ترخيص مفتوح المصدر (MIT/Apache 2.0)
10. دعم المنصات: macOS + Windows + Android (web-responsive)
11. Telegram Bot متكامل
12. الالتزام بـ GDPR/SOC2 (تشفير بيانات، حق المسح، consent)

### Should Have (مهم لكن يمكن تأجيله لأسبوع):
1. Telegram Bot متكامل
2. نظام صلاحيات للأدوات
3. اختبارات وحدة أساسية
4. GitHub Actions CI/CD
5. مراقبة وتحسين الأداء

### Could Have (تحسينات إضافية):
1. ذاكرة طويلة المدى (Vector DB)
2. دعم مزودين مخصصين
3. Vision Agent
4. نظام إشعارات متقدم
5. وكلاء مخصصون

### Won't Have (في MVP):
1. Desktop View كامل
2. نظام multi-tenant
3. لوحة تحكم إدارية
4. دعم WebSocket مزدوج الاتجاه
5. نظام billing/usage tracking

---

## 8. المعلومات المفقودة (Missing Information) — تحتاج تأكيد صاحب القرار

| # | المعلومة | الأثر | القيمة الافتراضية | الحالة |
|---|----------|-------|-------------------|--------|
| M-01 | هل المشروع مفتوح المصدر أم خاص؟ | يحدد الترخيص ومستوى التوثيق | **مفتوح المصدر — متاح للجميع** | ✅ مُؤكَّد |
| M-02 | عدد المستخدمين المستهدف في MVP | يحدد متطلبات التوسع | **3 مستخدمين في المرحلة الأولى** | ✅ مُؤكَّد |
| M-03 | الميزانية الشهرية لـ API Keys | يحدد اختيار النماذج | **حسب المستخدم — مجاني أو مدفوع** | ✅ مُؤكَّد |
| M-04 | المنصات المستهدفة | يحدد tray.py والبديل | **macOS + Windows + Android** | ✅ مُؤكَّد |
| M-05 | هل هناك قاعدة بيانات مفضلة؟ | يحدد اختيار DB | **لا توجد تفضيل — SQLite افتراضياً** | ✅ مُؤكَّد |
| M-06 | هل Telegram Bot مطلوب في MVP؟ | يحدد الأولوية | **بالتأكيد — Must** | ✅ مُؤكَّد |
| M-07 | ما النماذج المحددة المطلوبة؟ | يحدد الإعدادات | **Ollama للمحلي + OpenRouter/Groq/Gemini للـ API** | ✅ مُؤكَّد |
| M-08 | هل هناك متطلبات امتثال (GDPR, SOC2)؟ | يحدد متطلبات الأمان | **نعم — يجب الالتزام** | ✅ مُؤكَّد |
| M-09 | مَن هو صاحب القرار النهائي؟ | يحدد سلسلة الموافقة | ✅ **أنت (صاحب القرار)** | ✅ مُؤكَّد |
| M-10 | هل هناك deadline محدد لإطلاق MVP؟ | يحدد الجدول الزمني | **محدّد بالتاسك (Task-driven)** | ✅ مُؤكَّد |

---

## 9. مخاطر أولية مع التخفيف

| # | الخطر | الاحتمال | التأثير | التخفيف |
|---|-------|----------|---------|---------|
| R-01 | تسرب مفاتيح API (موجودة حالياً في JSON) | عالي | حرج | نقل فوري لـ .env + إضافة .env لـ .gitignore |
| R-02 | عدم استقرار نماذج LLM الخارجية | متوسط | عالي | دعم مزودين متعددين + fallback + Ollama محلي |
| R-03 | الأداء تحت الحمل | متوسط | متوسط | اختبارات تحميل + تحسين async |
| R-04 | تعقيد الكود الحالي (1409 سطر في ملف واحد) | عالي | متوسط | إعادة هيكلة تدريجية |
| R-05 | عدم توافق Python 3.14 مع بعض المكتبات | منخفض | متوسط | اختبار التوافق مبكراً |
| R-06 | فقدان بيانات المحادثات (JSON محلي) | متوسط | عالي | إضافة SQLite كقاعدة بيانات |
| R-07 | عدم التوافق مع GDPR/SOC2 | متوسط | حرج | تشفير البيانات + حق المسح + consent management + audit logs |
| R-08 | تعقيد دعم 3 منصات (macOS/Windows/Android) | عالي | عالي | web-responsive كحل MVP أولي + Electron للديسكتوب لاحقاً |

---

## 10. معايير القبول (Acceptance Criteria) — نماذج

### AC-01: توجيه الطلبات لنموذج ML
```json
{
  "feature": "توجيه الطلبات إلى نموذج ML مناسب",
  "priority": "Must",
  "acceptance_criteria": [
    "توجيه متطلبات نصية إلى نموذج 'NLP-v1' عندما حجم الطلب < 1k tokens",
    "زمن التوجيه ≤ 50ms",
    "في حالة فشل المزود الأساسي، التبديل للمزود البديل خلال 200ms"
  ]
}
```

### AC-02: بث مباشر للتقدم
```json
{
  "feature": "بث مباشر لتقدم المهمة عبر SSE",
  "priority": "Must",
  "acceptance_criteria": [
    "العميل يستقبل أحداث 'step_start', 'step_complete', 'result', 'error'",
    "زمن التأخير بين الحدث والاستلام ≤ 100ms",
    "إعادة الاتصال التلقائي عند فقدان الاتصال خلال 3 ثوانٍ"
  ]
}
```

### AC-03: المصادقة
```json
{
  "feature": "مصادقة المستخدم للواجهة",
  "priority": "Must",
  "acceptance_criteria": [
    "طلب تسجيل دخول مع username + password",
    "إرجاع token صالح لمدة 24 ساعة",
    "رفض الطلبات بدون token برسالة 401",
    "تشفير password بـ bcrypt أو معادل"
  ]
}
```

---

## 11. مؤشرات الأداء (KPIs) للمرحلة الأولى

| المؤشر | الهدف | طريقة القياس |
|--------|-------|-------------|
| زمن تطوير MVP | ≤ 8 أسابيع | تتبع Git commits |
| معدل نجاح الاختبارات الحرجة | ≥ 95% | pytest output |
| زمن استجابة API المتوسط | ≤ 300ms (100 concurrent) | Apache Bench / k6 |
| تغطية اختبارات الوحدة | ≥ 60% | pytest-cov |
| عدد الأخطاء الحرجة في الإنتاج | 0 | Sentry/logs |
| رضا المستخدم (subjective) | ≥ 4/5 | استبيان |

---

## 12. مخرجات JSON — الميزات الأساسية والواجهات

### 12.1 الميزات الأساسية (JSON)

```json
{
  "document": "EMO AI Core Features",
  "version": "1.0.0",
  "date": "2026-05-17",
  "features": [
    {
      "id": "FR-01",
      "name": "إدارة المحادثات",
      "priority": "Must",
      "status": "partial",
      "endpoints": ["POST /api/chat", "GET /api/conversations", "POST /api/conversations", "POST /api/conversations/{id}/activate"]
    },
    {
      "id": "FR-02",
      "name": "نظام الوكلاء المتعددين",
      "priority": "Must",
      "status": "stub",
      "agents": ["planner", "coder", "writer", "researcher"]
    },
    {
      "id": "FR-03",
      "name": "التكامل مع نماذج LLM",
      "priority": "Must",
      "status": "stub",
      "providers": ["openrouter", "groq", "gemini"]
    },
    {
      "id": "FR-04",
      "name": "نظام الأدوات",
      "priority": "Must",
      "status": "exists-not-connected",
      "categories": ["DevOps", "Project Intelligence", "GitHub", "Supabase", "Firebase", "System"]
    },
    {
      "id": "FR-05",
      "name": "إدارة المهام",
      "priority": "Must",
      "status": "partial",
      "states": ["pending", "running", "complete", "error"]
    },
    {
      "id": "FR-06",
      "name": "الذاكرة والسياق",
      "priority": "Must",
      "status": "partial"
    },
    {
      "id": "FR-07",
      "name": "الواجهة الأمامية",
      "priority": "Must",
      "status": "exists",
      "languages": ["en", "ar"],
      "themes": ["dark", "light"]
    },
    {
      "id": "FR-10",
      "name": "الأمان والمصادقة",
      "priority": "Must",
      "status": "disabled"
    }
  ]
}
```

### 12.2 واجهات API الأساسية (JSON)

```json
{
  "api_spec": "EMO AI Orchestrator API v1",
  "base_url": "http://localhost:8080",
  "endpoints": {
    "GET /": {
      "description": "حالة الخادم",
      "response": {
        "name": "string",
        "version": "string",
        "status": "string"
      }
    },
    "POST /api/chat": {
      "description": "إرسال رسالة وبدء مهمة",
      "input": {
        "message": {"type": "string", "required": true, "description": "نص الرسالة"},
        "conversation_id": {"type": "string", "required": false, "description": "معرف المحادثة"},
        "file_name": {"type": "string", "required": false},
        "file_type": {"type": "string", "required": false},
        "base64": {"type": "string", "required": false}
      },
      "response": {
        "task_id": {"type": "string", "description": "معرف المهمة"},
        "status": {"type": "string", "enum": ["started"]}
      }
    },
    "GET /api/stream/{task_id}": {
      "description": "بث مباشر لتقدم المهمة (SSE)",
      "events": [
        {"type": "step_start", "data": {"step": "string", "agent": "string", "tool": "string"}},
        {"type": "step_complete", "data": {"step": "string", "result": "string"}},
        {"type": "result", "data": {"content": "string"}},
        {"type": "error", "data": {"message": "string"}}
      ]
    },
    "GET /api/tasks": {
      "description": "قائمة المهام",
      "query_params": {"limit": {"type": "integer", "default": 10}},
      "response": {
        "tasks": [{"id": "string", "status": "string", "message": "string", "created_at": "string"}]
      }
    },
    "GET /api/conversations": {
      "description": "قائمة المحادثات",
      "response": {
        "conversations": [{"id": "string", "name": "string", "message_count": "integer"}],
        "active": "string"
      }
    },
    "POST /api/conversations": {
      "description": "إنشاء محادثة جديدة",
      "input": {"name": {"type": "string", "required": true}},
      "response": {"id": "string", "name": "string"}
    },
    "POST /api/settings": {
      "description": "تحديث إعداد",
      "input": {"key": {"type": "string"}, "value": {"type": "string"}},
      "response": {"status": "string", "enum": ["saved"]}
    },
    "GET /api/status": {
      "description": "حالة الاتصال بالـ LLM",
      "response": {
        "connected": "boolean",
        "provider": "string",
        "model": "string",
        "latency_ms": "integer"
      }
    },
    "GET /api/history": {
      "description": "سجل محادثة نشطة",
      "response": {
        "messages": [{"role": "string", "content": "string", "file_data": "object?"}]
      }
    },
    "GET /api/global_stream": {
      "description": "بث عام للأحداث (SSE)",
      "events": [
        {"type": "task_update", "data": {"task_id": "string", "status": "string"}},
        {"type": "play_sound", "data": {"message": "string"}}
      ]
    }
  }
}
```

### 12.3 نموذج البيانات (JSON)

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

## 13. خطوات التنفيذ خلال 24 ساعة (قابلة للتنفيذ فوراً)

### الخطوة 1: تأمين مفاتيح API (فوري — 30 دقيقة)

```bash
# 1. إنشاء ملف .env
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

# 2. التأكد من أن .env في .gitignore
echo ".env" >> /Users/AI\ Workspace/Emo-AI/.gitignore

# 3. إزالة المفاتيح من .emo_settings.json (استبدالها بـ "")
# يتم يدوياً أو عبر سكربت
```

### الخطوة 2: تثبيت المتطلبات وتشغيل الخادم (30 دقيقة)

```bash
cd /Users/AI\ Workspace/Emo-AI
source venv/bin/activate  # أو: python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
python main.py
# التحقق: curl http://localhost:8080/
```

### الخطوة 3: إنشاء ملف تكوين المشروع (JSON)

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

### الخطوة 4: إنشاء سجل التتبع (Tracking Log)

```bash
cat > /Users/AI\ Workspace/Emo-AI/docs/PROGRESS.md << 'EOF'
# سجل التقدم — EMO AI Orchestrator

## الأسبوع 1 (2026-05-17 إلى 2026-05-24)
- [x] وثيقة فهم المتطلبات (v1.0-DRAFT)
- [ ] تأمين مفاتيح API
- [ ] ربط Brain بـ OpenRouter API
- [ ] تنفيذ SSE stream
- [ ] تفعيل المصادقة الأساسية

## القرارات المطلوبة من صاحب القرار:
1. M-01: هل المشروع مفتوح المصدر أم خاص؟
2. M-02: عدد المستخدمين المستهدف؟
3. M-03: الميزانية الشهرية لـ API Keys؟
4. M-09: مَن صاحب القرار النهائي؟
5. M-10: هل هناك deadline محدد؟
EOF
```

---

## 14. خلاصة التوصيات

### قرارات صاحب القرار المُؤكَّدة (10/10 — كاملة):
| القرار | الحالة |
|--------|--------|
| M-01: مفتوح المصدر | ✅ مؤكَّد |
| M-02: 3 مستخدمين في المرحلة الأولى | ✅ مؤكَّد |
| M-03: مفاتيح API حسب المستخدم (مجاني/مدفوع) | ✅ مؤكَّد |
| M-04: macOS + Windows + Android | ✅ مؤكَّد |
| M-05: لا قاعدة بيانات مفضلة — SQLite افتراضياً | ✅ مؤكَّد |
| M-06: Telegram Bot مطلوب بالتأكيد | ✅ مؤكَّد |
| M-07: Ollama للمحلي + API للسحابي | ✅ مؤكَّد |
| M-08: نعم — متطلبات امتثال GDPR/SOC2 | ✅ مؤكَّد |
| M-09: صاحب القرار = أنت | ✅ مؤكَّد |
| M-10: deadline محدد بالتاسك | ✅ مؤكَّد |

| # | التوصية | الأولوية | الجهد |
|---|---------|----------|-------|
| 1 | نقل مفاتيح API من `.emo_settings.json` إلى `.env` | حرجة | 30 دقيقة |
| 2 | ربط `brain.py` بـ OpenRouter API الحقيقي | حرجة | 2-3 ساعات |
| 3 | تنفيذ SSE stream في `routers/chat.py` | حرجة | 3-4 ساعات |
| 4 | تفعيل المصادقة الأساسية | عالية | 4-6 ساعات |
| 5 | إنشاء Dockerfile | عالية | 2 ساعة |
| 6 | إضافة اختبارات وحدة أساسية | عالية | 1 يوم |
| 7 | ربط الأدوات بالوكلاء فعلياً | متوسطة | 2-3 أيام |
| 8 | إضافة SQLite كقاعدة بيانات | متوسطة | 1-2 يوم |
| 9 | إنشاء CI/CD pipeline | متوسطة | 1 يوم |
| 10 | إعادة هيكلة `project_tools.py` | منخفضة | 2-3 أيام |

---

**نهاية الوثيقة — الإصدار 1.0.0-DRAFT**

*هذه الوثيقة مسودة وتحتاج مراجعة وموافقة صاحب القرار قبل الانتقال لمرحلة الاستكشاف والتصميم.*

*للموافقة أو التعديل: راجع قسم "المعلومات المفقودة" (الجدول 8) وقدّم إجابات واضحة.*
