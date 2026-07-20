mod backend;
mod commands;
mod security;

use backend::BackendSupervisor;
use tauri::{Manager, RunEvent};

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .manage(BackendSupervisor::default())
        .setup(|app| {
            let executable = std::env::var("DISCREPANCY_DESK_BACKEND_EXECUTABLE")
                .map_err(|_| "DISCREPANCY_DESK_BACKEND_EXECUTABLE is not configured")?;
            let app_data = app
                .path()
                .app_data_dir()
                .map_err(|error| format!("app data directory unavailable: {error}"))?;
            std::fs::create_dir_all(&app_data)
                .map_err(|error| format!("app data directory creation failed: {error}"))?;
            let evidence_root = app_data.join("evidence");
            std::fs::create_dir_all(&evidence_root)
                .map_err(|error| format!("evidence directory creation failed: {error}"))?;
            let migrations_root = app
                .path()
                .resource_dir()
                .map_err(|error| format!("resource directory unavailable: {error}"))?
                .join("migrations");
            let database_path = app_data.join("discrepancy-desk.sqlite3");
            let supervisor = app.state::<BackendSupervisor>();
            supervisor
                .start(
                    &executable,
                    &database_path.to_string_lossy(),
                    &evidence_root.to_string_lossy(),
                    &migrations_root.to_string_lossy(),
                )
                .map_err(|error| format!("governed backend startup failed: {error}"))?;
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![commands::backend_session])
        .build(tauri::generate_context!())
        .expect("desktop runtime failed");

    app.run(|handle, event| {
        if matches!(event, RunEvent::Exit | RunEvent::ExitRequested { .. }) {
            let supervisor = handle.state::<BackendSupervisor>();
            let _ = supervisor.stop();
        }
    });
}
