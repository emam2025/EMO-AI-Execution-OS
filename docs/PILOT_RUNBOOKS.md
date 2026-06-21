# Pilot Runbooks — Emo-AI v1.0.0-RC18

## 1. Pilot Start / Restart

```bash
# Verify environment
curl -f https://emo-ai-pilot-production.up.railway.app/api/status

# Check security modules
curl -s https://emo-ai-pilot-production.up.railway.app/api/security/health | python3 -m json.tool

# Expected: {"security":true,"rbac":true,"identity":true,"provider_gateway":true}

# Check workflows endpoint
curl -s https://emo-ai-pilot-production.up.railway.app/api/workflows

# Expected: []
```

## 2. Pilot Stop / Drain

```bash
# Via Railway Dashboard (no CLI stop available):
# 1. Open https://railway.com/dashboard
# 2. Select emo-ai-pilot → Settings → Danger Zone → Stop
```

## 3. Rollback Procedure

```bash
# Rollback to previous deployment
railway up --service emo-ai-pilot --detach  # redeploy local code
# OR via Railway Dashboard → Deployments → Select previous → Rollback
```

## 4. Incident Response

| Severity | Response | Time |
|----------|----------|------|
| 🔴 CRITICAL — API down >5min | Rollback to last known good | < 5 min |
| 🟡 WARNING — Latency >500ms p95 | Check Railway tier, upgrade if needed | < 15 min |
| 🔵 INFO — Single endpoint fails | Check logs, restart service | < 30 min |

## 5. Logs & Debug

```bash
# View live logs
railway logs --service emo-ai-pilot

# Filter by module
railway logs --service emo-ai-pilot 2>&1 | grep -i "gateway"
railway logs --service emo-ai-pilot 2>&1 | grep -i "error"
railway logs --service emo-ai-pilot 2>&1 | grep -i "security"
```

## 6. Health Check Endpoints

| Endpoint | Purpose |
|----------|---------|
| `GET /api/status` | General health |
| `GET /api/security/health` | Security modules + ProviderGateway |
| `GET /api/security/status` | Identity + RBAC + Gateway status |
| `GET /api/workflows` | Workflow router status (returns `[]`) |
| `POST /api/workspaces` | Workspace isolation test (returns list/405) |

## 7. Data Safety

- No persistent database in Pilot stage (SQLite only)
- No real customer data
- All environment variables are test/staging values
- Railway staging environment is fully isolated
