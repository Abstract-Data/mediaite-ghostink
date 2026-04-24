---
name: scripts
description: "Skill for the Scripts area of mediaite-ghostink. 21 symbols across 2 files."
---

# Scripts

21 symbols | 2 files | Cohesion: 36%

## When to Use

- Working with code in `scripts/`
- Understanding how code, nb02, nb06 work
- Modifying scripts-related functionality

## Key Files

| File | Symbols |
|------|---------|
| `scripts/generate_phase8_notebooks.py` | _lines, code, nb02, nb06, md (+11) |
| `scripts/bench_phase15.py` | PerAuthorStageTimings, PerAuthorBench, _get_git_sha, _bench_one_author, _main |

## Entry Points

Start here when exploring this area:

- **`code`** (Function) — `scripts/generate_phase8_notebooks.py:33`
- **`nb02`** (Function) — `scripts/generate_phase8_notebooks.py:239`
- **`nb06`** (Function) — `scripts/generate_phase8_notebooks.py:407`
- **`md`** (Function) — `scripts/generate_phase8_notebooks.py:29`
- **`nb04`** (Function) — `scripts/generate_phase8_notebooks.py:321`

## Key Symbols

| Symbol | Type | File | Line |
|--------|------|------|------|
| `PerAuthorStageTimings` | Class | `scripts/bench_phase15.py` | 36 |
| `PerAuthorBench` | Class | `scripts/bench_phase15.py` | 49 |
| `code` | Function | `scripts/generate_phase8_notebooks.py` | 33 |
| `nb02` | Function | `scripts/generate_phase8_notebooks.py` | 239 |
| `nb06` | Function | `scripts/generate_phase8_notebooks.py` | 407 |
| `md` | Function | `scripts/generate_phase8_notebooks.py` | 29 |
| `nb04` | Function | `scripts/generate_phase8_notebooks.py` | 321 |
| `nb08` | Function | `scripts/generate_phase8_notebooks.py` | 489 |
| `nb09` | Function | `scripts/generate_phase8_notebooks.py` | 522 |
| `write_nb` | Function | `scripts/generate_phase8_notebooks.py` | 75 |
| `nb01` | Function | `scripts/generate_phase8_notebooks.py` | 171 |
| `nb05` | Function | `scripts/generate_phase8_notebooks.py` | 363 |
| `nb00` | Function | `scripts/generate_phase8_notebooks.py` | 82 |
| `nb03` | Function | `scripts/generate_phase8_notebooks.py` | 282 |
| `nb07` | Function | `scripts/generate_phase8_notebooks.py` | 440 |
| `main` | Function | `scripts/generate_phase8_notebooks.py` | 557 |
| `_get_git_sha` | Function | `scripts/bench_phase15.py` | 65 |
| `_bench_one_author` | Function | `scripts/bench_phase15.py` | 81 |
| `_main` | Function | `scripts/bench_phase15.py` | 119 |
| `_lines` | Function | `scripts/generate_phase8_notebooks.py` | 23 |

## Execution Flows

| Flow | Type | Steps |
|------|------|-------|
| `_main → Config_fingerprint` | cross_community | 5 |
| `Main → _lines` | cross_community | 4 |
| `Main → _nb` | cross_community | 4 |
| `Nb04 → _lines` | cross_community | 3 |
| `Nb04 → _nb` | cross_community | 3 |
| `Nb05 → _lines` | cross_community | 3 |
| `Nb05 → _nb` | intra_community | 3 |
| `Nb06 → _lines` | cross_community | 3 |
| `Nb06 → _nb` | cross_community | 3 |
| `Nb07 → _lines` | cross_community | 3 |

## Connected Areas

| Area | Connections |
|------|-------------|
| Tests | 3 calls |
| Analysis | 1 calls |
| Forensics | 1 calls |

## How to Explore

1. `gitnexus_context({name: "code"})` — see callers and callees
2. `gitnexus_query({query: "scripts"})` — find related execution flows
3. Read key files listed above for implementation details
