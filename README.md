# 🧠 EMO AI Execution OS

**نظام تشغيل ذكاء اصطناعي للتنفيذ الموزع**

[![Python](https://img.shields.io/badge/Python-3.14+-blue.svg)](https://python.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.136+-green.svg)](https://fastapi.tiangolo.com)
[![Tests](https://img.shields.io/badge/Tests-1667%20PASS-brightgreen.svg)](./tests/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)

---

## 📖 نظرة عامة

EMO AI ليس مجرد مساعد ذكاء اصطناعي أو إطار عمل للوكلاء. إنه **نظام تشغيل كامل للتنفيذ الذكي** مصمم لتشغيل سير العمل المعقدة، إدارة الوكلاء المتعددين، والتكامل مع الأنظمة الصناعية والمؤسسية.

### 🎯 ما يميز EMO AI؟

- **🏭 جاهز للإنتاج الصناعي**: محاكاة كاملة لقطاعات المياه، الطاقة، التصنيع، وERP
- **🔒 أمان مؤسسي**: RBAC، ABAC، Guardian Pipeline، تشفير AES-256
- **🌐 موزع بالكامل**: Service Mesh، Lease-based Execution، Distributed Scheduler
- **🧩 قابل للتوسع**: Plugin Architecture، Connector Certification Pipeline
- **📊 observable بالكامل**: Telemetry، Tracing، Metrics، Audit Logs

---

## 🚀 Quick Start

### التثبيت

```bash
# 1. استنساخ المشروع
git clone https://github.com/emo-ai/emo-ai.git
cd emo-ai

# 2. إنشاء بيئة افتراضية
python3 -m venv venv
source venv/bin/activate  # macOS/Linux

# 3. تثبيت المتطلبات
pip install -r requirements.txt

# 4. إعداد المتغيرات البيئية
cp .env.example .env
# عدّل .env بمفاتيح API الخاصة بك

# 🧠 EMO AI Execution OS
# 5. تشغيل الخادم
python main.py
# → Server running on http://localhost:8080
```

### التشغيل السريع

```python
from core.workflow_runtime_v2 import WorkflowV2, WorkflowNode, NodeType

# إنشاء workflow بسيط
wf = WorkflowV2(name="My First Workflow")
wf.add_node(WorkflowNode(node_id="n1", node_type=NodeType.STANDARD, name="Step 1"))
wf.add_node(WorkflowNode(node_id="n2", node_type=NodeType.HUMAN_GATE, name="Approval"))

# تنفيذ
wf.start()
wf.execute_node("n1")
wf.execute_node("n2")
wf.complete()
```

---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Multi-Agent Layer                         │
│  Planner Agent • Critic Agent • Optimizer Agent             │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│                  AI Execution OS                             │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐     │
│  │ Workflow V2  │  │  Knowledge   │  │   Digital    │     │
│  │   Engine     │  │     OS       │  │    Twin      │     │
│  └──────────────┘  └──────────────┘  └──────────────┘     │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│                  Distributed Runtime                         │
│  Service Mesh • Lease Manager • Scheduler • EventBus        │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│               Governance & Security                          │
│  RBAC • ABAC • Guardian • Audit Trail • Encryption          │
└─────────────────────────────────────────────────────────────┘
```

---

## 🧩 المكونات الرئيسية

| المكون | الوصف | الحالة |
|--------|-------|--------|
| Workflow V2 | محرك سير العمل مع 6 أنواع عقد | ✅ Production |
| Knowledge OS | إدارة المعرفة مع RAG وGraph | ✅ Production |
| Digital Twin | محاكاة القطاعات الصناعية | ✅ Production |
| Service Mesh | اتصال موزع بين الخدمات | ✅ Production |
| Security Gateway | بوابة أمان موحدة | ✅ Production |

---

## 📡 API Endpoints

### Authentication

```
POST /api/auth/signup        — إنشاء حساب
POST /api/auth/login         — تسجيل دخول
GET  /api/auth/verify        — التحقق من Token
```

### Workflows

```
POST /api/runtime/submit                — تنفيذ workflow
POST /api/runtime/{ticket_id}/resume    — استئناف
POST /api/runtime/{ticket_id}/cancel    — إلغاء
GET  /api/runtime/{ticket_id}/observe   — مراقبة
```

### Knowledge

```
POST /api/projectos/knowledge              — إنشاء قاعدة معرفة
GET  /api/projectos/knowledge              — قائمة قواعد المعرفة
POST /api/projectos/knowledge/documents    — إضافة وثيقة
```

### Digital Twin

```
POST /api/digital-twin/entities    — إنشاء كيان
GET  /api/digital-twin/hierarchy   — التسلسل الهرمي
GET  /api/digital-twin/stats       — إحصائيات
```

📚 **Full API Documentation**: docs/api/

---

## 🧪 Testing

```bash
# تشغيل جميع الاختبارات
python -m pytest tests/ -v

# تشغيل مجموعة محددة
python -m pytest tests/test_workflow_v2.py -v

# مع التغطية
python -m pytest tests/ --cov=core --cov-report=html
```

**Test Coverage**: 1667+ اختبار، 100% Pass Rate

---

## 📦 Deployment

### Docker

```bash
# بناء الصورة
docker build -t emo-ai:latest .

# تشغيل الحاوية
docker run -p 8080:8080 --env-file .env emo-ai:latest
```

### Kubernetes

```bash
# تثبيت Helm chart
helm install emo-ai ./helm/emo-ai

# التحقق من الحالة
kubectl get pods -l app=emo-ai
```

📚 **Deployment Guides**: docs/deployment/

---

## 🤝 Contributing

نرحب بالمساهمات! يرجى قراءة دليل المساهمة قبل البدء.

### خطوات المساهمة

1. Fork المشروع
2. إنشاء فرع للميزة (`git checkout -b feature/amazing-feature`)
3. Commit التغييرات (`git commit -m 'Add amazing feature'`)
4. Push للفرع (`git push origin feature/amazing-feature`)
5. فتح Pull Request

---

## 📄 License

هذا المشروع مرخص تحت MIT License

---

## 📞 Support

- **Documentation**: docs/
- **Issues**: GitHub Issues
- **Discussions**: GitHub Discussions

---

## 🌟 Acknowledgments

- FastAPI team for the amazing framework
- Python community for continuous support
- All contributors who made this project possible

---

**Made with ❤️ by the EMO AI Team**
