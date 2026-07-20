mod backend;
mod commands;
mod security;

use backend::BackendSupervisor;
use tauri::{Manager, RunEvent};

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .manage(BackendSupervisor::default())
        .setup(|app| {
            let app_data = app
                .path()
                .app_data_dir()
                .map_err(|error| format!("app data directory unavailable: {error}"))?;
            let resource_dir = app
                .path()
                .resource_dir()
                .map_err(|error| format!("resource directory unavailable: {error}"))?;
            let executable = match std::env::var("DISCREPANCY_DESK_BACKEND_EXECUTABLE") {
                Ok(value) => std::path::PathBuf::from(value),
                Err(_) => {
                    let resource_candidate = resource_dir.join("backend").join("discrepancy-desk-backend.exe");
                    if resource_candidate.is_file() {
                        resource_candidate
                    } else {
                        std::env::current_exe()
                            .map_err(|error| error.to_string())?
                            .parent()
                            .ok_or_else(|| "desktop executable has no parent directory".to_string())?
                            .join("discrepancy-desk-backend.exe")
                    }
                }
            };
            std::fs::create_dir_all(&app_data)
                .map_err(|error| format!("app data directory creation failed: {error}"))?;
            let evidence_root = app_data.join("evidence");
            std::fs::create_dir_all(&evidence_root)
                .map_err(|error| format!("evidence directory creation failed: {error}"))?;
            let migrations_root = resource_dir.join("migrations");
            let database_path = app_data.join("discrepancy-desk.sqlite3");
            let supervisor = app.state::<BackendSupervisor>();
            supervisor
                .start(
                    executable.to_string_lossy().as_ref(),
                    &database_path.to_string_lossy(),
                    &evidence_root.to_string_lossy(),
                    &migrations_root.to_string_lossy(),
                )
                .map_err(|error| format!("governed backend startup failed: {error}"))?;
            if let Ok(value) = std::env::var("DISCREPANCY_DESK_DESKTOP_PROOF_AUTO_EXIT_MS") {
                let delay_ms: u64 = value
                    .parse()
                    .map_err(|_| "proof auto-exit delay must be an integer")?;
                if !(100..=60_000).contains(&delay_ms) {
                    return Err("proof auto-exit delay must be between 100 and 60000 ms".into());
                }
                let handle = app.handle().clone();
                std::thread::spawn(move || {
                    std::thread::sleep(std::time::Duration::from_millis(delay_ms));
                    let supervisor = handle.state::<BackendSupervisor>();
                    let _ = supervisor.stop();
                    handle.exit(0);
                });
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![commands::backend_session, commands::import_evidence_file])
        .build(tauri::generate_context!())
        .expect("desktop runtime failed");

    app.run(|handle, event| {
        if matches!(event, RunEvent::Exit | RunEvent::ExitRequested { .. }) {
            let supervisor = handle.state::<BackendSupervisor>();
            let _ = supervisor.stop();
        }
    });
}
