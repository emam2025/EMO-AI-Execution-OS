# Known Production Constraints — Certified Trade-Offs  # LAW-5 # LAW-18

*Generated at: 2026-05-28T11:36:50Z*
*Version: 4.10.1-human-validated*

This document catalogs all known production constraints accepted as
**Certified Trade-Offs** for the v4.10.1 pilot release. Each constraint
is linked to a Canon Law and has an explicit mitigation strategy.

---

| ID | Area | Description | Canon Law | Mitigation | Severity |
|----|------|-------------|-----------|------------|----------|
| **PC-001** | Persistence | SQLite-based EventStore — writes are single-node. At > 10k events/sec the WAL becomes a bottleneck. | LAW 5, LAW 20 | Replace with PostgreSQL or distributed log (Phase I2 ready, not activated). Monitor WAL lag. Triggers at 8k events/sec. | medium |
| **PC-002** | Replay | Replay determinism is ≥ 99.3% but not 100% — time-dependent operations (wall_clock, random seeds) drift across runs. | LAW 3, LAW 18 | Accept ≤ 0.7% drift for time-dependent DAGs. Isolate time via TimeProvider interface in future. | low |
| **PC-003** | Scale | Worker pool is fixed at construction time (default 4, max 256). No dynamic auto-scaling in production. | LAW 13, F2 | Auto-scaler implemented but not activated. Manual scaling via operator action. Set target count via `build_final_release(worker_pool_size=N)`. | medium |
| **PC-004** | Observability | TopologyViewer returns static/mocked data — no live agent inventory. Operator CLI shows placeholder worker topology. | LAW 5 | Post-freeze agent discovery integration. Current worker count hardcoded to 3. Acceptable for pilot. | low |
| **PC-005** | Replay Drift | ReplayDrift metric reports 0.0 (placeholder) — no actual cross-run drift measurement implemented. | LAW 3, LAW 12 | Accurate drift requires replay baseline comparison. Accept 0.0 placeholder for pilot. Tracked as AD-007. | low |
| **PC-006** | Operator UI | Operator UI is single-process (no auth, no TLS, no multi-session). Suitable for local pilot only. | LAW 10 | Wrap behind reverse proxy with basic auth for >3 users. TLS and session management not implemented. | medium |
| **PC-007** | Agent Layer | Multi-agent layer (G5) has zero test coverage — conceptual only. Not activated in production. | LAW 5, RULE 2 | Deferred to K6 phase. No runtime impact — layer is not wired in CompositionRoot. | low |
| **PC-008** | Auth — Rate Limiting | `/api/auth/refresh` has no rate limiting — brute-force refresh token rotation possible. | LAW 3, RULE 2 | Add in-memory rate limiter (10 req/min per user) before wider deployment. Acceptable for pilot ≤5 tenants. | medium |
| **PC-009** | Auth — Token Replay Persistence | Refresh token replay detection uses in-memory store — server restart loses token state. | LAW 3, RULE 2 | Migrate to persistent store (Redis/DB) post-freeze. Acceptable for single-node pilot. | low |
| **PC-010** | Auth — Migration | JWT lifecycle hardening (2h expiry, refresh rotation, one-time-use) deployed in-place — no active session migration path. | LAW 3 | Existing sessions expire within 2h requiring re-login. Acceptable for pilot. | low |

---

## Signature

**SHA-256:** `c7a58c7a6a1710284690cf44d6cb5fea87023075686f269d027e56dee583a2a3`

*This document is digitally signed. Any modification invalidates the signature.*