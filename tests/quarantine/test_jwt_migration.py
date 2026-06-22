"""
jwt_migration — Pre-existing JWT security migration failures.

These tests validate JWT lifecycle (expiry 2h, refresh tokens, one-time use,
replay detection) and status endpoint auth protection. They fail because the
JWT implementation was migrated but some test assertions reference old behavior.

Root cause: JWT migration in progress (EMO_JWT_SECRET hardening, refresh token lifecycle).
Estimated effort: 2-3 hours (update test assertions + env setup).
"""
