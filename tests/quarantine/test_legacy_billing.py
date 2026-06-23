"""
legacy_billing — Pre-existing billing enterprise integration failures.

These tests require a full enterprise environment (billing engine, tenant router,
compliance auditor) that is not available in the current runtime. They are
quarantined until the Enterprise Pilot (ENT-PILOT-001) infrastructure is deployed.

Root cause: Legacy billing/enterprise modules not wired into current composition root.
Estimated effort: 5-8 hours (environment provisioning + integration tests).
"""
