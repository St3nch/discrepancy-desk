mod backend;
mod commands;
mod security;

use backend::BackendSupervisor;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(BackendSupervisor::default())
        .invoke_handler(tauri::generate_handler![commands::backend_session])
        .run(tauri::generate_context!())
        .expect("desktop runtime failed");
}
