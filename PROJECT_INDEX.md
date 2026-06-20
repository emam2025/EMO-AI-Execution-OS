# 📚 EMO AI — Project Index

> فهرس شامل للمشروع — دليل سريع لأي مطور جديد

---

## نظرة عامة

| الخاصية | القيمة |
|---------|--------|
| **الاسم** | EMO AI Execution OS |
| **الوصف** | نظام تشغيل ذكاء اصطناعي للتنفيذ الموزع |
| **الإصدار الحالي** | v1.0.0 (RC16.6) |
| **حالة المشروع** | Production-Ready |
| **اللغة** | Python 3.14+ |
| **الإطار** | FastAPI |
| **الترخيص** | MIT |

---

## هيكل المشروع

```
Emo-AI/
├── 📄 main.py                    # نقطة الدخول الرئيسية
├── 📄 brain.py                   # واجهة LLM (4 مزودين)
├── 📄 agent.py                   # نظام الوكلاء
├── 📄 requirements.txt           # المتطلبات
├── 📄 Dockerfile                 # صورة Docker
├── 📄 docker-compose.yml         # تكوين Docker
├── 📄 .env.example               # قالب المتغيرات البيئية
├── 📄 README.md                  # التوثيق الرئيسي
├── 📄 CONTRIBUTING.md            # دليل المساهمة
├── 📄 PROJECT_INDEX.md           # هذا الملف
├── 📄 DEVELOPER.md               # الدليل التقني
├── 📄 LICENSE                    # الترخيص
├── 📄 VERSION                    # إصدار المشروع
│
├── 📁 core/                      # النواة الأساسية (417 ملف)
├── 📁 routers/                   # طبقة API (14 ملف)
├── 📁 tests/                     # الاختبارات (178 ملف)
├── 📁 docs/                      # التوثيق (33 ملف)
├── 📁 scripts/                   # السكريبتات (132 ملف)
├── 📁 releases/                  # الإصدارات (1172 ملف)
├── 📁 middleware/                 # طبقة الوسيط
├── 📁 simulation_lab/            # مختبر المحاكاة
├── 📁 .github/workflows/         # CI/CD
└── 📁 helm/                      # Kubernetes Helm
```

---

## الملفات الرئيسية

| الملف | الوصف | الأهمية |
|-------|-------|---------|
| `main.py` | نقطة الدخول — FastAPI app | ⭐⭐⭐ |
| `brain.py` | واجهة LLM — 4 مزودين (OpenRouter, Groq, Gemini, Ollama) | ⭐⭐⭐ |
| `agent.py` | نظام الوكلاء المتعددين | ⭐⭐⭐ |
| `requirements.txt` | قائمة المتطلبات | ⭐⭐ |
| `Dockerfile` | بناء صورة Docker | ⭐⭐ |
| `.env.example` | قالب المتغيرات البيئية | ⭐⭐ |
| `DEVELOPER.md` | الدليل التقني الشامل | ⭐⭐⭐ |
| `VERSION` | إصدار المشروع الحالي | ⭐ |

---

## core/ — النواة الأساسية

> **417 ملف Python** — 61 مجلد فرعي

### المجلدات الرئيسية

| المجلد | عدد الملفات | الوصف |
|--------|------------|-------|
| `core/runtime/` | 201 | محرك التنفيذ和服务 |
| `core/interfaces/` | 30 | الواجهات والبروتوكولات |
| `core/codegraph/` | 25 | تحليل الكود |
| `core/control_plane/` | 12 | طبقة التحكم |
| `core/enterprise/` | 11 | الميزات المؤسسية |
| `core/observability/` | 9 | المراقبة والتتبع |
| `core/security/` | 8 | الأمان |
| `core/readiness/` | 7 | الاستعداد للإنتاج |
| `core/memory/` | 7 | الذاكرة |
| `core/devex/` | 7 | تجربة المطور |
| `core/composition/` | 7 | تجميع الخدمات |
| `core/canon/` | 7 | القواعد المعمارية |
| `core/orchestration/` | 6 | التنسيق |
| `core/models/` | 4 | النماذج |
| `core/infra/` | 4 | البنية التحتية |

### المجلدات الفرعية الأخرى

```
core/
├── adapters/          # المحولات
├── agent_teams/       # فرق الوكلاء
├── agents/            # الوكلاء
├── applications/      # التطبيقات
├── autonomous_control/ # التحكم المستقل
├── autonomy/          # الاستقلالية
├── canvas/            # اللوحة
├── chaos/             # الهندسة الفوضوية
├── cli/               # واجهة سطر الأوامر
├── cloud/             # السحابة
├── cognition/         # الإدراك
├── command_center/    # مركز الأوامر
├── communication_hub/ # مركز الاتصال
├── connector_cert/    # شهادة الموصلات
├── connectors/        # الموصلات
├── data_fabric/       # قماش البيانات
├── db.py              # قاعدة البيانات
├── deployment/        # النشر
├── devops/            # DevOps
├── digital_twin_platform/ # التوأم الرقمي
├── digital_twin_v2/   # التوأم الرقمي v2
├── enterprise_memory/ # ذاكرة المؤسسة
├── execution_governor/ # حاكم التنفيذ
├── generative_ui/     # الواجهة التوليدية
├── hardening/         # التقوية
├── human_governance/  # الحوكمة الإنسانية
├── human_twin/        # التوأم البشري
├── industry_framework/ # إطار الصناعة
├── industry_profiles/ # ملفات القطاعات
├── knowledge_graph/   # رسم المعرفة
├── knowledge_os/      # نظام المعرفة
├── marketplace/       # سوق الإضافات
├── projectos/         # نظام المشاريع
├── recovery/          # الاسترداد
├── release/           # الإصدار
├── sandbox/           # صندوق الرمل
├── security/          # الأمان
├── skill_factory/     # مصنع المهارات
├── threat_intel/      # استخبارات التهديدات
├── ui_marketplace/    # سوق الواجهات
├── ui_schema/         # مخطط الواجهة
├── workflow_os/       # نظام سير العمل
├── workflow_runtime_v2/ # بيئة سير العمل v2
└── workspace_intelligence/ # ذكاء مساحة العمل
```

---

## routers/ — طبقة API

> **14 ملف** — FastAPI Routers

| الملف | الوصف |
|-------|-------|
| `routers/auth.py` | المصادقة (signup, login, verify) |
| `routers/runtime_api.py` | API التنفيذ |
| `routers/project.py` | إدارة المشاريع |
| `routers/settings.py` | الإعدادات |
| `routers/chat.py` | الدردشة |
| `routers/conversations.py` | المحادثات |
| `routers/history.py` | السجل |
| `routers/tasks.py` | المهام |
| `routers/ai.py` | الذكاء الاصطناعي |
| `routers/stream.py` | البث المباشر |
| `routers/observability.py` | المراقبة |
| `routers/e2e.py` | الاختبارات الشاملة |

---

## tests/ — الاختبارات

> **178 ملف** — اختبارات شاملة

### تصنيف الاختبارات

| الفئة | عدد الملفات | الوصف |
|--------|------------|-------|
| `tests/test_*.py` | ~50 | اختبارات وحدات |
| `tests/phase*.py` | ~80 | اختبارات المراحل |
| `tests/red_team/` | ~5 | اختبارات الأمان |
| `tests/test_security_*.py` | ~10 | اختبارات أمان حرجة |
| `tests/test_workflow_*.py` | ~8 | اختبارات سير العمل |

### تشغيل الاختبارات

```bash
# جميع الاختبارات
python -m pytest tests/ -v

# اختبارات محددة
python -m pytest tests/test_service_isolation.py -v

# مع التغطية
python -m pytest tests/ --cov=core --cov-report=html
```

---

## docs/ — التوثيق

> **33 ملف** — توثيق شامل

### الوثائق الرئيسية

| الملف | الوصف |
|-------|-------|
| `docs/INDEX.md` | فهرس التوثيق |
| `docs/DEVELOPER.md` | الدليل التقني |
| `docs/architecture/` | التصميم المعماري |
| `docs/api/` | مرجع API |
| `docs/sdk/` | دليل المطور |
| `docs/security/` | النموذج الأمني |
| `docs/deployment/` | أدلة النشر |
| `docs/testing.md` | سجل الاختبارات |

---

## scripts/ — الأتمتة

> **132 ملف** — سكريبتات مساعدة

### تصنيف السكريبتات

| الفئة | الوصف |
|-------|-------|
| `scripts/setup/` | إعداد البيئة |
| `scripts/deploy/` | نشر المشروع |
| `scripts/test/` | تشغيل الاختبارات |
| `scripts/build/` | بناء المشروع |
| `scripts/ci/` | أتمتة CI/CD |

---

## releases/ — الإصدارات

> **1172 ملف** — إصدارات المشروع

### الإصدارات الرئيسية

| الإصدار | الحالة | الوصف |
|---------|--------|-------|
| RC12 | ✅ COMPLETED | Foundation |
| RC13 | ✅ COMPLETED | Cognitive Layer |
| RC14 | ✅ COMPLETED | Workflow Intelligence |
| RC15 | ✅ COMPLETED | Enterprise Platform |
| RC16 | ✅ COMPLETED | Generative Interface OS |
| RC16.6 | ✅ COMPLETED | Knowledge Freeze |
| RC17 | 📋 PLANNED | Domain Intelligence |

---

## إحصائيات المشروع

| الإحصائية | القيمة |
|-----------|--------|
| **إجمالي ملفات Python** | 742 |
| **إجمالي أسطر الكود** | 161,371 |
| **ملفات core/** | 417 |
| **ملفات routers/** | 14 |
| **ملفات tests/** | 178 |
| **ملفات docs/** | 33 |
| **ملفات scripts/** | 132 |
| **ملفات releases/** | 1,172 |
| **عدد الاختبارات** | 1,667+ |
| **نسبة النجاح** | 100% |
| **عدد endpoints** | 290+ |

---

## روابط سريعة

### الوثائق المهمة

- 📖 [README.md](README.md) — نظرة عامة
- 🔧 [DEVELOPER.md](DEVELOPER.md) — الدليل التقني
- 🏗️ [docs/architecture/](docs/architecture/) — التصميم المعماري
- 📡 [docs/api/](docs/api/) — مرجع API
- 🔒 [docs/security/](docs/security/) — الأمان
- 🚀 [docs/deployment/](docs/deployment/) — النشر
- 🧪 [docs/testing.md](docs/testing.md) — الاختبارات
- 🤝 [CONTRIBUTING.md](CONTRIBUTING.md) — دليل المساهمة

### السكريبتات المهمة

```bash
# إعداد البيئة
python setup.py

# تشغيل الخادم
python main.py

# اختبارات سريعة
python -m pytest tests/test_service_isolation.py -v

# التحقق من القواعد المعمارية
python -m core.tools.emo_guard --ci
```

### أوامر شائعة

```bash
# بناء Docker
docker build -t emo-ai:latest .

# تشغيل الحاوية
docker run -p 8080:8080 --env-file .env emo-ai:latest

# نشر Kubernetes
helm install emo-ai ./helm/emo-ai
```

---

**آخر تحديث**: 2026-06-12
