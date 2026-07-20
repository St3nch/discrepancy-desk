# Backup Encryption Prerequisites

Encrypted archive generation uses the external `age` command-line program.

Required executables for encryption validation:

```text
age
age-keygen
```

They must be available on `PATH`, or the caller must supply an explicit executable path. Missing tooling fails with a clear prerequisite error and removes any partial encrypted output.

The M05 packaged desktop does not bundle `age`. Packaged backup, restore, key management, and operator installation guidance remain M15 work. Tests that require real encryption skip honestly when `age`/`age-keygen` are unavailable; the closure profile for encrypted backup must require them explicitly.
