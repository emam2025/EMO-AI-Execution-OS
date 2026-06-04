mod commands;

use tauri::Manager;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(std::sync::Mutex::new(None::<commands::RuntimeProcess>))
        .invoke_handler(tauri::generate_handler![
            commands::start_runtime,
            commands::stop_runtime,
            commands::get_runtime_status,
            commands::set_api_key,
            commands::run_agent,
        ])
        .setup(|app| {
            #[cfg(debug_assertions)]
            {
                let window = app.get_webview_window("main").unwrap();
                window.open_devtools();
            }
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running EMO Desktop");
}
