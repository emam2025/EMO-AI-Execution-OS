# Pilot Execution Plan — Emo-AI

> **Branch:** `release/v1-production-candidate` (frozen)
> **Version:** v1.0.0-RC18
> **Phase:** Pilot Expansion — before Phase H
> **Users:** ≤3 (Operator Pilot Users)

---

## 1. Pilot Overview

### 1.1 Objective
Prove system readiness for operation in a real (or near-real) industrial environment across Energy, Manufacturing, Water, and Healthcare sectors. Success means: stability, performance, security, reliability — paving the way for Phase H (Computer Use Runtime).

### 1.2 Proposed Duration
| Phase | Duration | Description |
|-------|----------|-------------|
| Setup (Staging) | Week 1 | Environment deployment, test data loading |
| Operation (Active Pilot) | Weeks 2-3 | Scenario execution, metrics collection |
| Evaluation (Evaluation) | Week 4 | Results analysis, Post-Pilot decision |

### 1.3 Governing Principles
1. **Total Isolation** — Each sector operates in a separate workspace
2. **Default Deny** — No cross-sector access without explicit policy
3. **Human-in-the-Loop** — All critical actions require human approval
4. **Transparency** — Every decision published on EventBus and recorded in audit trail
5. **No Functional Changes** — Pilot for measurement only, no development

---

## 2. Operating Environment Definition

### 2.1 Environment

| Component | Platform | Specifications |
|-----------|----------|----------------|
| Backend API | Railway / Render / Fly.io | 1 vCPU, 1GB RAM, 10GB SSD |
| Frontend UI | Vercel (independent) | Static export, Serverless |
| Database | SQLite (constrained by PC-001) → PostgreSQL later | File `data/emo_ai.db` |
| Event Store | SQLiteEventStore | Warns at 8k events/sec |
| Worker Pool | Fixed — 4 workers (manually expandable up to 256) |
| Auth | JWT (2h expiry, refresh rotation) — Rate Limiter not currently enabled |

### 2.2 Required Environment Variables

```
EMO_JWT_SECRET=<32+ char secret>
EMO_AUTH_MODE=migration
DATABASE_URL=sqlite:///./data/emo_ai.db
EMO_LOG_LEVEL=INFO
EMO_PILOT_MODE=true
EMO_METRICS_INTERVAL=60
```

### 2.3 Isolation

| Layer | Isolation Mechanism |
|-------|---------------------|
| **Workspace** | `_verify_workspace_access()` on every endpoint |
| **User** | JWT with tenant_id + user_id |
| **Sector** | Each sector (Energy, Manufacturing, Water, Healthcare) in independent workspace |
| **Data** | No data leakage between sectors — Default Deny |

---

## 3. Scenarios — Four Sectors

### 3.1 Manufacturing

| Scenario | Description | Data Source |
|----------|-------------|-------------|
| CNC Overheat | Simulate CNC machine overheating → detect → stop line → operator approval | `LineSupervisorAgent` |
| OEE Monitoring | Periodic OEE calculation, detect performance decline, alert | `OEECalculator`, `OEEMonitorAgent` |
| Predictive Maintenance | Detect abnormal vibrations, predict failures | `PredictiveMaintenanceAgent` |
| Quality Control | Automated quality inspection, request line slowdown on recurring defects | `QualityInspectorClosedLoop` |

**Success Metrics:**
- Overheat detection time: < 5 seconds
- OEE accuracy: ±2%
- False alarm rate (Predictive): < 10%
- Human approval time: < 30 seconds

---

### 3.2 Energy

| Scenario | Description | Data Source |
|----------|-------------|-------------|
| Load Balancing | Simulate load distribution across power generators | `EnergyAgent` |
| Grid Anomaly | Detect power grid anomaly, isolate affected sector | `EnergySafetyPolicies` |
| Consumption Forecast | Energy consumption forecast based on historical data | `KnowledgeGraph` + Embedding |

**Success Metrics:**
- Anomaly detection time: < 10 seconds
- Forecast accuracy: > 85%
- Sector isolation time: < 15 seconds

---

### 3.3 Water

| Scenario | Description | Data Source |
|----------|-------------|-------------|
| Leak Detection | Detect water network leak → locate → isolate | `WaterAgent` |
| Quality Monitoring | Monitor water quality (pH, TDS, chlorine) → alert on exceedance | `WaterPolicies` |
| Pressure Management | Auto-adjust network pressure based on consumption | `WaterAgent` + Digital Twin |

**Success Metrics:**
- Leak detection time: < 10 seconds
- Leak location accuracy: ±5 meters
- Pressure change response time: < 20 seconds

---

### 3.4 Healthcare

| Scenario | Description | Data Source |
|----------|-------------|-------------|
| Patient Monitoring | Monitor vital signs, detect deterioration → alert medical team | `HealthcareAgent` |
| Drug Interaction | Verify drug interactions when adding new medication | `HealthcarePolicies` |
| Resource Allocation | Allocate resources (beds, ventilators) by priority | `HealthcareAgent` + Governance |

**Success Metrics:**
- Deterioration detection time: < 30 seconds
- Drug interaction detection accuracy: > 99%
- Resource allocation time: < 10 seconds

---

## 4. Pass and Fail Criteria

### 4.1 Pass Criteria

| Criterion | Minimum | Weight |
|-----------|---------|--------|
| **All four scenarios** executed successfully ≥ 90% | 90% success | Critical |
| **Latency** < 100ms (p95) | 100ms | Critical |
| **Policy Denial Rate** < 5% | 5% | Critical |
| **Audit Trail Completeness** = 100% | 100% | Critical |
| **Workflow Success Rate** ≥ 95% | 95% | Important |
| **Provider Response Time** < 500ms | 500ms | Important |
| **Zero Security Incidents** | 0 breaches | Critical |
| **Zero Data Leakage** | 0 leaks | Critical |

### 4.2 Fail Criteria

| Criterion | Threshold | Result |
|-----------|-----------|--------|
| **Any security breach** | ≥ 1 | **FAIL Immediate — Stop Pilot** |
| **Any data leakage** | ≥ 1 | **FAIL Immediate — Stop Pilot** |
| **Complete service downtime** | > 30 minutes | **FAIL — Re-evaluate** |
| **Policy Denial Rate** | > 15% | **FAIL — Review policies** |
| **Two or more sectors fail** | ≥ 2 sectors | **FAIL — Re-evaluate** |

### 4.3 Post-Pilot Decision

| Result | Decision |
|--------|----------|
| ✅ **Full Success** — All Pass Criteria met, no Fail Criteria | Proceed to **Phase H** |
| ⚠️ **Partial Success** — Pass Criteria ≥ 80%, no Fail Criteria | **Hardening only** — address gaps, no expansion |
| ❌ **Failure** — Any Fail Criteria | **Stop** — root cause analysis, return to development |

---

## 5. Metrics & Acceptance Gates

### 5.1 Latency

| Type | Target (p95) | Measurement Method |
|------|--------------|--------------------|
| API Request | < 100ms | Prometheus + `/metrics` endpoint |
| Agent Decision | < 200ms | Distributed Tracing (Trace Explorer) |
| Workflow Execution | < 5s (per DAG) | Audit Trail Timestamps |

**Acceptance Gate:** 100ms p95 across all API endpoints. If exceeded → Hardening.

### 5.2 Policy Denial Rate

| Type | Target | Measurement Method |
|------|--------|--------------------|
| ALLOW/DENY Ratio | DENY < 5% of ALL | ProviderGateway Logs |
| False Denials | < 1% | Weekly manual review |

**Acceptance Gate:** DENY < 5%. If exceeded → review ProviderGateway rules.

### 5.3 Audit Trail Completeness

| Type | Target | Measurement Method |
|------|--------|--------------------|
| Event Coverage | 100% | Compare EventBus publications with Audit Trail |
| Trace Completeness | 100% | Distributed Tracing — Trace Explorer |

**Acceptance Gate:** 100%. Any unlogged event = breach of LAW 5 → **FAIL Immediate**.

### 5.4 Workflow Success Rate

| Type | Target | Measurement Method |
|------|--------|--------------------|
| DAG Completion | ≥ 95% | Audit Trail — COMPLETED vs FAILED |
| Auto-Recovery Rate | ≥ 80% | RollbackEngine logs |

**Acceptance Gate:** 95%. Below that → analyze failure causes.

### 5.5 Provider Response Time

| Type | Target | Measurement Method |
|------|--------|--------------------|
| Provider Gateway Decision | < 500ms | ProviderGateway Metrics |
| Connector I/O | < 200ms | Connector Logs |

**Acceptance Gate:** 500ms. If exceeded → check ProviderGateway congestion.

---

## 6. Staging Deployment

### 6.1 Platform Choice

| Option | Pros | Cons |
|--------|------|------|
| **Railway** | ⭐ Simple, Git-connected, integrated with Docker | Limited resources on free plan |
| Render | Docker support, cron jobs, well-known | More complex network setup |
| Fly.io | Closer to Edge, high performance | Higher learning curve |

**Recommendation:** **Railway** — for maximum simplicity with the current project (`Dockerfile` + `docker-compose.yml` ready).

### 6.2 Deployment Steps

```bash
# 1. Login
railway login

# 2. Link project
railway init

# 3. Set variables
railway variables set EMO_JWT_SECRET=$(openssl rand -base64 48)
railway variables set EMO_AUTH_MODE=migration
railway variables set EMO_PILOT_MODE=true
railway variables set EMO_LOG_LEVEL=INFO

# 4. Deploy service
railway up --service backend

# 5. Deploy frontend (Vercel — independent)
cd apps/web
vercel --prod
vercel env add NEXT_PUBLIC_API_BASE_URL
```

### 6.3 Isolation

| Level | Action |
|-------|--------|
| **Workspace Isolation** | 4 workspaces (energy, manufacturing, water, healthcare) — each with `_verify_workspace_access()` |
| **Network Isolation** | Backend on Railway, Frontend on Vercel — no direct connection |
| **Data Isolation** | Separate SQLite database per workspace (upgradeable to PostgreSQL) |
| **Auth Isolation** | JWT per user — permissions scoped to workspace |

### 6.4 Test Data

| Source | Type | Size |
|--------|------|------|
| Historical data | OEE metrics, energy, water, healthcare | ~1000 records per sector |
| Simulation data | Random events (overheat, leak, anomaly) | 10 events/minute |
| Operational data | Approval requests, ALLOW/DENY decisions | ~100 events/hour |

---

## 7. Pilot Runbooks

### 7.1 Operation

#### Daily Startup

```bash
# 1. Check service health
curl -f http://<backend-url>/health

# 2. Check worker status
railway logs --service backend | grep "worker"

# 3. Check EventBus
railway logs --service backend | grep "EventBus started"

# 4. Check database
railway logs --service backend | grep "Database connected"
```

#### Sector Activation

```bash
# Activate Manufacturing sector
curl -X POST http://<backend-url>/api/workspace/manufacturing/activate \
  -H "Authorization: Bearer <token>"

# Activate Energy sector
curl -X POST http://<backend-url>/api/workspace/energy/activate \
  -H "Authorization: Bearer <token>"
```

#### User Onboarding
Follow `docs/PILOT_ONBOARDING.md` — covers user creation steps, agent activation, and Dashboard monitoring.

---

### 7.2 Monitoring

#### Review Intervals

| Metric | Interval | Responsible |
|--------|----------|-------------|
| Latency (p95) | Every 5 minutes | Automatic — Prometheus |
| Policy Denial Rate | Every hour | Automatic + report |
| Audit Trail Completeness | Every 6 hours | Automatic + report |
| Workflow Success Rate | Daily | Automatic |
| Provider Response Time | Every 5 minutes | Automatic |
| Security review | Daily | Manual |
| Comprehensive review | Weekly | Manual — formal report |

#### Dashboard

```
http://<backend-url>/dashboard
├── Cluster Health
├── Active DAGs
├── Worker Topology
└── Operator Action Log
```

#### Red Indicators (Immediate Call)

| Indicator | Action |
|-----------|--------|
| Latency > 500ms | Check worker congestion, scale up |
| DENY > 15% | Review ProviderGateway rules |
| Any Security Violation | Stop Pilot immediately |
| Downtime > 5 minutes | Route traffic to backup |
| Audit Gap (unlogged event) | Immediate investigation |

---

### 7.3 Rollback

#### When to Rollback?

| Condition | Decision |
|-----------|----------|
| Latency > 1000ms for 5 minutes | Immediate Rollback |
| Policy Denial Rate > 25% | Immediate Rollback |
| Any breach | Immediate Rollback |
| Two sectors fail | Rollback (restart) |
| Data corruption | Immediate Rollback |

#### Rollback Steps

```bash
# 1. Stop current service
railway down --service backend

# 2. Restore previous version (RC17.5)
railway up --service backend --from v1.0.0-RC17.5

# 3. Restore database from backup
cp ./backups/pre-pilot.db ./data/emo_ai.db

# 4. Verify health
curl -f http://<backend-url>/health

# 5. Notify users
echo "Rollback completed at $(date). Reason: <reason>" >> ./pilot/rollback.log
```

#### Backup

| Item | Frequency | Location |
|------|-----------|----------|
| Database | Every 6 hours | `./backups/emo_ai_<timestamp>.db` |
| Event Store | Daily | `./backups/events_<date>.jsonl` |
| Audit Logs | Continuous | `./audit/` |
| Docker Images | Each release | GitHub Container Registry |

---

### 7.4 Incident Handling

#### Incident Classification

| Level | Description | Response Time | Resolution Time |
|-------|-------------|---------------|-----------------|
| **P0** | Complete service outage, breach, data leak | Immediate | < 30 minutes |
| **P1** | Major sector failure, severe slowdown | < 15 minutes | < 2 hours |
| **P2** | Minor sector failure, intermittent errors | < 1 hour | < 8 hours |
| **P3** | Non-critical alerts, cosmetic errors | < 24 hours | < 1 week |

#### P0 Handling Process

```
1. Incident detection ← automatic or manual
2. Team notification ← dedicated channel (Slack/Telegram/Pager)
3. Assessment ← P0, P1, P2, P3
4. Containment ← Rollback / sector isolation / service stop
5. Root Cause Analysis (RCA) ← Documentation
6. Resolution ← Apply patch or restore version
7. Review ← Does Post-Pilot decision need change?
8. Document in INCIDENT_LOG.md
```

#### Incident Report Template

```markdown
# Incident Report — <ID>

##基本信息
- **Date:** YYYY-MM-DD HH:mm
- **Level:** P0/P1/P2/P3
- **Source:** Manufacturing / Energy / Water / Healthcare / System
- **Impacted:** Affected sectors
- **Responder:** Responding person

## Description
<Incident description>

## Root Cause
<What happened and why>

## Action Taken
<Rollback / Patch / Isolation>

## Result
<Was it resolved?>

## Lessons Learned
<What we will do differently>
```

---

## 8. Post-Pilot Decision

### 8.1 Decision Criteria

| Status | Criteria | Decision |
|--------|----------|----------|
| ✅ **Green — Full Success** | All Pass Criteria ≥ 100% | **Phase H** begins |
| 🟡 **Yellow — Partial Success** | Pass Criteria ≥ 80%, 0 Fail Criteria | **Hardening** — address gaps then Phase H |
| 🔴 **Red — Failure** | Any Fail Criteria | **Stop** — return to development |

### 8.2 Post-Pilot Report

```markdown
# Post-Pilot Evaluation Report — <Date>

## Pass Criteria
| Metric | Target | Result | ✅/❌ |
|--------|--------|--------|------|
| Latency (p95) | < 100ms | ×ms | |
| Policy Denial Rate | < 5% | ×% | |
| Audit Trail Completeness | 100% | ×% | |
| Workflow Success Rate | ≥ 95% | ×% | |
| Provider Response Time | < 500ms | ×ms | |
| Sector Coverage | 4/4 | ×/4 | |

## Fail Criteria
| Metric | Threshold | Result | ✅/❌ |
|--------|-----------|--------|------|
| Security Incidents | 0 | × | |
| Data Leakage | 0 | × | |
| Downtime | > 30 min | × min | |
| Policy Denial Rate | > 15% | ×% | |

## Decision
[ ] Phase H — Ready for expansion
[ ] Hardening — Address gaps
[ ] Stop — Return to development

## Signature
<Project Manager>
```

---

## 9. Executive Summary

```
Pilot Expansion — Emo-AI v1.0.0-RC18
├── Environment: Railway + Vercel (isolated)
├── Sectors: Energy, Manufacturing, Water, Healthcare
├── Duration: 4 weeks (Setup + Operation + Evaluation)
├── Metrics: 5 main (Latency, Policy, Audit, Workflow, Provider)
├── Pass Criteria: ≥ 90% per scenario, 0 breaches
├── Post-Pilot Decision: Phase H / Hardening / Stop
└── Principles: Isolation, Default Deny, Human-in-the-Loop, Transparency
```

---

> **Summary:** The Pilot Execution Plan defines the environment, scenarios, metrics, pass/fail criteria, operational runbooks, monitoring, rollback, incident handling, and post-pilot decision mechanism. The plan is ready for execution upon approval.

> **Note:** This document is an execution plan — not a technical guide. For technical guidance, refer to `README_DEPLOY.md` and `docs/PILOT_ONBOARDING.md`.
