# Pilot Monitoring Specs — Emo-AI v1.0.0-RC18

## 1. Metrics Tracked (5 Core)

| Metric | Target | Current | Alert Threshold |
|--------|--------|---------|-----------------|
| Latency p95 | < 100ms | ~900ms | > 500ms |
| Policy Denial Rate | < 5% | 0% | > 10% |
| Audit Completeness | 100% | 100% | < 95% |
| Workflow Success Rate | ≥ 95% | 100% | < 90% |
| Provider Response Time | < 500ms | N/A (cold) | > 2000ms |

## 2. Endpoint Coverage (16 Total, 14 Active)

| # | Endpoint | Status | Last Check |
|---|----------|--------|------------|
| 1 | `GET /api/status` | ✅ 200 | 2026-06-21 |
| 2 | `GET /api/security/health` | ✅ 200 | 2026-06-21 |
| 3 | `GET /api/security/status` | ✅ 200 | 2026-06-21 |
| 4 | `GET /api/workflows` | ✅ 200 | 2026-06-21 |
| 5 | `POST /api/workspaces` | ✅ 405 (expected) | 2026-06-21 |
| 6-14 | Legacy endpoints | ✅ 200/422 | 2026-06-21 |
| 15 | `GET /` | ❌ No template | Deferred |
| 16 | `/observability/` | ❌ No template | Deferred |

## 3. Sectors Monitored

| Sector | Status | Last Scenario Run |
|--------|--------|-------------------|
| Manufacturing | ✅ Ready | Pending |
| Energy | ✅ Ready | Pending |
| Water | ✅ Ready | Pending |
| Healthcare | ✅ Ready | Pending |

## 4. Alerting (Manual via Railway Dashboard)

Railway does not support automated alerting on free tier.
Monitoring is done manually via:
- `railway logs --service emo-ai-pilot`
- `curl` health check endpoints
- Railway Dashboard → Deployments → Status

## 5. Success Criteria

| Gate | Criteria | Current | Pass? |
|------|----------|---------|-------|
| G1 | All routers wired | ✅ | Pass |
| G2 | ProviderGateway active | ✅ | Pass |
| G3 | Security modules integrated | ✅ | Pass |
| G4 | Latency < 100ms p95 | ❌ ~900ms | Blocking |
| G5 | Full endpoint coverage (16/16) | ✅ 14/16 | 2 deferred |
