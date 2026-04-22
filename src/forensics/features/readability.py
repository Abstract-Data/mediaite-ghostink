"""Readability scores (Phase 4)."""

from __future__ import annotations

import logging

import textstat

logger = logging.getLogger(__name__)

_NAN_READABILITY: dict[str, float] = {
    "flesch_kincaid": float("nan"),
    "coleman_liau": float("nan"),
    "gunning_fog": float("nan"),
    "smog": float("nan"),
}


def extract_readability_features(text: str) -> dict[str, float]:
    """Flesch–Kincaid grade, Coleman–Liau, Gunning Fog, SMOG (textstat)."""
    if not text or not text.strip():
        return dict(_NAN_READABILITY)
    try:
        return {
            "flesch_kincaid": float(textstat.flesch_kincaid_grade(text)),
            "coleman_liau": float(textstat.coleman_liau_index(text)),
            "gunning_fog": float(textstat.gunning_fog(text)),
            "smog": float(textstat.smog_index(text)),
        }
    except (ValueError, ZeroDivisionError, AttributeError) as exc:
        logger.warning("readability: textstat failed (%s); returning NaN scores", exc)
        return dict(_NAN_READABILITY)
