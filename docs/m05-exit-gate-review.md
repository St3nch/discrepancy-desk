# M05 Exit-Gate Review — Provisional Technical Record

## Status

M05 Packages A through C are technically implemented and validated. The executable evidence is bound to the exact accepted implementation commit below. M05 is technically complete and awaits explicit owner closure acceptance.

## Delivered Desktop Foundation

The Windows desktop application now provides:

- a Tauri 2 shell with deny-by-default capabilities;
- a Rust-owned backend supervisor;
- a packaged Python/FastAPI backend bound only to dynamic loopback;
- an ephemeral per-launch API token passed through environment variables;
- account-scoped Command Center, Calendar, Work, Records, Metrics, and System surfaces;
- explicit disabled placeholders for Release Watch and Library;
- governed desktop JSON operations for capture, organization, tags, scheduling, rescheduling, Reserve, drafting, exact approval, manual-ready, publication, sources, evidence, and metrics;
- native evidence-file selection copied by Rust into the governed evidence inbox;
- no direct SQLite access from React or Rust UI code;
- no updater, public endpoint, code-signing, Store, or autonomous platform-write authority.

## Packaged Sidecar Decision

The first PyInstaller one-file proof was rejected because its bootloader could leave a worker process alive after the Rust-owned process exited. Package C was corrected to use a PyInstaller on-directory runtime. Rust now owns the actual backend process directly.

The final packaged sidecar proof records:

```text
Artifact: desktop/src-tauri/binaries/discrepancy-desk-backend/discrepancy-desk-backend.exe
Executable size: 12,206,395 bytes
Package size: 40,115,495 bytes
Executable SHA-256: d127ff1e633b851e32932459f78afead428d4540f4a55b4a69513373ce0a354d
Build-evidence SHA-256: 6a8468679d4595b437a10d94ed70ef1ce06bc19281b0f89e21c436bd57c39c36
```

The packaged executable started on loopback, authenticated API v1, migrated a disposable database through `0004`, and terminated cleanly.

## Installed Lifecycle Proof

The NSIS current-user installer was built and installed into an isolated test directory. The installed application contained the desktop executable, on-directory backend runtime, Alembic configuration, and migrations `0001` through `0004`.

First launch and restart both proved:

- desktop exit code `0`;
- migration `0004`;
- no surviving `discrepancy-desk-backend.exe` process after desktop exit.

Runtime proof:

```text
Installer size: 21,258,493 bytes
Installed backend: backend/discrepancy-desk-backend.exe
Launch/restart proof SHA-256: ae374de3c1670e6cbbd2358dcd5fb247bfac990a20d0df84a41d825d9963215b
```

Silent uninstall proved:

- uninstaller exit code `0`;
- installed desktop executable removed;
- user database preserved after uninstall.

Uninstall-proof SHA-256:

```text
2fede7376a0f09200f9fc0a730192d9529737dac3090a3de03fc933318715cd4
```

Test-created app data and installation directories were removed after proof.

## Validation

Current pre-commit results:

```text
uv run ruff check .                                      passed
uv run pytest -o addopts= --disable-warnings -q          97 passed
pnpm --dir desktop build                                 passed
cargo test --manifest-path desktop/src-tauri/Cargo.toml  3 passed
pnpm --dir desktop tauri build --bundles nsis            passed
uv run python scripts/run_ht_evidence.py                 29 executed, 29 passed, 0 failed
Inherited HT-14 scope deferral                           1
npm package-lock audit                                   0 reported vulnerabilities
```

## Security and Distribution Findings

- Desktop API is disabled without an explicit launch token.
- Wrong or missing tokens fail before route execution.
- Backend binds only to `127.0.0.1` on a dynamic port.
- The token and governed paths are not command-line arguments.
- Tauri capabilities admit `core:default` and bounded dialog open only.
- Native evidence import limits files to 100 MiB and copies them into a governed inbox.
- No updater or remote webview origin is configured.
- Installer is Windows x64 NSIS with `currentUser` install mode.
- The produced development installer is unsigned and is not claimed as a production release.
- Generated binaries, package directories, Cargo output, and secondary lockfiles are excluded from source control.

## Final Evidence Binding

Implementation commit:

```text
31d7a7001e72e7477e6a38cb2e7c3ee9d099197c
```

Executable hammer evidence:

```text
runtime/ht-evidence/latest-ht-evidence.json
SHA-256: e3c59481d3fd7b8163828e5cc97f6f26ac359d086c481e41ec5cfb5bc2c6fc20
Executed: 29
Passed: 29
Failed: 0
Inherited scope deferral: 1
```

The evidence payload records the same exact implementation commit SHA.

## Remaining Milestone Gate

The only remaining action is explicit owner acceptance to close M05 and authorize M06 planning. No M06 work is authorized by this technical completion record alone.
