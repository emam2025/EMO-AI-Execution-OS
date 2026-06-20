# 🏗️ EMO AI — Architecture Design Document

> وثيقة التصميم المعماري الشاملة — المرجع النهائي لبنية النظام

---

## 1. Executive Summary

### وصف موجز للنظام

EMO AI هو **نظام تشغيل ذكاء اصطناعي للتنفيذ الموزع** (AI Execution OS) مصمم لتشغيل سير العمل المعقدة، إدارة الوكلاء المتعددين، والتكامل مع الأنظمة الصناعية والمؤسسية.

### الرؤية النهائية

**Industrial AI Execution OS** — نظام تشغيل ذكاء اصطناعي جاهز للإنتاج الصناعي، يدعم قطاعات المياه، الطاقة، التصنيع، وERP.

### الحالة الحالية

| الخاصية | القيمة |
|---------|--------|
| **الإصدار** | RC16.6.1 (Knowledge Freeze) |
| **التاريخ** | 2026-06-12 |
| **الحالة** | Production-Ready |
| **عدد الملفات** | 657+ |
| **عدد الاختبارات** | 2,430+ |
| **نسبة النجاح** | 100% |

---

## 2. System Overview

### الطبقات الرئيسية

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 9: User Interface                                     │
│  (FastAPI + WebSocket + SSE)                                 │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│  Layer 8: Application Services                               │
│  (Auth, Workflows, Knowledge, Digital Twin)                  │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│  Layer 7: Orchestration                                      │
│  (Workflow V2, Human Gate, Loop, Parallel)                   │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│  Layer 6: Execution                                          │
│  (ExecutionGovernor, RiskAnalyzer, SimulationEngine)         │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│  Layer 5: Service Mesh                                       │
│  (Scheduler, Dispatcher, RetryHandler, StateStore, Lease)    │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│  Layer 4: Runtime                                            │
│  (EventBus, CapGuard, HealthCheck, Tracer)                   │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│  Layer 3: Infrastructure                                     │
│  (FileSystem, Network, Database, Cache)                      │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│  Layer 2: Security                                           │
│  (RBAC, ABAC, Guardian, Encryption)                          │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│  Layer 1: Canon (Rules)                                      │
│  (LAW 1-27, RULE 1-10)                                       │
└─────────────────────────────────────────────────────────────┘
```

### المكونات الأساسية

| المكون | الطبقة | الوصف |
|--------|--------|-------|
| **Security OS** | Layer 2 | RBAC, ABAC, Guardian |
| **Workflow OS** | Layer 7 | WorkflowV2 Engine |
| **Knowledge OS** | Layer 3 | Knowledge Entity, Version Control |
| **Autonomy** | Layer 6 | Agent Runtime, Decision Engine |
| **Execution Governor** | Layer 6 | L0-L4 Modes, Risk Analyzer |
| **Digital Twin v2** | Layer 6 | Predictive, Prescriptive Engines |
| **Connector Certification** | Layer 3 | 4-Stage Pipeline |
| **Enterprise Apps** | Layer 8 | Finance, HR, Operations |
| **Generative UI** | Layer 9 | Schema Engine, Component Registry |
| **Adaptive Workspace** | Layer 9 | Workspace Engine |
| **Command Center** | Layer 8 | Supervisor, Action Pipeline |

### العلاقات بين المكونات

```
User Request
    ↓
Auth (JWT) → RBAC → ABAC → Guardian
    ↓
Execution Governor (Risk + Simulation)
    ↓
Service Mesh (Scheduler → Dispatcher → Worker)
    ↓
StateStore (Checkpoint)
    ↓
Audit Trail (SHA-256)
```

---

## 3. Architecture Layers

### 3.1 Security OS (RC12.5+)

**المساهمة**: RBAC, ABAC, Guardian, Decision Gateway, Identity Provider

#### المكونات

| المكون | الوصف |
|--------|-------|
| **RBAC** | Role-Based Access Control (7 أدوار) |
| **ABAC** | Attribute-Based Access Control |
| **Guardian** | Injection Detection Pipeline |
| **Decision Gateway** | Centralized Authorization |
| **Identity Provider** | User Management |

#### Roles

| الدور | الصلاحيات |
|-------|----------|
| `admin` | كل الصلاحيات |
| `operator` | تشغيل + مراقبة |
| `developer` | تطوير + اختبار |
| `viewer` | قراءة فقط |
| `auditor` | مراجعة + تدقيق |
| `guest` | صلاحيات محدودة |
| `service` | صلاحيات خدمية |

### 3.2 Workflow OS (RC15 + RC16.5)

**المساهمة**: WorkflowV2 Engine, 6 Node Types, Compensation & Parallel

#### Node Types

| النوع | الوصف |
|-------|-------|
| `STANDARD` | تنفيذ عادي |
| `HUMAN_GATE` | انتظار موافقة بشرية |
| `PARALLEL` | تنفيذ متوازي |
| `LOOP` | تكرار |
| `COMPENSATION` | تعويض |
| `CONDITIONAL` | شرطي |

#### Execution Modes

- **Sequential**: تنفيذ تسلسلي
- **Parallel**: تنفيذ متوازي
- **Dynamic**: تنفيذ ديناميكي

### 3.3 Knowledge OS (RC16.3)

**المساهمة**: Knowledge Entity, Version Control, Audit Log

#### المكونات

| المكون | الوصف |
|--------|-------|
| **Knowledge Entity** | كيان المعرفة |
| **Version Control** | التحكم بالإصدارات |
| **Audit Log** | سجل التدقيق |
| **Conflict Resolver** | حل التعارضات |
| **RAG Engine** | محرك الاسترجاع المعزز |

### 3.4 Autonomy (RC16.4)

**المساهمة**: Agent Runtime, Decision Engine, Execution Governor

#### المكونات

| المكون | الوصف |
|--------|-------|
| **Agent Runtime** | بيئة تشغيل الوكيل |
| **Decision Engine** | محرك القرارات |
| **Action Planner** | مخطط الإجراءات |
| **Recovery Manager** | مدير الاسترداد |

### 3.5 Execution Governor (RC16.5)

**المساهمة**: L0-L4 Modes, Risk Analyzer, Simulation Engine

#### Execution Modes

| الوضع | الوصف |
|-------|-------|
| **L0** | Direct Execution (منخفض المخاطر) |
| **L1** | Validated Execution (مخاطرة منخفضة) |
| **L2** | Supervised Execution (مخاطرة متوسطة) |
| **L3** | Restricted Execution (مخاطرة عالية) |
| **L4** | Blocked Execution (مخاطرة حرجة) |

#### المكونات

| المكون | الوصف |
|--------|-------|
| **Risk Analyzer** | محلل المخاطر |
| **Simulation Engine** | محرك المحاكاة |
| **Approval Gate** | بوابة الموافقة |

### 3.6 Digital Twin v2 (RC16.5)

**المساهمة**: Predictive Engine, Prescriptive Engine

#### Engines

| المحرك | الوصف |
|--------|-------|
| **Predictive** | توقع الأحداث المستقبلية |
| **Prescriptive** | اقتراح الإجراءات |
| **Descriptive** | وصف الحالة الحالية |

#### Supported Sectors

- 🚰 Water (مياه)
- ⚡ Energy (طاقة)
- 🏭 Manufacturing (تصنيع)
- 🏢 Enterprise (مؤسسات)

### 3.7 Connector Certification (RC16.5)

**المساهمة**: 4-Stage Pipeline, 5 Certification Levels

#### Pipeline

```
Stage 1: Validation → Stage 2: Security Scan → Stage 3: Integration Test → Stage 4: Certification
```

#### Certification Levels

| المستوى | الوصف |
|---------|-------|
| **Bronze** | أساسي |
| **Silver** | متوسط |
| **Gold** | متقدم |
| **Platinum** | احترافي |
| **Enterprise** | مؤسسي |

### 3.8 Enterprise Apps (RC16.5)

**المساهمة**: Finance, HR, Operations, Medical

#### Modules

| الوحدة | الوصف |
|--------|-------|
| **Finance** | المحاسبة والميزانية |
| **HR** | الموارد البشرية |
| **Operations** | العمليات |
| **Medical** | الطبي |

### 3.9 Generative UI (RC16-RC16.1)

**المساهمة**: Schema Engine, Component Registry

#### المكونات

| المكون | الوصف |
|--------|-------|
| **Schema Engine** | محرك المخططات |
| **Component Registry** | سجل المكونات |
| **Theme Engine** | محرك الثيمات |
| **Renderer** | العارض |

### 3.10 Adaptive Workspace (RC16.2)

**المساهمة**: Workspace Engine, Layout Planner

#### المكونات

| المكون | الوصف |
|--------|-------|
| **Workspace Engine** | محرك مساحة العمل |
| **Layout Planner** | مخطط التخطيط |
| **State Manager** | مدير الحالة |
| **Context Manager** | مدير السياق |

### 3.11 Command Center (RC15.7)

**المساهمة**: Supervisor, Action Pipeline

#### المكونات

| المكون | الوصف |
|--------|-------|
| **Supervisor** | المشرف |
| **Action Pipeline** | أنبوب الإجراءات |
| **Reports** | التقارير |
| **Dashboard** | لوحة التحكم |

---

## 4. Critical Architecture Decisions

### Decision 1: Security-First

> **القرار**: الأمان هو الأولوية القصوى في كل قرار معماري.

- لا ت妥协 على الأمان أبداً
- كل طبقة لها فحص أمان خاص بها
- Guardian Pipeline إلزامي لكل طلب

### Decision 2: No Caller-Supplied Roles

> **القرار**: لا تسمح للمستخدم بتحديد أدواره.

- الأدوار تُحدد فقط من قاعدة البيانات
- لا roles في JWT payload
- لا trusts from clients

### Decision 3: Default DENY

> **القرار**: الافتراضي هو الرفض، ويجب السماح صراحةً.

- لا صلاحيات افتراضية
- كل إذن يجب توثيقه
- Audit trail لكل قرار أمان

### Decision 4: Enterprise Control Plane

> **القرار**: بناء طبقة تحكم مؤسسية موحدة.

- إدارة المستخدمين وال_roles
- Audit Trail موحد
- Policy Enforcement Point

### Decision 5: Agent Contract Unification

> **القرار**: توحيد عقود الوكلاء.

- عقد موحد لكل Types من الوكلاء
- لا أنواع متعددة للعقود
- اختبارات صارمة لكل عقد

### Decision 6: Human Governance

> **القرار**:Human-in-the-Loop إلزامي للقرارات الحرجة.

- Human Gate لكل قرار يتجاوز عتبة معينة
- Approval Pipeline
- Simulation-before-execution

---

## 5. Architecture Canon (Laws 1-27)

### LAW 1: ExecutionEngine Isolation

> **ممنوع** الوصول المباشر إلى ExecutionEngine من أي مكان خارج CompositionRoot.

```python
# ✅ الصحيح
from core.execution_governor import ExecutionGovernor

# ❌ الخطأ
from core.runtime.execution_engine import ExecutionEngine  # FORBIDDEN
```

### LAW 2: Interface Authority

> **الواجهات** هي السلطة العليا في تحديد العقود.

- لا تعديل interfaces بدون مراجعة
- كل خدمة تتحقق من الـ interface

### LAW 3: Lease-Aware Execution

> **كل عملية** يجب أن تكون aware بالـ lease الخاص بها.

- لا تنفيذ بدون lease صالح
- لا تجاوز lease timeout

### LAW 4: Replay-Safe

> **الاستئناف** يجب أن يكون آمناً ومتكرر النتيجة.

- لا side effects during replay
- Deterministic execution

### LAW 5: Observable Execution

> **كل عملية** يجب أن تكون observable.

- Telemetry لكل operation
- Tracing لكل request
- Metrics لكل service

### LAW 6: Shared Models

> **النماذج المشتركة** تُعرَّف في مكان واحد فقط.

- لا نسخ للنماذج
- Single source of truth

### LAW 7: Deterministic Logic

> **المنطق** يجب أن يكون deterministic.

- لا عشوائية
- لا depends on external state

### LAW 8: Recoverable State

> **الحالة** يجب أن تكون recoverable.

- Checkpointing إلزامي
- State reconstruction ممكن

### LAW 9: Governance Independence

> **الحوكمة** يجب أن تكون مستقلة عن التنفيذ.

- لا تداخل بين Governance و Execution
- استقلالية القرارات

### LAW 10: Unreliable Workers

> **العمال** يعتبرون غير موثوقين افتراضياً.

- لا ثقة في العمال
- التحقق من كل نتيجة
- Timeout لكل operation

### LAW 11: No Global State

> **لا حالة عامة** في النظام.

- كل خدمة لها حالتها
- لا مشاركة حالة بين الخدمات

### LAW 12: Traceable Side Effects

> **كل side effect** يجب أن يكون traceable.

- Audit trail لكل تغيير
- Trace ID لكل operation

### LAW 13: CompositionRoot Only

> **التجميع** يحدث في مكان واحد فقط.

- لا إنشاء خدمات في أي مكان آخر
- Single composition point

### LAW 14: CodeGraph-Derived Boundaries

> **الحدود** مشتقة من CodeGraph.

- لا تعديل boundaries يدوياً
- CodeGraph هو المرجع

### LAW 15: Graph-First Refactor

> **الإعادة هيكلة** تبدأ من CodeGraph.

- تحليل CodeGraph أولاً
- ثم التعديل

### LAW 16: Risk Score > 0.8 Decomination

> **المخاطرة > 0.8** يعني decominoation إلزامي.

- فصل المكونات عالية المخاطرة
- Audit trail للقرار

### LAW 17-19: Runtime Intelligence

> **الذكاء في بيئة التنفيذ** إلزامي.

- Adaptive scheduling
- Dynamic resource allocation
- Performance optimization

### LAW 20-22: Failure Propagation

> **انتشار الأخطاء** يجب أن يكون محدداً.

- Failure Matrix لكل خدمة
- Circuit Breaker لكل service
- Retry policy محدد

### LAW 23-27: Service Ownership

> **كل خدمة** مسؤولة فقط عن نطاقها.

- لا cross-service calls مباشرة
- Communication عبر EventBus فقط
- Ownership محدد لكل خدمة

---

## 6. Service Mesh Architecture

### 5 Bounded Services

| الخدمة | المسؤولية | الملف |
|--------|----------|-------|
| **ExecutionScheduler** | ترتيب التنفيذ | `scheduler.py` |
| **Dispatcher** | توزيع المهام | `dispatcher.py` |
| **RetryHandler** | إعادة المحاولة | `retry_handler.py` |
| **StateStore** | حفظ الحالة | `state_store.py` |
| **LeaseManager** | إدارة الإيجار | `lease_manager.py` |

### Failure Propagation Matrix

| المصدر | الهدف | الإجراء |
|--------|-------|---------|
| Dispatcher | Scheduler | RETRY |
| Dispatcher | RetryHandler | CLASSIFY |
| Dispatcher | LeaseManager | RELEASE |
| Dispatcher | Core | NOTIFY |
| LeaseManager | Engine | CANCEL |
| LeaseManager | Engine | ROLLBACK |
| LeaseManager | Scheduler | REASSIGN |
| LeaseManager | StateStore | RECORD |
| StateStore | Core | DEGRADE |
| StateStore | Scheduler | BUFFER |
| StateStore | Scheduler | CONTINUE |
| StateStore | RetryHandler | DEFER |

### Isolation Tests (D8.3)

- ✅ 26/26 tests pass
- ✅ No cross-layer imports
- ✅ Service ownership enforced
- ✅ Failure propagation matrix validated

---

## 7. Security Architecture

### Authentication Flow

```
User → Login Request → JWT Generation → Token Response
                                              ↓
                                    Auth Middleware Validation
                                              ↓
                                    RBAC Check → ABAC Check
                                              ↓
                                    Guardian Pipeline
                                              ↓
                                    Execution
```

### Authorization Flow

```
Request → JWT Validation → Role Extraction → Permission Check
                                                  ↓
                                            ABAC Attributes
                                                  ↓
                                            Decision Gateway
                                                  ↓
                                            Allow / Deny
```

### Guardian Pipeline

```
Input → Injection Detection → SQL Injection Check → XSS Check
                                                        ↓
                                                  Path Traversal Check
                                                        ↓
                                                  Command Injection Check
                                                        ↓
                                                  Output Sanitization
```

### Emergency Stop

```
Emergency Signal → All Services Stop → State Checkpoint → Audit Log
```

---

## 8. Data Flow

### User Intent → Execution

```
User Intent
    ↓
Intent Parser
    ↓
Workflow Builder
    ↓
Execution Governor
    ↓
Service Mesh
    ↓
Worker Execution
    ↓
Result Collection
    ↓
User Response
```

### Event Bus Architecture

```
Event Producer → EventBus → Event Consumer 1
                          → Event Consumer 2
                          → Event Consumer N
```

### Telemetry & Observability

```
Service → Tracer → Collector → Storage → Dashboard
```

---

## 9. Deployment Architecture

### Standalone Mode

```bash
python main.py
# All services in one process
```

### Distributed Mode

```bash
# Multiple services
python main.py --service scheduler
python main.py --service dispatcher
python main.py --service retry_handler
python main.py --service state_store
python main.py --service lease_manager
```

### Cloud Mode

```bash
# Docker + Kubernetes
docker build -t emo-ai:latest .
helm install emo-ai ./helm/emo-ai
```

### Hybrid Mode

```bash
# Mix of local and cloud
# Local: Core services
# Cloud: Enterprise services
```

---

## 10. Constraints & Rules

### KERNEL FREEZE

> ⚠️ **ممنوع تعديل core/interfaces/ و core/canon/ بدون مراجعة مسبقة.**

- هذه الملفات هي "النواة" غير القابلة للتعديل
- أي تعديل يحتاج موافقة المشرف
- الاختبارات يجب أن تبقى PASS

### RC16.7 MANDATE

> 📋 **يجب إكمال RC16.7 قبل الانتقال لأي إصدار آخر.**

- إكمال Control Plane
- إكمال Agent Unification
- إكمال Digital Twin Core

### Development Rules

| القاعدة | الوصف |
|---------|-------|
| **No Cross-Layer Imports** | ممنوع imports بين الطبقات |
| **Test Coverage ≥ 80%** | تغطية اختبارات لا تقل عن 80% |
| **Type Hints Required** | نوع البيانات مطلوب لكل دالة |
| **Docstrings Required** | وصف مطلوب لكل دالة |
| **No Hardcoded Secrets** | ممنوع secrets في الكود |
| **Logging Required** | استخدام logging بدلاً من print |

---

## 11. Known Limitations

### SQLite Concurrency

- **المشكلة**: SQLite يدعم اتصال واحد للكتابة
- **الأثر**: بطء في بيئة متعددة المستخدمين
- **الحل**: الترقية إلى PostgreSQL

### Desktop UI Coverage

- **المشكلة**: بعض المكونات لا ت exist في Desktop UI
- **الأثر**: واجهة غير مكتملة
- **الحل**: إكمال التغطية

### Legacy Tests

- **المشكلة**: بعض الاختبارات القديمة غير فعالة
- **الأثر**: تغطية اختبارات أقل
- **الحل**: تحديث الاختبارات

---

## 12. Future Architecture (RC17+)

### Domain Intelligence Platform

- **الهدف**: بناء منصة ذكاء قطاعي
- **المكونات**: Sector Modules, Analytics Engine
- **الجدول**: RC17

### Industry Plugins

- **الهدف**: إضافة إضافات للقطاعات الصناعية
- **المكونات**: Water Plugin, Energy Plugin, Manufacturing Plugin
- **الجدول**: RC17-RC18

### Commercial Platform

- **الهدف**: بناء منصة تجارية
- **المكونات**: Multi-Tenant, Billing, Enterprise Features
- **الجدول**: RC18

---

**آخر تحديث**: 2026-06-12
**الإصدار**: 1.0.0
**الحالة**: Production-Ready
