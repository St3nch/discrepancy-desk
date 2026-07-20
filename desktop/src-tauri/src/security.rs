use rand::{distributions::Alphanumeric, Rng};

pub fn generate_launch_token() -> String {
    rand::thread_rng().sample_iter(&Alphanumeric).take(64).map(char::from).collect()
}

pub fn loopback_base_url(port: u16) -> String { format!("http://127.0.0.1:{port}") }


#[cfg(test)]
mod tests {
    use super::{generate_launch_token, loopback_base_url};

    #[test]
    fn launch_tokens_are_long_and_distinct() {
        let first = generate_launch_token();
        let second = generate_launch_token();
        assert_eq!(first.len(), 64);
        assert_eq!(second.len(), 64);
        assert_ne!(first, second);
        assert!(first.chars().all(|value| value.is_ascii_alphanumeric()));
    }

    #[test]
    fn backend_url_is_loopback_only() {
        assert_eq!(loopback_base_url(43127), "http://127.0.0.1:43127");
    }
}
