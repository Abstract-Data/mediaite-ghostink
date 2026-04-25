# AI Marker Frequency Calibration

Version: 0.1.0
Status: active
Last Updated: 2026-04-24
Model: gpt-5-3-codex

## Purpose

Define the frozen v0.1.0 AI-marker phrase list used by
`ai_marker_frequency` calibration. This artifact records the list as a
methodology contract; extractor code is the executable source used by tests.

## Marker Specs

- `it's important to note`
- `it's worth noting`
- `delve`
- `in today's * landscape`
- `navigate`
- `underscores`
- `arguably`
- `at its core`
- `a testament to`
- `in an era of`
- `serves as a`
- `plays a crucial role`
- `it should be noted`
- `represents a significant`
- `offers a unique`
- `is a game-changer`

## Calibration Rule

Run a labeled calibration set with pre-Nov-2022 human articles as negatives
and synthetic AI baseline articles as positives. Keep this marker list only
when AI-marker frequency separates positives from negatives by the configured
minimum separation in deterministic scorer tests; otherwise release a new
immutable prompt version and update `AI_MARKER_LIST_VERSION`.
