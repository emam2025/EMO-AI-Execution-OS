# R1 Deployment Checklist — EMO Distributed AI Runtime OS v1-runtime-stable

## Prerequisites
- [ ] Python 3.14+ installed
- [ ] `pip install -r requirements.txt` (source/requirements.txt)
- [ ] `EMO_JWT_SECRET` environment variable set (strong, unique value)
- [ ] `EMO_AUTH_PASSWORD` environment variable set (if auth enabled)
- [ ] No conflicting services on port 8080

## Single-Node (Docker)
- [ ] `docker compose -f deployment/docker-compose.runtime.yml up -d`
- [ ] Verify: `curl http://localhost:8080/api/tray/ping` → `{"status":"ok"}`
- [ ] Verify auth: `curl -I http://localhost:8080/api/status` → 401

## Single-Node (Native Python)
- [ ] `python source/main.py`
- [ ] Verify: `curl http://localhost:8080/api/tray/ping` → `{"status":"ok"}`

## Kubernetes
- [ ] `kubectl apply -f deployment/k8s/emo-runtime-os.yaml`
- [ ] Create secrets:
  ```bash
  kubectl create secret generic emo-jwt-secret --from-literal=secret=$EMO_JWT_SECRET -n emo-runtime-os
  kubectl create secret generic emo-auth-password --from-literal=password=$EMO_AUTH_PASSWORD -n emo-runtime-os
  ```
- [ ] Verify pod is running: `kubectl get pods -n emo-runtime-os`

## Post-Deployment Validation
- [ ] Run: `python -m pytest -m "not quarantined"` → all PASS
- [ ] Run: `python scripts/cli/emo_cli.py status` → health check OK
- [ ] Run: `python scripts/cli/emo_cli.py submit summarize --tenant test` → orchestration works

## Security Verification
- [ ] Security headers present: CSP, HSTS, X-Frame-Options
- [ ] Default admin credentials are NOT in use
- [ ] `EMO_JWT_SECRET` is not the default value

## Known Constraints
- Single-node only (no horizontal scaling)
- SQLite-backed (not PostgreSQL)
- 100 pre-existing test failures quarantined (see `artifacts/debt/DEBT_RESOLUTION_PLAN.md`)
- Enterprise billing and distributed mesh are R2/R3 features
