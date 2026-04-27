"""I-01 — scraping subset participates in its own deterministic hash."""

from __future__ import annotations

from forensics.config.settings import ScrapingConfig
from forensics.utils.provenance import _collect_hash_enumerated_fields, compute_model_config_hash


def test_scraping_hash_fields_enumerated() -> None:
    fields = _collect_hash_enumerated_fields(ScrapingConfig())
    assert fields is not None
    assert fields == {
        "bulk_fetch_mode",
        "simhash_threshold",
        "post_year_min",
        "post_year_max",
    }


def test_flipping_simhash_threshold_changes_hash() -> None:
    base = ScrapingConfig()
    h0 = compute_model_config_hash(base)
    h1 = compute_model_config_hash(base.model_copy(update={"simhash_threshold": 0}))
    assert h0 != h1
