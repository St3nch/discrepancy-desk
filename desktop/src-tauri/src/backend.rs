use serde::Serialize;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;

use crate::security::{generate_launch_token, loopback_base_url};

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct BackendSession { pub base_url: String, pub launch_token: String, pub api_version: String }

pub struct BackendSupervisor { child: Mutex<Option<Child>>, session: Mutex<Option<BackendSession>> }

impl Default for BackendSupervisor { fn default() -> Self { Self { child: Mutex::new(None), session: Mutex::new(None) } } }

impl BackendSupervisor {
    pub fn start(&self, executable: &str, port: u16) -> Result<BackendSession, String> {
        let mut child_guard = self.child.lock().map_err(|_| "backend lock poisoned")?;
        if child_guard.is_some() { return Err("backend already owns the desktop database".into()); }
        let token = generate_launch_token();
        let session = BackendSession { base_url: loopback_base_url(port), launch_token: token.clone(), api_version: "1".into() };
        let child = Command::new(executable)
            .env("DISCREPANCY_DESK_DESKTOP_TOKEN", &token)
            .env("DISCREPANCY_DESK_DESKTOP_HOST", "127.0.0.1")
            .env("DISCREPANCY_DESK_DESKTOP_PORT", port.to_string())
            .stdin(Stdio::null()).stdout(Stdio::null()).stderr(Stdio::piped())
            .spawn().map_err(|error| format!("backend start failed: {error}"))?;
        *child_guard = Some(child);
        *self.session.lock().map_err(|_| "session lock poisoned")? = Some(session.clone());
        Ok(session)
    }

    pub fn session(&self) -> Result<BackendSession, String> {
        self.session.lock().map_err(|_| "session lock poisoned")?.clone().ok_or_else(|| "backend not started".into())
    }

    pub fn stop(&self) -> Result<(), String> {
        if let Some(mut child) = self.child.lock().map_err(|_| "backend lock poisoned")?.take() { let _ = child.kill(); let _ = child.wait(); }
        *self.session.lock().map_err(|_| "session lock poisoned")? = None;
        Ok(())
    }
}
