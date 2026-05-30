# Production Deployment Guide — v4.7.0-prod-ready

## Overview

Deployment guide for EMO AI Runtime v4.7.0-prod-ready. This release has passed
full production readiness certification with 100% canon compliance, 0 regressions,
and all critical guards enforced.

Ref: Canon LAW 1-27, RULE 1-5
Ref: DEVELOPER.md §16 (Architecture Canon)
Ref: ROADMAP 🔟 FINAL DELIVERY STAGE

---

## 1. Pre-Deployment Checklist

| Check | Command / Action | Expected |
|-------|-----------------|----------|
| Canon compliance | `python3 -m scripts.release.certificate_engine` | 100% — all phases compliant |
| Test suite | `python3 -m pytest tests/ -x --tb=short` | 2616+ passed, 10 skipped, 3 pre-existing |
| Guards enforced | Verify `RELEASE_CERTIFICATE.json` guard matrix | All critical guards passed |
| Architecture drift | CodeGraph baseline comparison | 0 drift detected |
| Dependency lock | `scripts/release/baseline_freezer.py` lock | All dependencies found and hashed |

---

## 2. Deployment Steps

### Step 1: Pull Release Artifacts

```bash
git checkout v4.7.0-prod-ready
python3 -m scripts.release.certificate_engine --verify
```

### Step 2: Verify Certificate

```bash
python3 -c "
import json
with open('artifacts/release/RELEASE_CERTIFICATE.json') as f:
    cert = json.load(f)
assert cert['overall_status'] == 'APPROVED', 'Release not approved!'
print(f'Version: {cert[\"version\"]}')
print(f'Tests: {cert[\"test_matrix\"][\"total_passed\"]}/{cert[\"test_matrix\"][\"total_tests\"]}')
print(f'Canon: {cert[\"canon_compliance\"][\"overall_pct\"]}%')
"
```

### Step 3: Canary Deployment (10% traffic)

```bash
# Deploy to canary namespace
kubectl apply -f k8s/canary/deployment.yaml
# Verify canary health
kubectl rollout status deployment/emo-runtime-canary -n canary
# Run smoke tests
python3 -m pytest tests/test_j3_readiness_integration.py -v
```

### Step 4: Gradual Rollout

| Stage | Traffic % | Duration | Validation |
|-------|-----------|----------|------------|
| Canary | 10% | 30 min | P99 < 200ms, error rate < 1% |
| Early | 25% | 60 min | All guards passing |
| Half | 50% | 120 min | No oscillation detected |
| Full | 100% | — | Production snapshot frozen |

### Step 5: Production Freeze

```bash
# Freeze production baseline
python3 -c "
from scripts.release.baseline_freezer import BaselineFreezer
f = BaselineFreezer()
f.lock_dependencies(['core/readiness/', 'core/composition/root.py', 'artifacts/release/RELEASE_CERTIFICATE.json'])
f.generate_signing_manifest('artifacts/release/SIGNING_MANIFEST.md', {'release': 'v4.7.0-prod-ready'})
print('Production baseline frozen.')
"
```

---

## 3. Rollback Plan

| Scenario | Rollback Action | Recovery Time |
|----------|----------------|---------------|
| P99 exceeds 200ms | Revert to previous deployment | < 5 min |
| Error rate > 5% | Scale down, activate canary | < 3 min |
| Oscillation detected | Rollback to last stable snapshot | < 10 min |
| Data integrity failure | Restore from I1 snapshot | < 15 min |
| Certification guard fails | Block deployment, alert on-call | Immediate |

---

## 4. Feature Flags

| Flag | Default | Purpose |
|------|---------|---------|
| `chaos_injection_enabled` | False | Enable chaos engineering in production |
| `strict_readiness_mode` | False | Enforce readiness guards in production |
| `strict_release_mode` | False | Enforce release freeze guards |
| `oscillation_detection_enabled` | True | Enable load oscillation monitoring |

---

## 5. Monitoring & Alerts

### Key Metrics

| Metric | Source | Warning | Critical |
|--------|--------|---------|----------|
| `readiness.certification.score` | CertificationGate | < 0.85 | < 0.70 |
| `readiness.load.p99_ms` | LoadOrchestrator | > 150ms | > 200ms |
| `readiness.load.oscillation_score` | LoadOrchestrator | > 0.2 | > 0.3 |
| `readiness.chaos.recovery_slo_met` | ChaosInjector | < 1.0 (any) | — |

### Post-Deployment Validation

```bash
# Run full certification check
python3 -m pytest tests/test_final_release_certification.py -v
# Verify release certificate
python3 -c "
import json
with open('artifacts/release/RELEASE_CERTIFICATE.json') as f:
    print(json.dumps(json.load(f), indent=2))
"
```

---

## 6. Architecture Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                     F1 UnifiedRuntime API                    │
├────────────────┬───────────────┬────────────────────────────┤
│  I1 Infra      │  I2 Data      │  I3 Reliability            │
│  (K8s/Storage) │  (PostgreSQL) │  (Failover/Recovery)       │
├────────────────┴───────────────┴────────────────────────────┤
│                  Phase FINAL Certification                   │
│  (Audit → Load Test → Security → Compliance → Certify)      │
├────────────────┬───────────────┬────────────────────────────┤
│  J1 DevEx      │  J2 Enterprise│  J3 Production Readiness   │
│  (SDK/CLI)     │  (Multi-Tenant)│  (Chaos/Load/Cert)        │
├────────────────┴───────────────┴────────────────────────────┤
│                  F4 Observability & Release Certification   │
└─────────────────────────────────────────────────────────────┘
```

---

## 7. Contacts

| Role | Responsibility |
|------|---------------|
| DevOps Engineer | Deployment orchestration, rollback |
| SRE | Production monitoring, alert response |
| Runtime Team | Core runtime health, guard validation |
| Security Team | Compliance audit, certificate verification |
