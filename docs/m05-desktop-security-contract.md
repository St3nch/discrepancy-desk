# M05 Desktop Security Contract

## Status

Package A first implementation batch prepared for owner review.

## Authority Boundary

The desktop frontend is presentation and operator-intent collection only. It does not open SQLite, calculate approval authority, mark content Ready-to-Post independently, publish to a platform, or execute arbitrary processes.

All business operations remain in the existing governed Python service and query layer.

## Desktop API Boundary

Desktop API mode is opt-in at application construction and uses versioned routes under:

```text
/desktop-api/v1/
```

Every desktop API request requires the ephemeral launch token in:

```text
x-discrepancy-desk-token
```

Missing or incorrect tokens are refused before route execution. Refusal responses state that persisted records were preserved and no mutation occurred.

The normal FastAPI/Jinja web harness remains available independently and does not silently enable desktop API mode.

## Loopback and Token Rules

The Rust supervisor contract:

- constructs only `http://127.0.0.1:<port>` backend URLs;
- passes the launch token through a child-process environment variable;
- does not pass the token through command-line arguments;
- redirects standard output away from the frontend;
- retains standard error only for bounded startup diagnostics;
- rejects a second child while one backend owns the desktop database;
- clears the process and session on stop.

The packaged sidecar entrypoint, dynamic port allocation, health polling, restart policy, and exact executable resolution remain to be completed in the next Package A batch.

## Tauri Capability Boundary

The current capability file assigns only:

```text
core:default
```

to the bundled `main` window. It grants no shell, filesystem, updater, global-shortcut, remote-origin, or arbitrary-window capability.

The Tauri configuration:

- uses a loopback-only Vite development URL;
- restricts CSP network access to loopback HTTP;
- declares NSIS current-user packaging only;
- does not configure an updater;
- does not configure remote webview origins.

## Frontend Dependency Boundary

The desktop frontend depends on React, Vite, TypeScript, and the Tauri API. It has no SQLite dependency and contains no SQL or direct persistence command surface.

The frontend retrieves a backend session through the single custom Rust command `backend_session`, then sends the launch token only as the required local API header.

## Current Validation

```text
uv run ruff check .                                      passed
uv run pytest tests/test_m05_desktop_api_contract.py     passed
uv run pytest tests/test_m05_desktop_security.py         passed
uv run pytest tests/test_m05_sidecar_lifecycle.py        passed
uv run pytest -q                                         79 passed
pnpm --dir desktop build                                 passed
npm package-lock-only resolution                         0 reported vulnerabilities
```

## Explicit Validation Limitation

The approved repository tool exposes Node and pnpm but does not expose Cargo or Rust compilation. Therefore:

- Rust source and configuration are covered by static contract tests;
- no successful `cargo check`, `cargo test`, `tauri build`, or native executable claim is made;
- native compilation remains a mandatory gate before Package A can close.

## Stop Conditions Still Active

Stop and return for owner ruling if native implementation requires:

- direct database access from Rust or React;
- broad shell or filesystem capability;
- remote API origins;
- updater activation;
- a public distribution endpoint;
- a second persistence authority;
- a material change outside the accepted M05 path list.
