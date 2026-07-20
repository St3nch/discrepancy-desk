# M05 Desktop Security Contract

## Status

M05 owner-accepted and closed. This contract reflects the final admitted desktop boundary after Package C and the post-M05 independent-audit correction pass.

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

The packaged sidecar uses a PyInstaller on-directory runtime so Rust owns the actual backend process. Dynamic loopback allocation, authenticated health polling, exact resource resolution, installed restart, and child cleanup are proven.

## Tauri Capability Boundary

The capability file assigns only:

```text
core:default
dialog:allow-open
```

to the bundled `main` window. `dialog:allow-open` supports explicit human file selection; Rust copies the selected file into the governed evidence inbox. It grants no shell, broad filesystem, updater, global-shortcut, remote-origin, or arbitrary-window capability.

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
uv run pytest tests/test_m05_packaging_contract.py       passed
uv run pytest -o addopts= --disable-warnings -q          88 passed
npm --prefix desktop run build                           passed
npm --prefix desktop run tauri -- info                   Rust/Cargo/MSVC/WebView2 verified
npm --prefix desktop run tauri -- build --bundles nsis   passed
cargo test via the admitted Tauri toolchain               3 passed
npm package-lock-only resolution                         0 reported vulnerabilities
```

The lifecycle proof now includes a real Python subprocess that starts the desktop backend with environment-only configuration, binds to a disposable loopback port, migrates a disposable database through Alembic `0004`, authenticates an API v1 health request, and terminates cleanly. The Rust source reserves a dynamic loopback port, supplies application-data and packaged-resource paths through environment variables, polls the authenticated health endpoint, rejects early child exit or timeout, and stops the child on desktop exit.

The native toolchain is now directly proven through Tauri CLI execution. A Windows release executable compiled successfully with Rust 1.94.1, Cargo 1.94.1, MSVC Build Tools 2026, and the installed WebView2 runtime. Three Rust unit tests pass for launch-token quality, loopback URL construction, and dynamic loopback port reservation.

## Final Native Validation Boundary

The NSIS current-user installer, installed first launch, restart, packaged Python sidecar, migration resources, database preservation on uninstall, and clean backend shutdown were proven during M05 closure. The installer remains unsigned and is not represented as a production distribution release.

## Stop Conditions Still Active

Stop and return for owner ruling if native implementation requires:

- direct database access from Rust or React;
- broad shell or filesystem capability;
- remote API origins;
- updater activation;
- a public distribution endpoint;
- a second persistence authority;
- a material change outside the accepted M05 path list.
