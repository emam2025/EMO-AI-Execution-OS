use serde::{Deserialize, Serialize};
use std::process::{Child, Command};
use std::sync::Mutex;
use tauri::State;

// ──────────────────────────────────────────────
// Types
// ──────────────────────────────────────────────

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct RuntimeInfo {
    pub pid: u32,
    pub port: u16,
    pub status: String,
    pub session_token: String,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct RuntimeStatus {
    pub running: bool,
    pub pid: Option<u32>,
    pub port: Option<u16>,
    pub healthy: bool,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct AgentResult {
    pub run_id: String,
    pub status: String,
    pub result: String,
    pub elapsed_seconds: f64,
}

pub struct RuntimeProcess {
    pub child: Option<Child>,
    pub pid: u32,
    pub port: u16,
    pub session_token: String,
}

// ──────────────────────────────────────────────
// IPC Commands
// ──────────────────────────────────────────────

/// Starts the backend binary (Nuitka/PyInstaller build) with resource isolation.
#[tauri::command]
pub fn start_runtime(
    state: State<'_, Mutex<Option<RuntimeProcess>>>,
) -> Result<RuntimeInfo, String> {
    let mut guard = state.lock().map_err(|e| e.to_string())?;

    if let Some(proc) = guard.as_ref() {
        return Ok(RuntimeInfo {
            pid: proc.pid,
            port: proc.port,
            status: "running".into(),
            session_token: proc.session_token.clone(),
        });
    }

    let port: u16 = 8080;
    let session_token = uuid::Uuid::new_v4().to_string();

    // Launch the bundled Python binary (Nuitka/PyInstaller output).
    // Path resolution:
    //   dev: ../../dist/emo-desktop
    //   prod: resources/emo-runtime
    let binary_path = if cfg!(debug_assertions) {
        std::env::current_dir()
            .unwrap_or_default()
            .join("../../dist/emo-desktop")
    } else {
        std::env::current_exe()
            .unwrap_or_default()
            .parent()
            .unwrap_or(std::path::Path::new("."))
            .join("resources/emo-runtime")
    };

    let child = Command::new(&binary_path)
        .arg("--port")
        .arg(port.to_string())
        .arg("--session")
        .arg(&session_token)
        .spawn()
        .map_err(|e| format!("Failed to start runtime: {}", e))?;

    let pid = child.id();

    let process = RuntimeProcess {
        child: Some(child),
        pid,
        port,
        session_token: session_token.clone(),
    };

    *guard = Some(process);

    Ok(RuntimeInfo {
        pid,
        port,
        status: "starting".into(),
        session_token,
    })
}

/// Stops the runtime process by PID with memory cleanup.
#[tauri::command]
pub fn stop_runtime(
    state: State<'_, Mutex<Option<RuntimeProcess>>>,
) -> Result<(), String> {
    let mut guard = state.lock().map_err(|e| e.to_string())?;

    if let Some(proc) = guard.take() {
        if let Some(mut child) = proc.child {
            child.kill().map_err(|e| format!("Failed to stop runtime: {}", e))?;
            child.wait().ok();
        }
    }

    Ok(())
}

/// Returns the current runtime health status.
#[tauri::command]
pub fn get_runtime_status(
    state: State<'_, Mutex<Option<RuntimeProcess>>>,
) -> Result<RuntimeStatus, String> {
    let mut guard = state.lock().map_err(|e| e.to_string())?;

    match guard.as_mut() {
        Some(proc) => {
            let healthy = proc
                .child
                .as_mut()
                .map(|c| c.try_wait().ok().flatten().is_none())
                .unwrap_or(false);

            Ok(RuntimeStatus {
                running: healthy,
                pid: Some(proc.pid),
                port: Some(proc.port),
                healthy,
            })
        }
        None => Ok(RuntimeStatus {
            running: false,
            pid: None,
            port: None,
            healthy: false,
        }),
    }
}

/// Stores an API key in the OS keychain.
#[tauri::command]
pub fn set_api_key(provider: String, key: String) -> Result<(), String> {
    if key.len() < 8 {
        return Err("Key must be at least 8 characters".into());
    }
    let entry = keyring::Entry::new("emo-desktop", &format!("provider_{}", provider))
        .map_err(|e| format!("Keyring entry error: {}", e))?;
    entry.set_password(&key).map_err(|e| format!("Keyring error: {}", e))
}

/// Retrieves an API key from the OS keychain.
#[tauri::command]
pub fn get_api_key(provider: String) -> Result<String, String> {
    let entry = keyring::Entry::new("emo-desktop", &format!("provider_{}", provider))
        .map_err(|e| format!("Keyring entry error: {}", e))?;
    entry.get_password().map_err(|e| format!("Keyring error: {}", e))
}

/// Deletes an API key from the OS keychain.
#[tauri::command]
pub fn delete_api_key(provider: String) -> Result<(), String> {
    let entry = keyring::Entry::new("emo-desktop", &format!("provider_{}", provider))
        .map_err(|e| format!("Keyring entry error: {}", e))?;
    entry.delete_password().map_err(|e| format!("Keyring error: {}", e))
}

/// Sends a task to the runtime and returns the agent result.
///
/// Extracts `instruction` from the frontend AgentTask, POSTs it to the
/// backend FastAPI `/api/ai/run` endpoint, and maps the response back.
#[tauri::command]
pub fn run_agent(
    task: serde_json::Value,
    state: State<'_, Mutex<Option<RuntimeProcess>>>,
) -> Result<AgentResult, String> {
    let guard = state.lock().map_err(|e| e.to_string())?;
    let proc = guard.as_ref().ok_or_else(|| "Runtime not started".to_string())?;

    let instruction = task
        .get("instruction")
        .and_then(|v| v.as_str())
        .ok_or_else(|| "Task must contain an 'instruction' field".to_string())?
        .to_string();

    let url = format!("http://localhost:{}/api/ai/run", proc.port);
    let run_id = uuid::Uuid::new_v4().to_string();
    let start = std::time::Instant::now();

    let resp = ureq::post(&url)
        .query("query", &instruction)
        .query("strategy", "balanced")
        .set("Accept", "application/json")
        .timeout(std::time::Duration::from_secs(300))
        .call()
        .map_err(|e| match e {
            ureq::Error::Status(code, response) => {
                let body = response.into_string().unwrap_or_default();
                format!("Runtime API error ({}): {}", code, body)
            }
            ureq::Error::Transport(e) => {
                format!("Runtime API unreachable: {} — is the runtime running on port {}?", e, proc.port)
            }
        })?;

    let body_str = resp
        .into_string()
        .map_err(|e| format!("Failed to read runtime response: {}", e))?;
    let body: serde_json::Value = serde_json::from_str(&body_str)
        .map_err(|e| format!("Invalid JSON from runtime: {}", e))?;

    let elapsed = start.elapsed().as_secs_f64();
    let answer = body
        .get("answer")
        .and_then(|v| v.as_str())
        .unwrap_or("(no answer)");
    let plan = body
        .get("plan")
        .map(|v| serde_json::to_string(v).unwrap_or_default())
        .unwrap_or_default();
    let steps = body
        .get("steps")
        .and_then(|v| v.as_array())
        .map(|a| a.len())
        .unwrap_or(0);

    let result = format!(
        "Answer: {}\n\nPlan: {}\nSteps executed: {}",
        answer, plan, steps
    );

    Ok(AgentResult {
        run_id,
        status: "completed".to_string(),
        result,
        elapsed_seconds: elapsed,
    })
}
