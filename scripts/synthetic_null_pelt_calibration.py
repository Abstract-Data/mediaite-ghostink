"""Synthetic Gaussian null calibration for PELT break counts (M-23).

Run from the repository root::

    uv run python scripts/synthetic_null_pelt_calibration.py

Writes ``data/provenance/synthetic_null_pelt_calibration.json`` with mean /
std of detected break counts on pure noise, using the same PELT+L2+min_size
pattern as production (``ruptures.Pelt``).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import ruptures as rpt


def _count_breaks(y: np.ndarray, *, pen: float, cost_model: str = "l2") -> int:
    y = np.asarray(y, dtype=float).ravel()
    if len(y) < 10:
        return 0
    std = float(np.std(y))
    scaled_pen = pen * std if std > 1e-12 else pen
    algo = rpt.Pelt(model=cost_model, min_size=5).fit(y.reshape(-1, 1))
    b = algo.predict(pen=scaled_pen)
    return max(0, len(b) - 1)


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    out_path = root / "data" / "provenance" / "synthetic_null_pelt_calibration.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(42)
    n_samples = 500
    n_trials = 200
    pen = 5.0
    counts = [
        _count_breaks(rng.standard_normal(n_samples), pen=pen, cost_model="l2")
        for _ in range(n_trials)
    ]
    arr = np.asarray(counts, dtype=float)
    payload = {
        "recorded_at": datetime.now(UTC).isoformat(),
        "n_samples": n_samples,
        "n_trials": n_trials,
        "pelt_penalty_config": pen,
        "cost_model": "l2",
        "min_size": 5,
        "break_count_mean": float(arr.mean()),
        "break_count_std": float(arr.std(ddof=1)) if n_trials > 1 else 0.0,
        "break_count_p95": float(np.percentile(arr, 95)),
        "break_counts": [int(x) for x in counts],
    }
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
