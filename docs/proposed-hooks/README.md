# Proposed Hooks

These hook scripts were generated from cross-run pattern analysis (5 review runs, Apr 20-22, 2026). They address recurring review findings that language instructions alone cannot prevent.

## Installation

1. Copy each `.sh` file to `.claude/hooks/`
2. Make executable: `chmod +x .claude/hooks/*.sh`
3. Add the registration entries to `.claude/hooks.json` under `PostToolUse`

## Registration entries for `.claude/hooks.json`

```json
{
  "name": "Function Length Guard",
  "command": "bash .claude/hooks/function-length-guard.sh",
  "severity": "warning"
},
{
  "name": "Hand-Built Data Path",
  "command": "bash .claude/hooks/handbuilt-path-check.sh",
  "severity": "warning"
}
```

## What they catch

| Hook | Recurring Pattern | Runs Flagged |
|------|------------------|--------------|
| Function Length Guard | God functions >50 lines (extract_all_features, _fetch_one_article_html) | 5/5 runs |
| Hand-Built Data Path | Manual `project_root / "data" / "features"` instead of AnalysisArtifactPaths | 3/5 runs |
