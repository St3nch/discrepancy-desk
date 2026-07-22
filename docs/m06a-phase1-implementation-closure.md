# M06-A Phase 1 Implementation and Evidence Closure

## Status

M06-A Phase 1 implementation is complete and clean-commit evidence is bound to:

```text
8fe3be4cc9da3183da88cee4bf4b19e2979b901d
```

This record closes the implementation-and-proof package authorized by D030. It does not authorize M06-A Phase 2, parser admission, M06-B, network retrieval, providers, monitoring, live LLM work, Qdrant, graph work, destructive purge, or automated publishing.

The planned independent Claude implementation audit was deferred by the owner after Claude MCP/client failures and subscription usage limits prevented completion. The audit remains required before any Phase 2 authorization. No independent-review result is claimed here.

## Implemented Boundary

The commit adds the bounded Phase 1 foundation:

- central brand-level Vault accounts, registry records, and platform-owned-account bindings;
- one physically separate SQLite database per registered Vault;
- exact marker, database, and registry identity reconciliation;
- Windows path, reserved-name, case-collision, symlink, junction, and reparse-point rejection;
- trusted actor context and rejection of request-supplied human identity;
- per-Vault append-only audit chain and operation-key contract;
- cross-database receipts and explicit reconciliation-required outcomes without an atomicity claim;
- exact central and Vault Alembic environments, manifests, dirty-state handling, and recovery checks;
- opaque Vault routing and selected-Vault health;
- Tauri Vault list/create/select workflow through the token-gated loopback desktop API;
- no new Jinja Vault product surface or browser/Tauri parity requirement;
- stable desktop refusal messages that do not expose raw Vault filesystem paths;
- executable M06-A Phase 1 hammer mappings and evidence separation.

## Exact-Commit Validation

```text
uv run ruff check .                                      passed
uv run pytest -o addopts= --disable-warnings -q          139 passed
uv run python scripts/run_ht_evidence.py --suite m06a-phase1
                                                          31 executed, 31 passed, 0 failed
uv run python scripts/run_ht_evidence.py --suite legacy   31 executed, 31 passed, 0 failed
HT-14                                                     1 inherited approved deferral
pnpm --dir desktop test                                  2 passed
pnpm --dir desktop build                                 passed
pnpm --dir desktop exec cargo test --manifest-path src-tauri/Cargo.toml
                                                          3 passed
uv run python scripts/build_desktop_sidecar.py            passed
packaged loopback smoke                                  passed
central migration head                                   0005
Vault migration head                                     V0001
Vault audit chain                                        valid
obsolete /vaults route                                   absent / 404
duplicate-root path leakage                              absent
```

The working tree was clean when the full-suite and hammer evidence was generated. All evidence records below identify the implementation commit and report `working_tree_dirty: false`.

## Evidence Binding

Full-suite evidence:

```text
runtime/test-evidence/full-suite.json
SHA-256: 81b91a84e4acae96e31bb1e1236338f4d32cf9c034a4507a5241d01afc716b2b
Passed: 139
Failed: 0
Errors: 0
Skipped/XFail/XPass: 0
```

M06-A Phase 1 hammer evidence:

```text
runtime/ht-evidence/m06a-phase1/latest-ht-evidence.json
SHA-256: 34896d63cdaafc2b71f9742354c43c844ed0bf58a2bf86d0e533a00839643647
Required: 31
Executed: 31
Passed: 31
Failed: 0
Deferred: 0
```

Legacy hammer evidence:

```text
runtime/ht-evidence/legacy/latest-ht-evidence.json
SHA-256: 6bb8dde95ea9c0c542e600ee6b31e60644709810e63c3267caa8d628f2da25b8
Required: 32
Executed: 31
Passed: 31
Failed: 0
Deferred by approved scope: 1
```

Packaged sidecar evidence:

```text
runtime/desktop-sidecar-build/sidecar-build-evidence.json
Evidence-file SHA-256: 8454400f8ae71d9f41280aab82b3171fddab8a15e7db80894fbc72b06c9133f7
Packaged artifact SHA-256: 3c589baee8a2bebc534c167fa334371386c59dfbab6fe4b76a62e253c01021b1
```

## Gate Result

M06-A Phase 1 implementation and clean-commit technical proof are complete.

The independent Claude audit is deferred, not waived permanently. Phase 2 remains blocked until:

1. Claude independently reviews the committed Phase 1 implementation when usage and MCP access permit;
2. any resulting findings are corrected and evidence-bound;
3. the owner explicitly authorizes the next bounded phase.
