# Emo AI Orchestrator

> Multi-Agent Intelligence Orchestration System — مفتوح المصدر

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com/)
[![CI/CD](https://github.com/emo-ai/emo-ai/actions/workflows/ci.yml/badge.svg)](.github/workflows/ci.yml)
[![Tests](https://img.shields.io/badge/tests-35%20passed-brightgreen)](tests/)

نظام تنسيق ذكي متعدد الوكلاء يعمل كطبقة وسيطة بين المستخدم ونماذج الذكاء الاصطناعي المختلفة. يدعم النماذج السحابية (OpenRouter, Groq, Gemini) والمحلية (Ollama).

## المزايا

- 🤖 **وكلاء متعددون**: Planner, Coder, Writer, Researcher (متصلون بـ LLM)
- 🌐 **4 مزودين LLM**: OpenRouter, Groq, Gemini (API) + Ollama (محلي)
- 💬 **بث مباشر**: SSE للبث المباشر لتقدم المهام
- 🛠️ **30+ أداة**: DevOps, GitHub, Supabase, Firebase, Project Intelligence (متصلة بالوكلاء)
- 🌍 **عربي/إنجليزي**: واجهة ثنائية اللغة مع RTL/LTR
- 📱 **متعدد المنصات**: macOS + Windows + Android (web-responsive)
- 🔒 **آمن**: مفاتيح API في `.env`، مصادقة JWT + bcrypt
- 📲 **Telegram Bot**: دردشة عبر Telegram
- 🖥️ **System Tray**: pystray (cross-platform)
- 🐳 **Docker**: جاهز للنشر
- ✅ **35 اختبار**: تغطية شاملة للمكونات الأساسية
- 🔧 **CI/CD**: GitHub Actions (tests + Docker + security)
- 📋 **Logging**: نظام تسجيل شامل مع audit trail
- 🚀 **Setup Script**: تثبيت تلقائي بنقرة واحدة

## التثبيت السريع

### الطريقة 1: سكربت الإعداد التلقائي (موصى به)
```bash
python setup.py
```

### الطريقة 2: يدوياً
```bash
# 1. استنساخ المشروع
git clone <repo-url> && cd Emo-AI

# 2. إنشاء بيئة افتراضية
python3 -m venv venv && source venv/bin/activate

# 3. تثبيت المتطلبات
pip install -r requirements.txt

# 4. إعداد المتغيرات البيئية
cp .env.example .env
# عدّل .env بمفاتيحك

# 5. تشغيل الخادم
python main.py
# → http://localhost:8080
```

## التشغيل مع Ollama (محلي ومجاني)

```bash
# تثبيت Ollama
brew install ollama
ollama serve &
ollama pull llama3.2

# تشغيل EMO AI
LLM_PROVIDER=ollama python main.py
```

## التشغيل مع Docker

```bash
docker build -t emo-ai .
docker run -p 8080:8080 --env-file .env emo-ai
```

## الاختبارات

```bash
python -m pytest tests/ -v
# → 30 passed, 1 skipped
```

## الهيكل

```
Emo-AI/
├── main.py              # نقطة الدخول
├── brain.py             # واجهة LLM (4 مزودين)
├── agent.py             # نظام الوكلاء (4 وكلاء)
├── tools.py             # Tool base class + Registry
├── core/
│   ├── db.py            # SQLite manager
│   ├── state.py         # حالة التطبيق
│   ├── task_manager.py  # إدارة المهام
│   └── context_builder.py # بناء السياق
├── routers/
│   ├── chat.py          # Chat API + SSE
│   └── stream.py        # SSE streaming
├── templates/           # واجهة الويب
├── tests/               # اختبارات وحدة
└── docs/                # وثائق المشروع
```

## التوثيق

| المستند | الوصف |
|---------|-------|
| [DEVELOPER.md](DEVELOPER.md) | مرجع المطورين الشامل |
| [docs/REQUIREMENTS_UNDERSTANDING.md](docs/REQUIREMENTS_UNDERSTANDING.md) | وثيقة المتطلبات |
| [docs/EXPLORATION_REPORT.md](docs/EXPLORATION_REPORT.md) | تقرير الاستكشاف |
| [docs/ARCHITECTURE_DESIGN.md](docs/ARCHITECTURE_DESIGN.md) | التصميم المعماري |
| [docs/EXECUTION_REPORT.md](docs/EXECUTION_REPORT.md) | تقرير التنفيذ |
| [docs/core_features_api.json](docs/core_features_api.json) | مواصفات API |

## الترخيص

MIT License — راجع [LICENSE](LICENSE) للمزيد.
