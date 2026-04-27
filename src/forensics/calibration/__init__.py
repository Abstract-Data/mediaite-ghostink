"""Synthetic corpora and trial runner.

Submodules: :mod:`forensics.calibration.synthetic`, :mod:`forensics.calibration.runner`.
CLI: :mod:`forensics.cli.calibrate`.
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
