# EMO AI — Security Policy

## Code Freeze Constraints (RC18)

- NO new features allowed in frozen branches
- NO architectural law changes (LAW 1-27)
- ALLOWED: Critical release blockers, security patches, pilot documentation

## Security Principles

1. **Default Deny**: All operations denied unless explicitly allowed
2. **Human-in-the-Loop**: Destructive actions require approval
3. **Audit First**: Every action logged before execution
4. **Raw Evidence Only**: All claims must be backed by terminal output

## Secrets Management

- NEVER commit .env files, API keys, or credentials
- Use .env.example for documentation (empty values only)
- Rotate keys immediately if exposed
- Deleted — secrets_runtime.py removed (dead code, T-A15)

## Architectural Laws (LAW 1-27)

- LAW 10: No business logic in models
- LAW 13: Dependencies injected via constructor
- LAW 18: Trace analysis determinism
- LAW 23-27: Service mesh ownership and isolation
