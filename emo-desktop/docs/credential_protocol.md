# Credential Protocol — EMO Desktop Authentication

## Overview
Defines how EMO Desktop authenticates with the emo-runtime-service and
how credentials are stored, rotated, and invalidated.

## Session Token Lifecycle

```
start_runtime() → st_<uuid4> (generated)
       │
       ▼
  Active session (stored in memory, NOT persisted to disk)
       │
       ├── stop_runtime() → token invalidated
       │
       └── new start_runtime() → old token replaced
```

### Properties
- Token format: `st_<uuid4>` (36 hex chars + "st_" prefix)
- Single active session at any time
- Tokens are held in memory only (Zustand store, cleared on reset)
- NO localStorage, NO sessionStorage, NO cookies for session tokens

## Authorization Header

All IPC commands (except `start_runtime()`) carry the token:
```
Authorization: Bearer st_a1b2c3d4-e5f6-7890-abcd-ef1234567890
```

## Credential Storage Rules

| Credential | Storage | Persistence |
|---|---|---|
| Session token | Zustand store (in-memory) | None (cleared on close) |
| Runtime host/port | Zustand store (in-memory) | Optional localStorage |
| LLM API keys | OS Keychain (P2) | System keychain |
| EMO_JWT_SECRET | Never stored in Desktop | Runtime env only |

## Rotation & Revocation
- Session token rotated on every `start_runtime()`
- Old token immediately invalidated on rotation
- On `stop_runtime()`: token cleared, all pending requests cancelled
- Runtime error detection: if `/health` returns 401, session is considered expired

## Future Compatibility (P2)
- OS Keychain integration (macOS Keychain, Windows Credential Manager, libsecret)
- Biometric unlock support
- Certificate-based mutual TLS for remote runtime connections

## Contract Version
- **Version**: 1.0.0
- **Status**: DRAFT — Phase P1
