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

## Provider Credential Vault (P2)

Provider API keys use a two-layer security model:

### Layer 1: OS Keychain (Persistence)
- Keys stored exclusively in the OS-native keyring:
  - macOS: Keychain Services (Security.framework)
  - Windows: Credential Manager (CredWriteW / CredReadW)
  - Linux: libsecret (Secret Service / D-Bus)
- Managed via `@tauri-apps/plugin-keyring` Tauri plugin
- **Fallback Policy: BLOCK** — no plaintext fallback available
- Keys scoped under service name `emo-desktop` with prefix `provider_`

### Layer 2: Ephemeral Injection (Runtime Handoff)
When a provider key is needed by the runtime:

```
DESKTOP                OS KEYCHAIN              RUNTIME
  │                        │                       │
  │  1. readKey(pid)       │                       │
  │───────────────────────►│                       │
  │◄───────────────────────│                       │
  │      api_key           │                       │
  │                        │                       │
  │  2. inject via stdin   │                       │
  │  or isolated env       │                       │
  │───────────────────────────────────────────────►│
  │                        │                       │
  │  3. confirm receipt    │                       │
  │◄───────────────────────────────────────────────│
  │                        │                       │
  │  4. clear from memory  │                       │
  │  (≤5 seconds)          │                       │
  │                        │                       │
  │                        │                 4b. auto-clear
  │                        │                  after 5s or
  │                        │                 session stop
```

### Injection Methods
| Method | Mechanism | When Used |
|---|---|---|
| `stdin` (primary) | Key written to runtime stdin pipe | Normal operation |
| `env_isolated` (fallback) | Temp env var in isolated process space | stdin unavailable |

### Prohibited Storage Locations
- ❌ `.env` files
- ❌ `config.json` or any config file
- ❌ `localStorage` / `IndexedDB`
- ❌ Persistent environment variables
- ❌ Log files or console output

## IPC Commands (P2)

### `register_provider(provider_id, ephemeral_key)`
Injects a provider API key ephemerally into the runtime process.
Key is delivered via stdin or isolated env; runtime confirms receipt;
Desktop clears its copy within 5 seconds.

### `test_provider_connection(provider_id)`
Sends a lightweight probe to the provider API through the Model Gateway.
Returns reachability, status code, latency, and available model count.

### `get_gateway_routing_status()`
Returns the Model Gateway routing table: active routes, failover readiness,
cost tracking (total spent vs budget), and per-provider status with priority.

## Rotation & Revocation
- Session token rotated on every `start_runtime()`
- Old token immediately invalidated on rotation
- On `stop_runtime()`: token cleared, all pending requests cancelled
- Runtime error detection: if `/health` returns 401, session is considered expired
- **Provider key rotation**: `rotateKey(pid, newKey)` replaces via `saveKey` (single write)
- **Provider key revocation**: `deleteKey(pid)` removes from OS keychain immediately
- **Force clear**: `forceClearInjection(pid)` cancels pending timers and clears in-memory references

## Future Compatibility (P2+)
- Biometric unlock support
- Certificate-based mutual TLS for remote runtime connections
- HSM-backed key storage for enterprise deployments

## Contract Version
- **Version**: 1.1.0
- **Status**: DRAFT — Phase P2 (OS Keychain + Ephemeral Injection + Gateway Routing)
- **Last Updated**: 2026-05-29
