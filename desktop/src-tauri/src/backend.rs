use serde::Serialize;
use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::thread;
use std::time::{Duration, Instant};

use crate::security::{generate_launch_token, loopback_base_url};

#[derive(Clone, Serialize)]
#[serde(rename_all = "camelCase")]
pub struct BackendSession {
    pub base_url: String,
    pub launch_token: String,
    pub api_version: String,
}

pub struct BackendSupervisor {
    child: Mutex<Option<Child>>,
    session: Mutex<Option<BackendSession>>,
}

impl Default for BackendSupervisor {
    fn default() -> Self {
        Self {
            child: Mutex::new(None),
            session: Mutex::new(None),
        }
    }
}

impl BackendSupervisor {
    pub fn reserve_loopback_port() -> Result<u16, String> {
        let listener = TcpListener::bind(("127.0.0.1", 0))
            .map_err(|error| format!("unable to reserve loopback port: {error}"))?;
        listener
            .local_addr()
            .map(|address| address.port())
            .map_err(|error| format!("unable to inspect loopback port: {error}"))
    }

    pub fn start(
        &self,
        executable: &str,
        database_path: &str,
        evidence_root: &str,
        migrations_root: &str,
    ) -> Result<BackendSession, String> {
        let mut child_guard = self.child.lock().map_err(|_| "backend lock poisoned")?;
        if child_guard.is_some() {
            return Err("backend already owns the desktop database".into());
        }

        let port = Self::reserve_loopback_port()?;
        let token = generate_launch_token();
        let session = BackendSession {
            base_url: loopback_base_url(port),
            launch_token: token.clone(),
            api_version: "1".into(),
        };
        let child = Command::new(executable)
            .env("DISCREPANCY_DESK_DESKTOP_TOKEN", &token)
            .env("DISCREPANCY_DESK_DESKTOP_HOST", "127.0.0.1")
            .env("DISCREPANCY_DESK_DESKTOP_PORT", port.to_string())
            .env("DISCREPANCY_DESK_DESKTOP_DATABASE", database_path)
            .env("DISCREPANCY_DESK_DESKTOP_EVIDENCE_ROOT", evidence_root)
            .env("DISCREPANCY_DESK_DESKTOP_MIGRATIONS_ROOT", migrations_root)
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::piped())
            .spawn()
            .map_err(|error| format!("backend start failed: {error}"))?;

        *child_guard = Some(child);
        drop(child_guard);

        if let Err(error) = self.wait_until_healthy(&session, Duration::from_secs(15)) {
            let _ = self.stop();
            return Err(error);
        }
        *self.session.lock().map_err(|_| "session lock poisoned")? = Some(session.clone());
        Ok(session)
    }

    fn wait_until_healthy(
        &self,
        session: &BackendSession,
        timeout: Duration,
    ) -> Result<(), String> {
        let deadline = Instant::now() + timeout;
        while Instant::now() < deadline {
            if self.child_exited()? {
                return Err("backend exited before becoming healthy".into());
            }
            if health_request(session).is_ok() {
                return Ok(());
            }
            thread::sleep(Duration::from_millis(100));
        }
        Err("backend health check timed out".into())
    }

    fn child_exited(&self) -> Result<bool, String> {
        let mut guard = self.child.lock().map_err(|_| "backend lock poisoned")?;
        match guard.as_mut() {
            Some(child) => child
                .try_wait()
                .map(|status| status.is_some())
                .map_err(|error| format!("backend status check failed: {error}")),
            None => Ok(true),
        }
    }

    pub fn session(&self) -> Result<BackendSession, String> {
        self.session
            .lock()
            .map_err(|_| "session lock poisoned")?
            .clone()
            .ok_or_else(|| "backend not started".into())
    }

    pub fn stop(&self) -> Result<(), String> {
        if let Some(mut child) = self.child.lock().map_err(|_| "backend lock poisoned")?.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
        *self.session.lock().map_err(|_| "session lock poisoned")? = None;
        Ok(())
    }
}

fn health_request(session: &BackendSession) -> Result<(), String> {
    let address = session
        .base_url
        .strip_prefix("http://")
        .ok_or_else(|| "backend URL is not loopback HTTP".to_string())?;
    let socket_address = address
        .parse()
        .map_err(|_| "backend address is invalid".to_string())?;
    let mut stream = TcpStream::connect_timeout(&socket_address, Duration::from_millis(250))
        .map_err(|error| format!("backend health connection failed: {error}"))?;
    stream
        .set_read_timeout(Some(Duration::from_millis(500)))
        .map_err(|error| format!("backend health timeout failed: {error}"))?;
    let request = format!(
        "GET /desktop-api/v1/health HTTP/1.1\r\nHost: {address}\r\nX-Discrepancy-Desk-Token: {}\r\nConnection: close\r\n\r\n",
        session.launch_token
    );
    stream
        .write_all(request.as_bytes())
        .map_err(|error| format!("backend health request failed: {error}"))?;
    let mut response = String::new();
    stream
        .read_to_string(&mut response)
        .map_err(|error| format!("backend health response failed: {error}"))?;
    if response.starts_with("HTTP/1.1 200") || response.starts_with("HTTP/1.0 200") {
        Ok(())
    } else {
        Err("backend health response was not successful".into())
    }
}


#[cfg(test)]
mod tests {
    use super::BackendSupervisor;

    #[test]
    fn reserved_port_is_nonzero_and_available_for_loopback() {
        let port = BackendSupervisor::reserve_loopback_port()
            .expect("loopback port reservation should succeed");
        assert!(port > 0);
    }
}
