# EMO AI Desktop

**Cross-platform desktop client for the EMO AI runtime.** Built with Tauri v2, React, TypeScript, and Rust.

| Component | Stack |
|-----------|-------|
| Frontend | React 18, TypeScript, Zustand, CSS |
| Backend IPC | Rust, Tauri v2, Serde |
| Security | OS Keychain (macOS Keychain, Windows Credential Manager, Linux Secret Service) |
| Distribution | NSIS (Windows), DMG (macOS), AppImage (Linux) |
| Tests | Vitest, Testing Library, Playwright |

## Quick Start

```bash
# Install dependencies
npm install

# Build Rust backend (requires Rust toolchain)
cargo build --manifest-path src-tauri/Cargo.toml

# Run tests
npm run test          # or: npx vitest run

# Development mode
npm run tauri dev
```

## Project Structure

```
emo-desktop/
├── src-tauri/          # Rust backend (IPC commands, keyring, build config)
├── ui/src/             # React frontend (routes, components, stores)
├── lib/                # Shared TypeScript libraries
│   ├── security/       #   Keychain validator, permission scanner, sandbox prober
│   └── telemetry/      #   Opt-in telemetry & crash reporting
├── tests/              # Test suites (36 files, 315+ tests)
│   ├── security/       #   Keychain enforcement, injection blocking, sandbox escape
│   ├── dist/           #   Installer integrity, auto-update, release manifests
│   ├── bridge/         #   Rust IPC bindings, keyring integration, runtime lifecycle
│   ├── docs/           #   Documentation readability and accuracy
│   ├── ui/             #   Command palette, wizard flow, trace explorer
│   ├── ux/             #   Screen live binding, design system consistency
│   └── gateway/        #   Routing, failover, rate limiting, telemetry
├── scripts/dist/       #   Build installers, update manifests, signature verification
├── docs/guides/        #   User, admin, security, deployment, and API guides
└── artifacts/          #   Release manifests, signing certificates, execution logs
```

## Core Principles

- **CORE FREEZE**: The `core/` directory and `releases/*/core/` are never modified
- **OS Keychain Only**: All credentials stored exclusively in OS keychain — no file-based fallback
- **Signed Distribution**: All packages must be signed (codesign, signtool, GPG); unsigned builds are blocked
- **Telemetry Opt-In**: Crash reporting and metrics are disabled by default; require explicit user consent
- **Zero Architectural Leakage**: No internal terms (DAG, Orchestrator, Execution Engine) in user-facing UI or docs

## Security

| Layer | Mechanism |
|-------|-----------|
| Credential Storage | OS Keychain via `keyring` crate |
| Injection Prevention | Pattern-based command injection blocking (7 categories) |
| Permission Scoping | Tool capability manifests with scope validation |
| Sandbox Isolation | Resource limits, filesystem confinement, network domain allowlists |
| Leakage Detection | Automated scan for plaintext keys, internal paths, architectural terms |

## License

Proprietary — EMO AI
