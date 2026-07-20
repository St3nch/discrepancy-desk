# AC-01 Post-M05 Independent-Audit Correction Closure

## Status

AC-01 is technically complete. The corrections below are bound to implementation commit:

```text
17f40e3d18a58ac47b48933551a4044586d940aa
```

## Corrections Applied

- reconciled `LEGAL_TRANSITIONS` with the accepted lifecycle doctrine;
- removed the inert `publication_mismatch → published` transition entry;
- added exact lifecycle-contract regression tests;
- separated full-suite, focused-session, and per-invariant hammer evidence paths;
- documented the external `age`/`age-keygen` prerequisite and M15 packaged-backup boundary;
- added clear missing-`age` failure behavior;
- changed generated-output hygiene tests to inspect Git-tracked paths rather than developer build directories;
- promoted `desktop/src-tauri/Cargo.lock` to committed application-build authority;
- standardized canonical JavaScript build documentation on `desktop/package-lock.json` and npm;
- updated the final Tauri capability contract to include bounded `dialog:allow-open`;
- expanded executable hammer coverage with AC01-G01 and AC01-G02.

## Exact-Commit Validation

```text
uv run ruff check .                                      passed
uv run pytest -o addopts= --disable-warnings -q          104 passed
frontend production build                               passed
Rust tests                                               3 passed
packaged sidecar build                                   passed
uv run python scripts/run_ht_evidence.py                 31 executed, 31 passed, 0 failed
HT-14                                                    1 inherited scope deferral
```

The repository service did not expose `npm` on its process PATH. Native validation used the available pnpm execution shim over the same committed `package-lock.json` dependency set. Canonical project commands remain npm as documented in `docs/desktop-build-tooling.md`.

## Evidence Binding

Full-suite evidence:

```text
runtime/test-evidence/full-suite.json
Commit: 17f40e3d18a58ac47b48933551a4044586d940aa
SHA-256: 78fc6073c087eb35f404b57030137d8a2c9e51b28f8da4c903812f2a64b40796
Passed: 104
Failed: 0
```

Hammer evidence:

```text
runtime/ht-evidence/latest-ht-evidence.json
Commit: 17f40e3d18a58ac47b48933551a4044586d940aa
SHA-256: baaba75a25125e9dde53bbf8255e13d1c4a6e4df66c20985b3857bad1c898dbf
Executed: 31
Passed: 31
Failed: 0
Deferred by scope: 1
```

Hammer execution no longer overwrites the aggregate full-suite record. Each executed invariant also writes a separate file under `runtime/test-evidence/hammer/`.

## Remaining Local Residue

The obsolete rejected one-file sidecar may remain as an ignored local file if Windows still holds its handle. It is not tracked, referenced, bundled, or authoritative. The admitted sidecar remains the generated on-directory package.

## Gate Result

The accepted independent-audit findings are resolved. AC-01 may close and R-M06-01 may begin. M06 implementation, connectors, scheduled monitors, and Qdrant remain blocked by the M06 research and architecture gates.
