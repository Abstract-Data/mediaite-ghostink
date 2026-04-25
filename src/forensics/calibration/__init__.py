"""Calibration suite — validate detection accuracy against synthetic ground truth.

Phase 12 §4. Provides:

- :mod:`forensics.calibration.synthetic` — build spliced / negative-control
  corpora from a real author's archive.
- :mod:`forensics.calibration.runner` — execute calibration trials and
  compute sensitivity / specificity / precision / F1 / date accuracy.

The CLI entry point lives in :mod:`forensics.cli.calibrate`.
"""

from forensics.calibration.markers import (
    MarkerCalibrationScore,
    score_marker_discrimination,
)
from forensics.calibration.runner import (
    CalibrationReport,
    CalibrationTrial,
    run_calibration,
)
from forensics.calibration.synthetic import (
    SyntheticCorpus,
    build_negative_control,
    build_spliced_corpus,
)

__all__ = [
    "CalibrationReport",
    "CalibrationTrial",
    "MarkerCalibrationScore",
    "SyntheticCorpus",
    "build_negative_control",
    "build_spliced_corpus",
    "run_calibration",
    "score_marker_discrimination",
]
