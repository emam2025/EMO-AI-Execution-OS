# Architecture Ownership Map — Emo-AI

> **الغرض:** توثيق ملكية كل مجلد، وتصنيف انتمائه للطبقات العشر (حالياً ومستقبلاً)، وتحديد التبعيات، والفصل بين ما هو موجود الآن وما يُرحّل لاحقاً.
>
> **حالة الفرع:** `release/v1-production-candidate` — **مجمّد**. لا تغييرات حتى انتهاء Pilot.
>
> **نوع الوثيقة:** Mapping Only — ليست خطة Refactor تنفيذية.

---

## 1. الطبقات العشر — ملكية الحاضر والمستقبل

### 1.1 Agent OS

| المسار | نوع الملكية | الحالة |
|--------|------------|--------|
| `core/agents/` | **ملك كامل — Agent OS** | يبقى في مكانه |
| `core/agent_teams/` | **ملك كامل — Agent OS** | يبقى في مكانه |
| `core/planner/` | **ملك كامل — Agent OS** | يبقى في مكانه |
| `core/autonomous_control/` | **ملك كامل — Agent OS** | يبقى في مكانه |
| `core/autonomy/` | **ملك كامل — Agent OS** | يبقى في مكانه |

**الملفات الأساسية:** `core/agents/planner_agent.py`, `critic_agent.py`, `adaptive_planner.py`, مجلدات القطاعات تحت `core/agents/{energy,manufacturing,water,healthcare}/`.

**تبعيات:** `core/models/` (event, planner, critic, agent), `core/interfaces/`, `core/governance/`, `core/security/`

---

### 1.2 Workflow OS

| المسار | نوع الملكية | الحالة |
|--------|------------|--------|
| `core/workflow_os/` | **Reserved / Target Ownership** — حاوية مستقبلية لمحتوى Workflow | **موجود لكنه فارغ حالياً** (يحتوي فقط على `__pycache__`). يُملأ لاحقاً |
| `core/workflow_runtime_v2/` | **ملك كامل — Workflow OS** | يبقى في مكانه |
| `core/canvas/` | **ملك تابع — Workflow OS** (UI canvas) | يبقى في مكانه |
| `core/dag_*.py` | **ملك كامل — Workflow OS** | يبقى في مكانه |
| `routers/workflow.py` | **ملك كامل — Workflow API** | يبقى في مكانه |

**محتوى `core/workflow_os/` المقترح مستقبلاً (في فرع refactor):**
- `workflow_engine.py` — مشغل DAG
- `workflow_validator.py` — التحقق من صحة DAG (موجود حالياً في `routers/workflow.py`)
- `workflow_scheduler.py` — جدولة workflows
- `workflow_models.py` — نماذج Workflow-specific

**تبعيات:** `core/models/dag.py`, `core/models/event.py`, `core/runtime/`

---

### 1.3 Project OS

| المسار | نوع الملكية | الحالة |
|--------|------------|--------|
| `core/projectos/` | **ملك كامل — Project OS** | يبقى في مكانه |
| `routers/project.py` | **ملك كامل — Project API** | يبقى في مكانه |

**تبعيات:** `core/models/`, `core/security/`, `core/governance/`

---

### 1.4 Industrial OS

| المسار | نوع الملكية | الحالة |
|--------|------------|--------|
| `core/industrial/` | **ملك كامل — Industrial OS** | يبقى في مكانه |
| `core/industry_profiles/` | **ملك كامل — Industrial OS** | يبقى في مكانه |
| `core/digital_twin_v2/` | **ملك كامل — Industrial OS** | يبقى في مكانه |
| `core/models/{energy,manufacturing,water,healthcare,industrial}.py` | **ملك كامل — Industrial OS** | يبقى في مكانه |

**تبعيات:** `core/governance/{energy,manufacturing,water,healthcare}_policies.py`

---

### 1.5 Integration OS

| المسار | نوع الملكية | الحالة |
|--------|------------|--------|
| `core/connectors/` | **ملك كامل — Integration OS** (6 مجلدات فرعية) | يبقى في مكانه |
| `core/communication_hub/` | **ملك كامل — Integration OS** | يبقى في مكانه |
| `core/gateway/` | **ملك كامل — Integration OS** (Provider Gateway) | يبقى في مكانه |
| `core/marketplace/` | **ملك كامل — Integration OS** | يبقى في مكانه |
| `routers/integrations.py` | **ملك كامل — Integration API** | يبقى في مكانه |
| `routers/providers.py` | **ملك كامل — Provider Marketplace API** | يبقى في مكانه |
| `core/models/integration.py` | **ملك كامل — Integration OS** | يبقى في مكانه |
| `core/models/provider_marketplace.py` | **ملك كامل — Integration OS** | يبقى في مكانه |

---

### 1.6 Cognitive Layer

| المسار | نوع الملكية | الحالة |
|--------|------------|--------|
| `core/cognition/` | **ملك كامل — Cognitive Layer** | يبقى في مكانه |
| `core/knowledge_graph/` | **ملك كامل — Cognitive Layer** | يبقى في مكانه |
| `core/knowledge_graph_os/` | **ملك كامل — Cognitive Layer** | يبقى في مكانه |
| `core/knowledge_os/` | **ملك كامل — Cognitive Layer** | يبقى في مكانه |
| `core/workspace_intelligence/` | **ملك كامل — Cognitive Layer** | يبقى في مكانه |
| `core/embedding_engine.py` | **ملك كامل — Cognitive Layer** | يبقى في مكانه |
| `core/semantic_store.py` | **ملك كامل — Cognitive Layer** | يبقى في مكانه |
| `core/graph_query.py` | **ملك كامل — Cognitive Layer** | يبقى في مكانه |
| `core/hybrid_retriever.py` | **ملك كامل — Cognitive Layer** | يبقى في مكانه |

---

### 1.7 Security Governance

| المسار | نوع الملكية | الحالة |
|--------|------------|--------|
| `core/security/` | **ملك كامل — Security Governance** | يبقى في مكانه |
| `core/governance/` | **ملك كامل — Security Governance** | يبقى في مكانه |
| `core/threat_intel/` | **ملك كامل — Security Governance** | يبقى في مكانه |
| `core/guardrails.py` | **ملك كامل — Security Governance** | يبقى في مكانه |
| `core/models/{security,secrets,trust,safety}.py` | **ملك كامل — Security Governance** | يبقى في مكانه |
| `SECURITY.md` | **ملك كامل — Security Governance** | يبقى في مكانه |

---

### 1.8 Memory Governance

| المسار | نوع الملكية | الحالة |
|--------|------------|--------|
| `core/memory/` | **ملك كامل — Memory Governance** (6 ملفات) | يبقى في مكانه |
| `core/enterprise_memory/` | **ملك كامل — Memory Governance** | يبقى في مكانه |
| `core/data_fabric/` | **ملك كامل — Memory Governance** | يبقى في مكانه |
| `core/memory_pressure.py` | **ملك كامل — Memory Governance** | يبقى في مكانه |
| `core/execution_memory.py` | **ملك كامل — Memory Governance** | يبقى في مكانه |

---

### 1.9 Production Hardening

| المسار | نوع الملكية | الحالة |
|--------|------------|--------|
| `core/hardening/` | **ملك كامل — Production Hardening** | يبقى في مكانه |
| `core/chaos/` | **ملك كامل — Production Hardening** | يبقى في مكانه |
| `core/deployment/` | **ملك كامل — Production Hardening** | يبقى في مكانه |
| `core/release/` | **ملك كامل — Production Hardening** | يبقى في مكانه |
| `core/readiness/` | **ملك كامل — Production Hardening** | يبقى في مكانه |
| `core/recovery/` | **ملك كامل — Production Hardening** | يبقى في مكانه |
| `core/connector_cert/` | **ملك كامل — Production Hardening** | يبقى في مكانه |
| `Dockerfile` | **ملك كامل — Production Hardening** | يبقى في مكانه |
| `docker-compose.yml` | **ملك كامل — Production Hardening** | يبقى في مكانه |
| `.github/workflows/ci.yml` | **ملك كامل — Production Hardening** | يبقى في مكانه |

---

### 1.10 Command Center — Ops / Supervisory Layer

`core/command_center/` هي **طبقة إشراف وتشغيل (Supervisory Layer)**، وليست المالك النهائي لكل API أو Router في النظام. وظيفتها: المراقبة، لوحات التحكم، CLI، والتحكم التشغيلي.

| المسار | نوع الملكية | الحالة |
|--------|------------|--------|
| `core/command_center/` | **Ops / Supervisory Layer** | يبقى في مكانه |
| `core/control_plane/` | **ملك كامل — Command Center** | يبقى في مكانه |
| `core/observability/` | **ملك كامل — Command Center** | يبقى في مكانه |
| `core/cli/` | **ملك كامل — Command Center** | يبقى في مكانه |
| `core/service_registry.py` | **ملك كامل — Command Center** | يبقى في مكانه |
| `core/worker_registry.py` | **ملك كامل — Command Center** | يبقى في مكانه |

---

## 2. المكونات Cross-Cutting (لا تنتمي لطبقة OS محددة)

### 2.1 `core/runtime/` — Execution Substrate

`core/runtime/` هو **substrate التنفيذ** — لا ينتمي لأي OS محدد. جميع الطبقات تعتمد عليه.

| التصنيف | القيمة |
|---------|--------|
| **الملكية** | **Execution Substrate — مستقل عن جميع الطبقات** |
| **الحالة** | يبقى في `core/runtime/` كما هو |
| **المكونات** | scheduler, state store, dispatcher, retry/lease/recovery, sandbox, isolation, resource scheduling, trust scheduling, event integration, control plane adapters |
| **المستفيدون** | جميع الطبقات العشر |
| **التبعيات** | `core/models/`, `core/security/` |

**ملفات Phases السابقة:** `core/runtime/unified_api.py` (F1), `core/runtime/control_plane/` (F2), `core/runtime/resource_scheduler/` (F3), `core/runtime/tracing/` (F4)

---

### 2.2 `core/execution_engine.py` — Thin Compatibility Entrypoint

| التصنيف | القيمة |
|---------|--------|
| **الملكية** | **Thin entrypoint** — لا يُعامل كمكوّن Domain |
| **الحالة** | يبقى في مكانه. مستقبلاً يُرحّل إلى `core/runtime/execution_engine.py` في فرع refactor |

---

### 2.3 `core/interfaces/` — Service Contracts

| التصنيف | القيمة |
|---------|--------|
| **الملكية** | **Cross-cutting** — جميع الطبقات |
| **الحالة** | يبقى في مكانه |

---

## 3. `core/models/` — النماذج (الوضع الحالي)

تحتوي `core/models/` حالياً على **33 ملف نموذج مسطح** تنتمي لطبقات متعددة. **هذا هو الهيكل الحالي ولا يُغيّر الآن.**

### التقسيم الحالي حسب المحتوى (تصنيفي فقط — لا نقل):

| المجموعة | الملفات |
|----------|---------|
| **Shared** | `event.py`, `events.py`, `failure_propagation.py`, `rollback.py`, `lifecycle.py`, `dag.py`, `types.py` |
| **Agent OS** | `agent.py`, `planner.py`, `critic.py` |
| **Industrial OS** | `energy.py`, `manufacturing.py`, `manufacturing_advanced.py`, `water.py`, `healthcare.py`, `industrial.py`, `energy_policy.py` |
| **Security Governance** | `security.py`, `secrets.py`, `trust.py`, `safety.py`, `guardrails.py` |
| **Integration OS** | `integration.py`, `provider_marketplace.py` |
| **Infrastructure / Runtime** | `infra_models.py`, `runtime_api.py`, `resource_scheduler.py`, `control_plane.py`, `distributed_tracing.py`, `sandbox.py` |
| **Workspace / Observability** | `workspace.py`, `observability.py` |

### Future Refactor Target — تقسيم `core/models/` (في فرع مستقل)

> ⚠️ **هذا ليس الهيكل الحالي.** هذا هو الهدف المستقبلي فقط، ويُنفّذ في فرع `refactor/` منفصل بعد Pilot.

```
core/models/
├── shared/          ← event.py, events.py, failure_propagation.py, rollback.py, lifecycle.py, types.py
├── agents/          ← agent.py, planner.py, critic.py
├── industrial/      ← energy.py, manufacturing.py, manufacturing_advanced.py, water.py, healthcare.py, industrial.py
├── security/        ← security.py, secrets.py, trust.py, safety.py, guardrails.py
├── integration/     ← integration.py, provider_marketplace.py
├── infrastructure/  ← infra_models.py, runtime_api.py, resource_scheduler.py, control_plane.py, distributed_tracing.py, sandbox.py
└── workspace/       ← workspace.py, observability.py
```

---

## 4. `routers/` — API Surfaces, Not Domain Ownership

`routers/` هي **واجهات API عامة** (API surfaces)، وليست ملكية متعمقة للطبقات. تصنيفها يعكس المجال الذي تخدمه، لا انتماءها التنظيمي.

| الراوتر | المجال | ملاحظة |
|---------|--------|--------|
| `workflow.py` | Workflow OS | |
| `project.py` | Project OS | |
| `integrations.py` | Integration OS | |
| `providers.py` | Provider Marketplace (Integration OS) | |
| `workspace.py` | Infrastructure (Cross-cutting) | |
| `ai.py` | Agent OS | |
| `chat.py` | Agent OS | |
| `conversations.py` | Agent OS | |
| `history.py` | Memory Governance | |
| `stream.py` | Runtime | |
| `tasks.py` | Runtime | |
| `auth.py` | Security Governance | |
| `e2e.py` | Testing / Production Hardening | |
| `observability.py` | Command Center | |
| `runtime_api.py` | Runtime | |
| `settings.py` | Command Center | |

**مبدأ ثابت:** `routers/` تحتوي فقط على منطق التوجيه (routing, validation, auth). لا تحتوي على منطق تنفيذي (`execute`, `run`, `dispatch`, `sandbox`).

### Future Refactor Target (في فرع مستقل):

```
routers/
├── agents/       ← ai.py, chat.py, conversations.py
├── workflows/    ← workflow.py
├── runtime/      ← stream.py, tasks.py, runtime_api.py
├── security/     ← auth.py
├── enterprise/   ← project.py, workspace.py
├── integrations/ ← integrations.py, providers.py
└── command_center/ ← observability.py, settings.py, history.py
```

---

## 5. `apps/web/` — Presentation Layer

| التصنيف | القيمة |
|---------|--------|
| **الملكية** | **Presentation Layer** — طبقة عرض مستقلة |
| **الحالة** | يبقى في مكانه |
| **المنصة** | Vercel (Frontend only) — منفصل كلياً عن Backend |
| **قاعدة صارمة** | **ممنوع استيراد أي منطق تنفيذي** من `core/` مباشرة. يتواصل مع Backend عبر API calls فقط. |

---

## 6. `tests/` — اختبارات الحاضر والمستقبل

### الوضع الحالي: ~80 ملف اختبار في `tests/` مسطح

### Future Refactor Target:

```
tests/
├── agents/
├── runtime/
├── workflows/
├── security/
├── industrial/
├── integration/
├── ui/
├── deployment/
└── core/           ← للمكونات cross-cutting
```

---

## 7. مصفوفة Cross-Cutting Dependencies

| المستهلك ↓ / المنتج → | `core/runtime/` | `core/security/` | `core/governance/` | `core/models/` | `core/interfaces/` |
|----------------------|:---:|:---:|:---:|:---:|:---:|
| Agent OS | ✅ | ✅ | ✅ | ✅ | ✅ |
| Workflow OS | ✅ | ✅ | ✅ | ✅ | ✅ |
| Project OS | — | ✅ | ✅ | ✅ | ✅ |
| Industrial OS | — | ✅ | ✅ | ✅ | — |
| Integration OS | ✅ | ✅ | ✅ | ✅ | ✅ |
| Cognitive Layer | ✅ | ✅ | — | ✅ | — |
| Security Governance | ✅ | — | ✅ | ✅ | ✅ |
| Memory Governance | ✅ | ✅ | — | ✅ | — |
| Production Hardening | ✅ | ✅ | ✅ | ✅ | — |
| Command Center | ✅ | ✅ | — | ✅ | ✅ |
| `routers/` | ✅ | ✅ | ✅ | ✅ | ✅ |
| `apps/web/` | ❌ | ❌ | ❌ | ❌ | ❌ |

---

## 8. خريطة الطريق — مرحلتين

### المرحلة 1 — Mapping Only (مكتملة ✅)
- [x] توثيق الملكية الحالية لكل مجلد
- [x] تصنيف المكونات للطبقات العشر
- [x] تحديد dependencies
- [x] الفصل بين الوضع الحالي والتنظيم المستقبلي
- [x] توثيق `core/runtime/` كـ execution substrate مستقل
- [x] توثيق `routers/` كواجهات API (ليست ملكية عميقة)
- [x] توثيق `apps/web/` كـ presentation layer
- [x] تأكيد تجميد `release/v1-production-candidate`

### المرحلة 2 — Refactor Branch (مستقبلية، بعد Pilot)
- [ ] إنشاء فرع: `refactor/10-layer-architecture`
- [ ] تقسيم `core/models/` حسب Future Refactor Target
- [ ] تنظيم `routers/` حسب المجال
- [ ] ملء `core/workflow_os/` بمحتوى Workflow-specific
- [ ] نقل `core/execution_engine.py` ← `core/runtime/execution_engine.py` (اختياري)
- [ ] تنظيم `tests/` حسب الطبقة
- [ ] تحديث جميع الـ imports
- [ ] تشغيل جميع الاختبارات والتحقق من الـ CI
- [ ] دمج الفرع بعد موافقة الفريق

---

## 9. المبادئ التوجيهية

1. **لا تكسر الـ API العام** — جميع endpoints الحالية تبقى متاحة
2. **لا تكسر الـ imports** — روابط رمزية (symlinks) كمرحلة انتقالية إن لزم الأمر
3. **كل Refactor في فرع منفصل** — ليس في `release/` أو `main/`
4. **100% من الاختبارات تمر** قبل وبعد الـ Refactor
5. **لا تغييرات وظيفية** — الـ Refactor هيكلي فقط، لا إضافة ميزات
6. **Pilot أولاً** — لا Refactor قبل استقرار Pilot وجمع بيانات كافية

---

> **الخلاصة:** النظام حاليًا صالح للـ Pilot. جميع مكونات الطبقات العشر موجودة في `core/` لكنها غير منظمة هرمياً. هذه الوثيقة تثبت الواقع الحقيقي (current state) وتحدد الهدف المستقبلي (future refactor target) بوضوح، دون خلط بينهما. الفرع `release/v1-production-candidate` مجمّد. الـ Refactor في فرع مستقل لاحقاً بعد Pilot.
