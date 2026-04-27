# `forensics` CLI exit codes

The `forensics` Typer CLI uses a small, stable set of process exit codes so scripts and automation (including AI agents) can branch without parsing stderr.

| Code | Name | Meaning |
|------|------|--------|
| `0` | `OK` | Success |
| `1` | `GENERAL_ERROR` | Unclassified failure |
| `2` | `USAGE_ERROR` | Missing/invalid flag, mutually exclusive flags, malformed argument value |
| `3` | `AUTH_OR_RESOURCE` | Missing prerequisite resource (database file, model file, unreachable dependency, write-protected directory) |
| `4` | `TRANSIENT` | Network timeout, rate limit, retryable I/O — safe for an agent to retry after backoff |
| `5` | `CONFLICT` | Already exists / already done (e.g. lock present, schema already current, corpus hash drift vs custody) |

## Guidance for callers

- **Retry on `4` only** — use exponential backoff; do not spin in a tight loop.
- **Treat `5` as idempotent / settled** — the system is already in (or refuses to leave) a state that matches a “no further action” outcome; do not retry the same command expecting a different `5` without changing inputs or environment.
- **Do not blindly retry `1`, `2`, or `3`** — these usually require fixing configuration, restoring files, or human intervention. Inspect logs (stderr) or structured JSON (`--output json`) when available.

The root `forensics --help` epilog points here for quick reference.
