# Developer Guide — EMO Distributed AI Runtime OS (R1)

## §16.0 — R1 IMMUTABLE STATE

| Dimension | Value |
|---|---|
| **Release** | v1-runtime-stable |
| **Status** | 🔒 IMMUTABLE — CLOSED & ARCHIVED |
| **Tag** | `v1-runtime-stable` |
| **Branch** | `main` (frozen at v4.15.0-delivery-ready) |
| **Next Development** | `next-dev` branch (R2/R3) |
| **Zero modifications** | Any change to `core/`, `scripts/`, `tests/`, or `interfaces/` in R1 is PROHIBITED |

### Isolation Rules
1. **No backports**: Bug fixes or features for R1 will NOT be backported.
   Users must upgrade to the next release.
2. **No patches**: The release archive is immutable. Patches must target `next-dev`.
3. **No cross-contamination**: R1 source, docs, and artifacts are fully isolated
   in `/releases/emo-runtime-os/`. The root workspace is for `next-dev` only.
4. **Governance lock**: `RELEASE_MANIFEST_R1.json` and `SIGNING_MANIFEST_R1.json`
   certify the immutable state. Any deviation invalidates the certification.

### Quality Gates (Certified)
- High-Signal Ratio: ≥85%
- Regressions: 0
- Canon Compliance: 100%
- Trace Propagation: 100%
- Replay Integrity: PASS
- Isolation Validation: PASS

### Snapshot Contents
- `source/core/` — Runtime, memory, orchestration, composition, interfaces
- `source/scripts/` — CLI, benchmark, validation, release tooling
- `source/tests/` — All test suites (Phase L, G, Final Prep, quarantine)
- `source/main.py` — Application entry point with security hardening
- `source/middleware/auth.py` — JWT auth with refresh lifecycle
- `source/pytest.ini` — Test configuration with quarantined marker

### Transition to next-dev (R2)
```bash
git checkout -b next-dev main
# R2 development starts here
```

For full details, see `R1_CLOSURE_REPORT.md` and `certificates/RELEASE_MANIFEST_R1.json`.
