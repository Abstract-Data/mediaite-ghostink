#!/bin/bash
# Extract+analyze for the 12 high-volume departed-staff authors filtered out
# by the recent-activity gate. Sequential per-author to avoid the multi-author
# extract hang. Idempotent: re-runs skip already-extracted authors.

set -u
LOG=${LOG:-/Users/johneakin/PyCharmProjects/mediaite-ghostink/data/logs/cohort_12_run.log}
PROJECT=/Users/johneakin/PyCharmProjects/mediaite-ghostink

declare -a NEEDS_EXTRACT=(
  ken-meyer
  kipp-jones
  jackson-richman
  josh-feldman
  phillip-nieto
  candice-ortiz
  caleb-howe
  jamie-frevele
  brandoncontes
  rudy-takala
  tom-durante
)

declare -a ALL_SLUGS=("${NEEDS_EXTRACT[@]}" leia-idliby)

echo "=== START $(date -u +%FT%TZ) ===" > "$LOG"

for slug in "${NEEDS_EXTRACT[@]}"; do
  parq="$PROJECT/data/features/${slug}.parquet"
  if [ -f "$parq" ]; then
    echo "=== EXTRACT SKIP (parquet exists): $slug $(date -u +%FT%TZ) ===" >> "$LOG"
    continue
  fi
  echo "=== EXTRACT (skip-embeddings): $slug $(date -u +%FT%TZ) ===" >> "$LOG"
  # --skip-embeddings sidesteps a long-running MPS embedding hang on this
  # machine. Pipeline B (semantic drift) will be zero for these authors;
  # Pipeline A and the AI-marker-effect-size escape hatch still detect
  # strong stylometric AI signals without needing embeddings.
  if ! uv run forensics --no-progress extract --author "$slug" --skip-embeddings >> "$LOG" 2>&1; then
    echo "EXTRACT FAILED: $slug" >> "$LOG"
  fi
done

for slug in "${ALL_SLUGS[@]}"; do
  result="$PROJECT/data/analysis/${slug}_result.json"
  if [ -f "$result" ]; then
    echo "=== ANALYZE SKIP (result exists): $slug $(date -u +%FT%TZ) ===" >> "$LOG"
    continue
  fi
  echo "=== ANALYZE: $slug $(date -u +%FT%TZ) ===" >> "$LOG"
  if ! uv run forensics --no-progress analyze --author "$slug" --exploratory --allow-pre-phase16-embeddings >> "$LOG" 2>&1; then
    echo "ANALYZE FAILED: $slug" >> "$LOG"
  fi
done

echo "=== ALL STAGES COMPLETE $(date -u +%FT%TZ) ===" >> "$LOG"
