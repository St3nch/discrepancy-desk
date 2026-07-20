use rand::{distributions::Alphanumeric, Rng};
use std::path::Path;
use tauri::{AppHandle, Manager, State};

use crate::backend::{BackendSession, BackendSupervisor};

#[tauri::command]
pub fn backend_session(
    supervisor: State<'_, BackendSupervisor>,
) -> Result<BackendSession, String> {
    supervisor.session()
}

#[tauri::command]
pub fn import_evidence_file(app: AppHandle, source_path: String) -> Result<String, String> {
    let source = Path::new(&source_path)
        .canonicalize()
        .map_err(|error| format!("selected evidence path is unavailable: {error}"))?;
    let metadata = source
        .metadata()
        .map_err(|error| format!("selected evidence metadata is unavailable: {error}"))?;
    if !metadata.is_file() {
        return Err("selected evidence path is not a file".into());
    }
    if metadata.len() > 100 * 1024 * 1024 {
        return Err("selected evidence file exceeds the 100 MiB desktop limit".into());
    }
    let extension = source
        .extension()
        .and_then(|value| value.to_str())
        .filter(|value| value.chars().all(|ch| ch.is_ascii_alphanumeric()))
        .map(|value| format!(".{value}"))
        .unwrap_or_default();
    let name: String = rand::thread_rng()
        .sample_iter(&Alphanumeric)
        .take(32)
        .map(char::from)
        .collect();
    let root = app
        .path()
        .app_data_dir()
        .map_err(|error| format!("app data directory unavailable: {error}"))?
        .join("evidence")
        .join("inbox");
    std::fs::create_dir_all(&root)
        .map_err(|error| format!("evidence inbox creation failed: {error}"))?;
    let destination = root.join(format!("{name}{extension}"));
    std::fs::copy(&source, &destination)
        .map_err(|error| format!("evidence import failed: {error}"))?;
    Ok(format!("inbox/{name}{extension}"))
}
