/**
 * Tauri App Entry — IPC Setup
 *
 * Skeleton entry point for the Tauri desktop application.
 * Registers IPC command handlers that will bridge to the emo-runtime-service.
 */
import { app, BrowserWindow } from "@tauri-apps/api";
import { invoke } from "@tauri-apps/api/core";

// IPC command handlers registered in Rust backend (src-tauri/src/main.rs)
// These are invoked from the renderer via runtime_bridge.ts.
//
// Commands:
//   - start_runtime       → Launch emo-runtime-service process
//   - stop_runtime        → Gracefully terminate runtime by PID
//   - get_runtime_status  → Proxy GET /api/health
//   - stream_events       → Open WebSocket to runtime.events
//   - get_trace           → Proxy GET /api/trace/{trace_id}

async function main() {
  await app.getVersion();

  const win = new BrowserWindow({
    title: "EMO Desktop",
    width: 1280,
    height: 800,
    resizable: true,
  });

  await win.loadURL("http://localhost:5173");
}

main().catch(console.error);
