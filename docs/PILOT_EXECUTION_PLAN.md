# Pilot Execution Plan — Emo-AI

> **الفرع:** `release/v1-production-candidate` (مجمّد)
> **الإصدار:** v1.0.0-RC18
> **المرحلة:** Pilot Expansion — قبل Phase H
> **عدد المستخدمين:** ≤3 (Operator Pilot Users)

---

## 1. Pilot Overview

### 1.1 الهدف
إثبات جاهزية النظام للتشغيل في بيئة صناعية حقيقية (أو شبه حقيقية) عبر قطاعات الطاقة، التصنيع، المياه، والرعاية الصحية. النجاح يعني: استقرار، أداء، أمان، وثوقية — مما يفتح الباب لـ Phase H (Computer Use Runtime).

### 1.2 المدة المقترحة
| المرحلة | المدة | الوصف |
|---------|-------|-------|
| الإعداد (Staging) | أسبوع 1 | نشر البيئة، تشغيل البيانات الاختبارية |
| التشغيل (Active Pilot) | أسبوعان 2-3 | تنفيذ السيناريوهات، جمع المقاييس |
| التقييم (Evaluation) | أسبوع 4 | تحليل النتائج، قرار Post-Pilot |

### 1.3 المبادئ الحاكمة
1. **العزل التام** — كل قطاع يعمل في مساحة منفصلة (workspace)
2. **Default Deny** — لا وصول عبر القطاعات بدون سياسة صريحة
3. **Human-in-the-Loop** — جميع الإجراءات الحرجة تتطلب موافقة بشرية
4. **الشفافية** — كل قرار يُنشر على EventBus ويسجّل في audit trail
5. **لا تغييرات وظيفية** — Pilot للقياس فقط، لا تطوير

---

## 2. تعريف بيئة التشغيل

### 2.1 البيئة

| المكوّن | المنصة | المواصفات |
|---------|--------|-----------|
| Backend API | Railway / Render / Fly.io | 1 vCPU, 1GB RAM, 10GB SSD |
| Frontend UI | Vercel (مستقل) | Static export, Serverless |
| قاعدة البيانات | SQLite (تقيّد بـ PC-001) ← PostgreSQL لاحقاً | ملف `data/emo_ai.db` |
| Event Store | SQLiteEventStore | يحذّر عند 8k events/sec |
| Worker Pool | ثابت — 4 workers (قابل للتوسيع يدوياً حتى 256) |
| Auth | JWT (2h expiry, refresh rotation) — Rate Limiter غير مفعّل حالياً |

### 2.2 المتغيرات البيئية المطلوبة

```
EMO_JWT_SECRET=<32+ char secret>
EMO_AUTH_MODE=migration
DATABASE_URL=sqlite:///./data/emo_ai.db
EMO_LOG_LEVEL=INFO
EMO_PILOT_MODE=true
EMO_METRICS_INTERVAL=60
```

### 2.3 العزل

| الطبقة | آلية العزل |
|--------|-----------|
| **Workspace** | `_verify_workspace_access()` في كل endpoint |
| **مستخدم** | JWT مع tenant_id + user_id |
| **قطاع** | كل قطاع (Energy, Manufacturing, Water, Healthcare) في workspace مستقل |
| **بيانات** | لا تسريب بيانات بين القطاعات — Default Deny |

---

## 3. السيناريوهات — القطاعات الأربعة

### 3.1 Manufacturing — التصنيع

| السيناريو | الوصف | مصدر البيانات |
|-----------|-------|---------------|
| CNC Overheat | محاكاة ارتفاع حرارة ماكينة CNC ← كشف ← إيقاف خط ← موافقة مشغل | `LineSupervisorAgent` |
| OEE Monitoring | حساب OEE دوري، كشف انخفاض الأداء، إنذار | `OEECalculator`, `OEEMonitorAgent` |
| Predictive Maintenance | كشف اهتزازات غير طبيعية، التنبؤ بالأعطال | `PredictiveMaintenanceAgent` |
| Quality Control | فحص جودة تلقائي، طلب إبطاء الخط عند عيوب متكررة | `QualityInspectorClosedLoop` |

**مقاييس النجاح:**
- زمن كشف overheat: < 5 ثوانٍ
- دقة OEE: ±2%
- معدل الإنذار الكاذب (Predictive): < 10%
- وقت الموافقة البشرية: < 30 ثانية

---

### 3.2 Energy — الطاقة

| السيناريو | الوصف | مصدر البيانات |
|-----------|-------|---------------|
| Load Balancing | محاكاة توزيع الأحمال بين مولدات الطاقة | `EnergyAgent` |
| Grid Anomaly | كشف شذوذ في شبكة الكهرباء، عزل القطاع المتأثر | `EnergySafetyPolicies` |
| Consumption Forecast | توقعات استهلاك الطاقة استناداً إلى البيانات التاريخية | `KnowledgeGraph` + Embedding |

**مقاييس النجاح:**
- زمن كشف الشذوذ: < 10 ثوانٍ
- دقة التوقعات: > 85%
- زمن عزل القطاع: < 15 ثانية

---

### 3.3 Water — المياه

| السيناريو | الوصف | مصدر البيانات |
|-----------|-------|---------------|
| Leak Detection | كشف تسرب في شبكة المياه ← تحديد الموقع ← عزل | `WaterAgent` |
| Quality Monitoring | مراقبة جودة المياه (pH, TDS, chlorine) ← إنذار عند التجاوز | `WaterPolicies` |
| Pressure Management | ضبط ضغط الشبكة تلقائياً وفقاً للاستهلاك | `WaterAgent` + Digital Twin |

**مقاييس النجاح:**
- زمن كشف التسرب: < 10 ثوانٍ
- دقة تحديد موقع التسرب: ±5 أمتار
- وقت الاستجابة لتغير الضغط: < 20 ثانية

---

### 3.4 Healthcare — الرعاية الصحية

| السيناريو | الوصف | مصدر البيانات |
|-----------|-------|---------------|
| Patient Monitoring | مراقبة العلامات الحيوية، كشف التدهور ← تنبيه الفريق الطبي | `HealthcareAgent` |
| Drug Interaction | التحقق من تفاعلات الأدوية عند إضافة دواء جديد | `HealthcarePolicies` |
| Resource Allocation | تخصيص الموارد (أسرة، أجهزة تنفس) حسب الأولوية | `HealthcareAgent` + Governance |

**مقاييس النجاح:**
- زمن كشف التدهور: < 30 ثانية
- دقة كشف تفاعل الأدوية: > 99%
- زمن تخصيص الموارد: < 10 ثوانٍ

---

## 4. حدود النجاح والفشل

### 4.1 شروط النجاح (Pass Criteria)

| المعيار | الحد الأدنى | الوزن |
|---------|-------------|-------|
| **جميع السيناريوهات الأربعة** نُفذت بنجاح ≥ 90% | 90% نجاح | حاسم |
| **الـ Latency** < 100ms (p95) | 100ms | حاسم |
| **Policy Denial Rate** < 5% | 5% | حاسم |
| **Audit Trail Completeness** = 100% | 100% | حاسم |
| **Workflow Success Rate** ≥ 95% | 95% | مهم |
| **Provider Response Time** < 500ms | 500ms | مهم |
| **Zero Security Incidents** | 0 اختراق | حاسم |
| **Zero Data Leakage** | 0 تسريب | حاسم |

### 4.2 شروط الفشل (Fail Criteria)

| المعيار | الحد | النتيجة |
|---------|------|---------|
| **أي اختراق أمني** | ≥ 1 | **FAIL فوري — إيقاف Pilot** |
| **أي تسريب بيانات** | ≥ 1 | **FAIL فوري — إيقاف Pilot** |
| **توقف الخدمة الكامل (Downtime)** | > 30 دقيقة | **FAIL — إعادة تقييم** |
| **Policy Denial Rate** | > 15% | **FAIL — مراجعة السياسات** |
| **فشل قطاعين أو أكثر** | ≥ 2 قطاع | **FAIL — إعادة تقييم** |

### 4.3 قرار Post-Pilot

| النتيجة | القرار |
|---------|--------|
| ✅ **نجاح كامل** — جميع Pass Criteria محققة، ولا Fail Criteria | انتقل إلى **Phase H** |
| ⚠️ **نجاح جزئي** — Pass Criteria ≥ 80%، ولا Fail Criteria | **Hardening فقط** — معالجة الفجوات، لا توسع |
| ❌ **فشل** — أي Fail Criteria | **إيقاف** — تحليل الجذور، العودة إلى التطوير |

---

## 5. المقاييس (Metrics) & Acceptance Gates

### 5.1 Latency — زمن الاستجابة

| النوع | الهدف (p95) | طريقة القياس |
|-------|-------------|-------------|
| API Request | < 100ms | Prometheus + `/metrics` endpoint |
| Agent Decision | < 200ms | Distributed Tracing (Trace Explorer) |
| Workflow Execution | < 5s (لكل DAG) | Audit Trail Timestamps |

**Acceptance Gate:** 100ms p95 عبر جميع الـ API endpoints. إذا تجاوز → Hardening.

### 5.2 Policy Denial Rate — نسبة رفض السياسات

| النوع | الهدف | طريقة القياس |
|-------|-------|-------------|
| ALLOW/DENY Ratio | DENY < 5% من ALL | ProviderGateway Logs |
| False Denials | < 1% | مراجعة يدوية أسبوعية |

**Acceptance Gate:** DENY < 5%. إذا تجاوز → مراجعة قواعد ProviderGateway.

### 5.3 Audit Trail Completeness — اكتمال مسار التدقيق

| النوع | الهدف | طريقة القياس |
|-------|-------|-------------|
| Event Coverage | 100% | مقارنة EventBus publications مع Audit Trail |
| Trace Completeness | 100% | Distributed Tracing — Trace Explorer |

**Acceptance Gate:** 100%. أي حدث غير مسجّل = اختراق لـ LAW 5 → **FAIL فوري**.

### 5.4 Workflow Success Rate — معدل نجاح سير العمل

| النوع | الهدف | طريقة القياس |
|-------|-------|-------------|
| DAG Completion | ≥ 95% | Audit Trail — COMPLETED vs FAILED |
| Auto-Recovery Rate | ≥ 80% | RollbackEngine logs |

**Acceptance Gate:** 95%. أقل من ذلك → تحليل أسباب الفشل.

### 5.5 Provider Response Time — زمن استجابة المزوّد

| النوع | الهدف | طريقة القياس |
|-------|-------|-------------|
| Provider Gateway Decision | < 500ms | ProviderGateway Metrics |
| Connector I/O | < 200ms | Connector Logs |

**Acceptance Gate:** 500ms. إذا تجاوز → تحقق من ازدحام ProviderGateway.

---

## 6. Staging Deployment — النشر

### 6.1 المنصة المختارة

| الخيار | المميزات | العيوب |
|--------|---------|--------|
| **Railway** | ⭐ بسيط، Git-connected, متكامل مع Docker | موارد محدودة في الخطة المجانية |
| Render | Docker support, cron jobs, معروف | إعدادات شبكة أكثر تعقيداً |
| Fly.io | أقرب إلى Edge، أداء عالٍ | منحنى تعلم أعلى |

**التوصية:** **Railway** — لأقصى بساطة مع المشروع الحالي (`Dockerfile` + `docker-compose.yml` جاهزان).

### 6.2 خطوات النشر

```bash
# 1. تسجيل الدخول
railway login

# 2. ربط المشروع
railway init

# 3. تعيين المتغيرات
railway variables set EMO_JWT_SECRET=$(openssl rand -base64 48)
railway variables set EMO_AUTH_MODE=migration
railway variables set EMO_PILOT_MODE=true
railway variables set EMO_LOG_LEVEL=INFO

# 4. رفع الخدمة
railway up --service backend

# 5. رفع الواجهة (Vercel — مستقل)
cd apps/web
vercel --prod
vercel env add NEXT_PUBLIC_API_BASE_URL
```

### 6.3 العزل

| المستوى | الإجراء |
|---------|--------|
| **Workspace Isolation** | 4 workspaces (energy, manufacturing, water, healthcare) — كل منها بـ `_verify_workspace_access()` |
| **Network Isolation** | Backend على Railway، Frontend على Vercel — لا اتصال مباشر |
| **Data Isolation** | قاعدة بيانات SQLite منفصلة لكل workspace (قابلة للترقية إلى PostgreSQL) |
| **Auth Isolation** | JWT لكل مستخدم — صلاحيات مقيدة بـ workspace |

### 6.4 بيانات الاختبار

| المصدر | النوع | الحجم |
|--------|------|-------|
| بيانات تاريخية | مقاييس OEE, طاقة, مياه, رعاية صحية | ~1000 سجل لكل قطاع |
| بيانات محاكاة | أحداث عشوائية (overheat, تسرب, شذوذ) | 10 أحداث/دقيقة |
| بيانات تشغيلية | طلبات موافقة، قرارات ALLOW/DENY | ~100 حدث/ساعة |

---

## 7. Pilot Runbooks

### 7.1 التشغيل

#### Daily Startup

```bash
# 1. التحقق من صحة الخدمة
curl -f http://<backend-url>/health

# 2. التحقق من حالة الـ Workers
railway logs --service backend | grep "worker"

# 3. التحقق من EventBus
railway logs --service backend | grep "EventBus started"

# 4. التحقق من قاعدة البيانات
railway logs --service backend | grep "Database connected"
```

#### Sector Activation

```bash
# تنشيط قطاع Manufacturing
curl -X POST http://<backend-url>/api/workspace/manufacturing/activate \
  -H "Authorization: Bearer <token>"

# تنشيط قطاع Energy
curl -X POST http://<backend-url>/api/workspace/energy/activate \
  -H "Authorization: Bearer <token>"
```

#### User Onboarding
اتبع `docs/PILOT_ONBOARDING.md` — يغطي خطوات إنشاء المستخدم، تشغيل الأجنت، ومراقبة Dashboard.

---

### 7.2 المراقبة

#### فترات المراجعة

| المقياس | الفترة | المسؤول |
|---------|--------|---------|
| Latency (p95) | كل 5 دقائق | تلقائي — Prometheus |
| Policy Denial Rate | كل ساعة | تلقائي + تقرير |
| Audit Trail Completeness | كل 6 ساعات | تلقائي + تقرير |
| Workflow Success Rate | يومياً | تلقائي |
| Provider Response Time | كل 5 دقائق | تلقائي |
| مراجعة أمنية | يومياً | يدوي |
| مراجعة شاملة | أسبوعياً | يدوي — تقرير رسمي |

#### لوحة المراقبة (Dashboard)

```
http://<backend-url>/dashboard
├── Cluster Health
├── Active DAGs
├── Worker Topology
└── Operator Action Log
```

#### Indicators الحمراء (استدعاء فوري)

| المؤشر | الإجراء |
|---------|---------|
| Latency > 500ms | تحقق من ازدحام workers, scale up |
| DENY > 15% | مراجعة ProviderGateway rules |
| أي Security Violation | إيقاف Pilot فوراً |
| Downtime > 5 دقائق | توجيه traffic إلى backup |
| Audit Gap (حدث غير مسجّل) | تحقيق فوري |

---

### 7.3 Rollback

#### متى نعمل Rollback؟

| الحالة | القرار |
|--------|--------|
| Latency > 1000ms لمدة 5 دقائق | Rollback فوري |
| Policy Denial Rate > 25% | Rollback فوري |
| أي اختراق | Rollback فوري |
| فشل قطاعين | Rollback (إعادة تشغيل) |
| خطأ في البيانات (Data corruption) | Rollback فوري |

#### خطوات Rollback

```bash
# 1. إيقاف الخدمة الحالية
railway down --service backend

# 2. استعادة النسخة السابقة (RC17.5)
railway up --service backend --from v1.0.0-RC17.5

# 3. استعادة قاعدة البيانات من backup
cp ./backups/pre-pilot.db ./data/emo_ai.db

# 4. التحقق من الصحة
curl -f http://<backend-url>/health

# 5. إشعار المستخدمين
echo "Rollback completed at $(date). Reason: <reason>" >> ./pilot/rollback.log
```

#### النسخ الاحتياطي (Backup)

| العنصر | التكرار | الموقع |
|--------|---------|--------|
| قاعدة البيانات | كل 6 ساعات | `./backups/emo_ai_<timestamp>.db` |
| Event Store | يومياً | `./backups/events_<date>.jsonl` |
| Audit Logs | مستمر | `./audit/` |
| Docker Images | عند كل إصدار | GitHub Container Registry |

---

### 7.4 Incident Handling

#### تصنيف الحوادث

| المستوى | الوصف | وقت الاستجابة | وقت الحل |
|---------|-------|--------------|---------|
| **P0** | توقف الخدمة بالكامل، اختراق، تسريب بيانات | فوري | < 30 دقيقة |
| **P1** | فشل قطاع رئيسي، بطء شديد | < 15 دقيقة | < ساعتين |
| **P2** | فشل قطاع ثانوي، أخطاء متقطعة | < ساعة | < 8 ساعات |
| **P3** | إنذارات غير حرجة، أخطاء تجميلية | < 24 ساعة | < أسبوع |

#### سير معالجة P0

```
1. كشف الحادث ← تلقائي أو يدوي
2. إشعار الفريق ← قناة مخصصة (Slack/Telegram/Pager)
3. تقييم ← P0, P1, P2, P3
4. احتواء ← Rollback / عزل القطاع / إيقاف الخدمة
5. تحليل السبب الجذري (RCA) ← توثيق
6. حل ← تطبيق patch أو استعادة النسخة
7. مراجعة ← هل يحتاج الـ Post-Pilot قرار تغيير؟
8. توثيق في INCIDENT_LOG.md
```

#### قالب الإبلاغ عن الحادث

```markdown
# Incident Report — <ID>

##基本信息
- **التاريخ:** YYYY-MM-DD HH:mm
- **المستوى:** P0/P1/P2/P3
- **المصدر:** Manufacturing / Energy / Water / Healthcare / System
- **المؤثرون:** القطاعات المتأثرة
- **الموجود:** الشخص المستجيب

## الوصف
<وصف الحادث>

## السبب الجذري
<ما حدث ولماذا>

## الإجراء المتخذ
<Rollback / Patch / عزل>

## النتيجة
<هل تم الحل؟>

## الدروس المستفادة
<ما سنفعله differently>
```

---

## 8. Post-Pilot Decision

### 8.1 معايير القرار

| الحالة | المعايير | القرار |
|--------|---------|--------|
| ✅ **Green — نجاح كامل** | جميع Pass Criteria ≥ 100% | **Phase H** يبدأ |
| 🟡 **Yellow — نجاح جزئي** | Pass Criteria ≥ 80%، 0 Fail Criteria | **Hardening** — معالجة الفجوات ثم Phase H |
| 🔴 **Red — فشل** | أي Fail Criteria | **إيقاف** — العودة إلى التطوير |

### 8.2 تقرير Post-Pilot

```markdown
# Post-Pilot Evaluation Report — <التاريخ>

## Pass Criteria
| المقياس | الهدف | النتيجة | ✅/❌ |
|---------|-------|---------|------|
| Latency (p95) | < 100ms | ×ms | |
| Policy Denial Rate | < 5% | ×% | |
| Audit Trail Completeness | 100% | ×% | |
| Workflow Success Rate | ≥ 95% | ×% | |
| Provider Response Time | < 500ms | ×ms | |
| Sector Coverage | 4/4 | ×/4 | |

## Fail Criteria
| المقياس | الحد | النتيجة | ✅/❌ |
|---------|------|---------|------|
| Security Incidents | 0 | × | |
| Data Leakage | 0 | × | |
| Downtime | > 30 min | × min | |
| Policy Denial Rate | > 15% | ×% | |

## القرار
[ ] Phase H — جاهز للتوسع
[ ] Hardening — معالجة الفجوات
[ ] إيقاف — العودة للتطوير

## التوقيع
<مدير المشروع>
```

---

## 9. الملخص التنفيذي

```
Pilot Expansion — Emo-AI v1.0.0-RC18
├── البيئة: Railway + Vercel (معزولان)
├── القطاعات: الطاقة، التصنيع، المياه، الرعاية الصحية
├── المدة: 4 أسابيع (إعداد + تشغيل + تقييم)
├── المقاييس: 5 رئيسية (Latency, Policy, Audit, Workflow, Provider)
├── حدود النجاح: ≥ 90% لكل سيناريو، 0 اختراق
├── قرار ما بعد Pilot: Phase H / Hardening / إيقاف
└── المبادئ: العزل، Default Deny، Human-in-the-Loop، الشفافية
```

---

> **الخلاصة:** Pilot Execution Plan يحدد البيئة، السيناريوهات، المقاييس، حدود النجاح/الفشل، runbooks التشغيل والمراقبة والـ rollback والحوادث، وآلية اتخاذ القرار بعد Pilot. الخطة جاهزة للتنفيذ فور الموافقة.

> **ملاحظة:** هذا المستند هو خطة تنفيذ — ليس دليلاً تقنياً. للتوجيه التقني، راجع `README_DEPLOY.md` و `docs/PILOT_ONBOARDING.md`.
