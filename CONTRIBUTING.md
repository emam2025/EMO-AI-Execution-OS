# 🤝 دليل المساهمة في EMO AI

مرحباً بك في دليل المساهمة في EMO AI. يرجى قراءة هذا الدليل بالكامل قبل البدء في أي مساهمة.

---

## 📋 قبل البدء

قبل البدء في المساهمة، تأكد من فهمك للبنية المعمارية للمشروع:

- 📖 اقرأ [DEVELOPER.md](DEVELOPER.md) — الدليل التقني الشامل
- 🏗️ اقرأ [ARCHITECTURE_DESIGN.md](docs/architecture/) — التصميم المعماري
- 📐 اقرأ [SOURCE_OF_TRUTH.md](docs/SOURCE_OF_TRUTH.md) — ترتيب الثقة وسياسة التوثيق
- 🗺️ اقرأ [REPOSITORY_STRUCTURE_MAP.md](docs/REPOSITORY_STRUCTURE_MAP.md) — خريطة هيكل المستودع
- ⚖️ فهم **Architecture Canon** (LAW 1-27) — القواعد المعمارية الصارمة

> ⚠️ **تحذير صارم**: عدم فهم القواعد المعمارية قد يؤدي إلى رفض Pull Request الخاص بك.

---

## 🚀 إعداد بيئة التطوير

### المتطلبات الأساسية

- Python 3.14+
- pip (أحدث إصدار)
- git

### خطوات الإعداد

```bash
# 1. استنساخ المشروع (Fork أولاً)
git clone https://github.com/YOUR-USERNAME/emo-ai.git
cd emo-ai

# 2. إنشاء بيئة افتراضية
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
# أو
venv\Scripts\activate  # Windows

# 3. تثبيت المتطلبات
pip install -r requirements.txt

# 4. إعداد المتغيرات البيئية
cp .env.example .env
# عدّل .env بمفاتيحك الخاصة

# 5. تشغيل الاختبارات للتأكد من صحة البيئة
python -m pytest tests/ -v
```

---

## 📝 معايير الكود

### نمط الكتابة (Code Style)

- **PEP 8**: اتبع معايير Python الرسمية
- **Type Hints**: استخدم type annotations لجميع الدوال
- **Docstrings**: استخدم Google Style Docstrings

```python
def example_function(param1: str, param2: int) -> bool:
    """وصف مختصر للدالة.

    Args:
        param1: وصف param1.
        param2: وصف param2.

    Returns:
        bool: وصف القيمة المُعادة.

    Raises:
        ValueError: إذا كان param1 فارغاً.
    """
    pass
```

### قواعد صارمة

- ❌ **لا circular imports** — استخدم TYPE_CHECKING للاستيراد الدائري
- ❌ **لا hardcoded secrets** — استخدم متغيرات البيئة
- ✅ **Test coverage ≥ 80%** — كل كود جديد يحتاج اختبارات
- ✅ **لا تعديل core/runtime/** بدون مراجعة مسبقة

---

## 🏗️ القواعد المعمارية (CRITICAL)

> ⚠️ **هذه القواعد إلزامية.** أي انتهاك يعني رفض الـ PR فوراً.

### LAW 1: ExecutionEngine Isolation

```python
# ✅ الصحيح
from core.execution_governor import ExecutionGovernor

# ❌ الخطأ
from core.runtime.execution_engine import ExecutionEngine  # FORBIDDEN
```

### LAW 13: CompositionRoot Only

```python
# ✅ الصحيح
def create_service() -> MyService:
    return MyService(dep1, dep2)

# ❌ الخطأ
service = MyService()  # FORBIDDEN outside CompositionRoot
```

### LAW 14-16: CodeGraph Boundaries

- لا تعديل `core/interfaces/` مباشرة بدون اطلاع المشرف
- لا إضافة imports من `core.runtime.*` في `core/interfaces/*`

### LAW 20-22: Failure Propagation

- كل service يجب أن يكون له `health_check()` method
- لا تarkan exceptions من `health_check()`

### LAW 23-27: Service Ownership

- كل خدمة مسؤولة فقط عن نطاقها
- لا cross-service calls مباشرة

### القواعد الإضافية

- ** LAW 10**: لا تعتمد على أن Workers موثوقين
- **LAW 28**: لا تعتمد على تشغيل cron jobs
- **LAW 35-37**: لا محتوى عربي في core/

> 📖 راجع [DEVELOPER.md](DEVELOPER.md) للتفاصيل الكاملة لكل قانون.

---

## 🧪 الاختبارات

### تشغيل الاختبارات

```bash
# تشغيل جميع الاختبارات
python -m pytest tests/ -v

# تشغيل اختبارات محددة
python -m pytest tests/test_workflow_v2.py -v

# مع تقرير التغطية
python -m pytest tests/ --cov=core --cov-report=html

# فتح تقرير التغطية
open htmlcov/index.html
```

### التحقق من عدم انتهاك العزل (إلزامي)

```bash
# تشغيل emo-guard للتحقق من القواعد المعمارية
python -m core.tools.emo_guard --ci

# أو
emo-guard --update-snapshot
```

### معايير القبول للاختبارات

- ✅ جميع الاختبارات الحالية تبقى PASS
- ✅ لا اختبارات جديدة تفشل
- ✅ Test coverage ≥ 80% للكود الجديد
- ✅ لا وجود لـ `print()` في اختبارات الإنتاج

---

## 📤 عملية الـ Pull Request

### 1. Fork و Clone

```bash
# Fork المشروع من GitHub
# ثم clone
git clone https://github.com/YOUR-USERNAME/emo-ai.git
cd emo-ai
```

### 2. إنشاء فرع جديد

```bash
# تأكد من أنك على main
git checkout main

# أنشئ فرع جديد
git checkout -b feature/your-feature-name

# أو
git checkout -b fix/bug-description
```

### 3. كتابة الكود والاختبارات

```python
# مثال: إضافة feature جديد

# 1. أضف الكود في المكان المناسب
# 2. أضف اختبارات جديدة
# 3. تأكد من أن جميع الاختبارات تمر
```

### 4. التحقق قبل الـ Commit

```bash
# تشغيل جميع الاختبارات
python -m pytest tests/ -v

# التحقق من القواعد المعمارية
python -m core.tools.emo_guard --ci

# التحقق من التغطية
python -m pytest tests/ --cov=core --cov-report=term-missing
```

### 5. الـ Commit

```bash
# أضف الملفات
git add .

# اكتب رسالة وصفية
git commit -m "feat: add health check endpoint for scheduler

- Add health_check() method to ExecutionScheduler
- Returns dict with status, uptime, active_tasks, queue_depth
- Never raises exceptions (wrapped in try/except)
- Add unit tests for health_check

Refs: #123"
```

### 6. الـ Push و فتح PR

```bash
# Push للفرع
git push origin feature/your-feature-name

# فتح Pull Request من GitHub
# - العنوان وصفي
# - الوصف يوضح ماذا فعلت ولماذا
# - ربط Issue إذا وجد
```

### 7. مراجعة الـ PR

- ⏳ انتظر مراجعة المشرف
- 🔧 عالج أي ملاحظات
- ✅ تأكد من مرور جميع الاختبارات في CI

---

## 🚫 ما لا يجب فعله

### ❌ ممنوعات صارمة

| الفعل | السبب | البديل |
|-------|-------|--------|
| Cross-layer imports | انتهاك LAW 1 | استخدم interfaces |
| تعديل `core/runtime/*` | Core Freeze | راجج المشرف |
| حذف اختبارات | تراجع التغطية | أعد كتابتها |
| Hardcoded secrets | ثغرة أمنية | استخدم .env |
| `print()` في الإنتاج | تسريب بيانات | استخدم `logging` |
| تعديل `core/interfaces/*` | انتهاك LAW 14-16 | راجج المشرف |
| إضافة `from core.runtime.*` في interfaces | انتهاك LAW 14-16 | استخدم TYPE_CHECKING |

### ❌ لا تفعل

```python
# ❌ لا تفعل هذا
from core.runtime.services.scheduler import ExecutionScheduler

# ❌ لا تفعل هذا
API_KEY = "sk-1234567890"

# ❌ لا تفعل هذا
print(f"Debug: {variable}")

# ❌ لا تفعل هذا
def test_something():
    assert True  # اختبار فارغ
```

### ✅ افعل هذا بدلاً منه

```python
# ✅ استخدم TYPE_CHECKING
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from core.runtime.services.scheduler import ExecutionScheduler

# ✅ استخدم متغيرات البيئة
import os
API_KEY = os.getenv("API_KEY")

# ✅ استخدم logging
import logging
logger = logging.getLogger(__name__)
logger.debug("Debug: %s", variable)

# ✅ اكتب اختبارات حقيقية
def test_something():
    result = my_function()
    assert result == expected_value
```

---

## 📞 التواصل

### قنوات التواصل

- 🐛 **GitHub Issues**: للأخطاء والمطالبات
- 💬 **GitHub Discussions**: للأسئلة العامة
- 📧 **Email**: للتواصل المباشر

###_reporting Security Issues

> ⚠️ **لا تفتح Issue عامة لثغرات أمنية.**

أرسل بريد إلكتروني إلى: security@emo-ai.dev

---

## 🏆 تقدير المساهمين

جميع المساهمين سيظهرون في قائمة المساهمين في README.md.

---

## 📄 الترخيص

بالمشاركة في هذا المشروع، أنت توافق على أن عملك سيكون مرخضاً تحت [MIT License](LICENSE).

---

**شكراً لمساهمتك في EMO AI! 🚀**
