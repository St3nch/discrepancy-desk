# Desktop Build Tooling Authority

## JavaScript dependencies

`desktop/package-lock.json` is the admitted JavaScript dependency lock. Canonical commands use npm:

```text
npm --prefix desktop ci
npm --prefix desktop run build
npm --prefix desktop run tauri -- info
npm --prefix desktop run tauri -- build --bundles nsis
```

`pnpm-lock.yaml` is not an admitted authority and must not be committed.

## Rust dependencies

`desktop/src-tauri/Cargo.lock` is committed because the Tauri project produces an application binary and installer. It is a reproducibility authority, not disposable build output.

Generated directories and packaged binaries remain ignored:

```text
desktop/node_modules/
desktop/dist/
desktop/src-tauri/binaries/
desktop/src-tauri/gen/
desktop/src-tauri/target/
```
