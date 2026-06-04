# Developer Guide

## Prerequisites

- **Node.js** >= 18
- **Rust** (latest stable via rustup)
- **Tauri CLI**: `cargo install tauri-cli --version "^2"`
- **Platform-specific**:
  - macOS: Xcode Command Line Tools
  - Windows: Visual Studio Build Tools, NSIS
  - Linux: `libwebkit2gtk-4.1-dev`, `libappindicator3-dev`

## Test Commands

```bash
npx vitest run         # Run all 315+ tests
npx vitest run --reporter=verbose  # Verbose output
npx vitest run tests/security/     # Security test suite only
```

## Adding Tests

1. Create file in `tests/<category>/test_<name>.ts`
2. Import from `lib/` or `ui/src/` using relative paths
3. Never import from `core/` or `releases/*/core/`
4. Run `npx vitest run` to verify

## Building for Distribution

```bash
# Build installers (requires platform tooling)
bash scripts/dist/build-installers.sh

# Generate update manifest
npx tsx scripts/dist/generate-update-manifest.ts

# Verify signatures
bash scripts/dist/verify-signatures.sh

# Run leakage scanner
bash scripts/security/leakage-scanner.sh
```

## Rust Backend (src-tauri/)

IPC commands available:

| Command | Description |
|---------|-------------|
| `start_runtime` | Launch backend binary with resource isolation |
| `stop_runtime` | Gracefully stop runtime process |
| `get_runtime_status` | Check runtime health (PID, port, alive) |
| `set_api_key` | Store API key in OS keychain |
| `run_agent` | Execute agent task via runtime HTTP API |

## Configuration

- `src-tauri/tauri.conf.json` — Tauri v2 configuration (CSP, updater, window)
- `src-tauri/Cargo.toml` — Rust dependencies and build settings
- `vitest.config.ts` — Test runner configuration (7 test directories)

## Code Style

- React: Functional components with hooks, no class components
- State: Zustand stores with `useRuntimeStore` as the primary store
- Styling: Inline styles + `glass-panel.css` design system
- Naming: camelCase for variables/functions, PascalCase for components/types
- Security: Every IPC command validates input; all credential operations are audited
