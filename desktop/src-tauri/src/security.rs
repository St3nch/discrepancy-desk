use rand::{distributions::Alphanumeric, Rng};

pub fn generate_launch_token() -> String {
    rand::thread_rng().sample_iter(&Alphanumeric).take(64).map(char::from).collect()
}

pub fn loopback_base_url(port: u16) -> String { format!("http://127.0.0.1:{port}") }
