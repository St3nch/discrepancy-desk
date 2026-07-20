use tauri::State;
use crate::backend::{BackendSession, BackendSupervisor};

#[tauri::command]
pub fn backend_session(supervisor: State<'_, BackendSupervisor>) -> Result<BackendSession, String> { supervisor.session() }
