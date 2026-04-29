# Security policy

## Supported versions

Security-sensitive fixes are applied to the **default branch** (`main`). Releases follow normal repository tagging practices described in project documentation.

## Reporting a vulnerability

**Please do not** open a public GitHub issue for undisclosed security vulnerabilities.

1. Use **[GitHub private vulnerability reporting](https://github.com/Abstract-Data/mediaite-ghostink/security/advisories/new)** for this repository if it is enabled for your account.
2. If private reporting is unavailable, contact the maintainers through an established Abstract Data channel you already use for this engagement.

Include enough detail to reproduce the issue (affected component, configuration, and impact). We will acknowledge receipt as soon as practical and coordinate disclosure and fixes with you.

## Scope notes

This project is a **local data pipeline** (CLI, SQLite, Parquet, optional network scraping to configured hosts). Reports about denial-of-service against third-party sites, or risks inherent to running untrusted code in your own environment, may be handled as documentation or operational guidance rather than product CVEs.
