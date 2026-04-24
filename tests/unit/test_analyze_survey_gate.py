"""Phase 15 — analyze CLI survey-gate guard for shared-byline accounts.

The Phase 15 D survey gate disqualifies group accounts (``mediaite``,
``mediaite-staff``) because single-author stylometry on aggregate bylines is
meaningless. The analyze CLI mirrors that gate so an operator can't pass
``--author mediaite`` and silently get PA=1.00 from a many-author corpus
that the survey would have rejected.

Tests:

1. happy path — a real, single-author slug runs without raising.
2. edge case — a shared byline without ``--include-shared-bylines`` raises
   ``typer.BadParameter``.
3. edge case — a shared byline WITH ``--include-shared-bylines`` is allowed
   through; the orchestrator's ``run_full_analysis`` is invoked.
4. edge case — heuristic fallback fires when the persisted
   ``is_shared_byline`` flag is False but the slug matches the outlet prefix
   (older databases that pre-date Phase 15 D ingest stamping).
5. happy path — ``author=None`` (newsroom-wide invocation) bypasses the gate
   entirely, since the gate is a per-author guard.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import typer

from forensics.cli.analyze import run_analyze
from forensics.config import get_settings
from forensics.models import Author
from forensics.storage.repository import Repository

OUTLET = "mediaite.com"


# ---------------------------------------------------------------------------
# fixtures / helpers
# ---------------------------------------------------------------------------


def _make_author(slug: str, *, name: str | None = None, shared: bool = False) -> Author:
    return Author(
        id=f"author-{slug}",
        name=name or slug.title().replace("-", " "),
        slug=slug,
        outlet=OUTLET,
        role="target",
        baseline_start=date(2020, 1, 1),
        baseline_end=date(2023, 12, 31),
        archive_url=f"https://www.mediaite.com/author/{slug}/",
        is_shared_byline=shared,
    )


def _seed_authors(db_path: Path, authors: list[Author]) -> None:
    with Repository(db_path) as repo:
        for author in authors:
            repo.upsert_author(author)


def _config_with_authors(slugs: list[str], *, with_shared: bool = False) -> str:
    """Render a minimal config.toml that contains the given author slugs."""
    blocks: list[str] = []
    for slug in slugs:
        is_shared = with_shared and slug in {"mediaite", "mediaite-staff"}
        # Even shared bylines listed in config retain role=target — the gate
        # is what blocks them, not the role label.
        blocks.append(
            "[[authors]]\n"
            f'name = "{slug.title().replace("-", " ")}"\n'
            f'slug = "{slug}"\n'
            'outlet = "mediaite.com"\n'
            'role = "target"\n'
            f'archive_url = "https://www.mediaite.com/author/{slug}/"\n'
            "baseline_start = 2020-01-01\n"
            "baseline_end = 2023-12-31\n"
            + ("# is_shared_byline reflected in DB row, not config\n" if is_shared else "")
        )
    return "\n".join(blocks) + "\n[scraping]\n[analysis]\n[report]\n"


@pytest.fixture
def isolated_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Path]:
    """Build a tmp project root with config.toml + empty articles.db.

    Patches ``get_settings`` and ``get_project_root`` so ``run_analyze``
    reads from this isolated directory instead of the real repo. Also
    monkeypatches the Phase 15 J3 sub-app preregistration verifier to a
    no-op so we don't need a real preregistration manifest.
    """
    project_root = tmp_path / "project"
    project_root.mkdir()
    data_dir = project_root / "data"
    data_dir.mkdir()
    db_path = data_dir / "articles.db"
    # Touch the DB so Repository().__enter__ creates schema cleanly.
    from forensics.storage.repository import init_db

    init_db(db_path)

    config_path = project_root / "config.toml"
    config_path.write_text(
        _config_with_authors(["isaac-schorr", "mediaite-staff", "mediaite"]),
        encoding="utf-8",
    )

    monkeypatch.setenv("FORENSICS_CONFIG_FILE", str(config_path))
    get_settings.cache_clear()

    # Patch project root resolution everywhere run_analyze touches it.
    monkeypatch.setattr("forensics.cli.analyze.get_project_root", lambda: project_root)
    # Skip preregistration verification — it would look for an audit file.
    monkeypatch.setattr(
        "forensics.cli.analyze.verify_preregistration",
        lambda settings: type("PR", (), {"status": "absent"})(),
    )
    # Stub PipelineContext.record_audit so we don't write real audit rows.
    monkeypatch.setattr(
        "forensics.cli.analyze.PipelineContext.resolve",
        lambda: type(
            "PC",
            (),
            {"record_audit": lambda self, *a, **k: "test-rid", "config_hash": "deadbeef"},
        )(),
    )

    yield {"root": project_root, "db": db_path, "config": config_path}

    get_settings.cache_clear()


def _stub_stages(monkeypatch: pytest.MonkeyPatch) -> dict[str, MagicMock]:
    """Replace every analyze stage with a MagicMock so we can assert calls."""
    full = MagicMock(name="run_full_analysis")
    cp_stub = MagicMock(name="run_changepoint_analysis")
    ts_stub = MagicMock(name="run_timeseries_analysis")
    drift_stub = MagicMock(name="run_drift_analysis")
    monkeypatch.setattr("forensics.analysis.orchestrator.run_full_analysis", full)
    monkeypatch.setattr("forensics.analysis.changepoint.run_changepoint_analysis", cp_stub)
    monkeypatch.setattr("forensics.analysis.timeseries.run_timeseries_analysis", ts_stub)
    monkeypatch.setattr("forensics.analysis.drift.run_drift_analysis", drift_stub)
    return {
        "full": full,
        "changepoint": cp_stub,
        "timeseries": ts_stub,
        "drift": drift_stub,
    }


# ---------------------------------------------------------------------------
# happy path: real single-author slug
# ---------------------------------------------------------------------------


def test_analyze_runs_for_non_shared_author(
    isolated_project: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Analyzing a real reporter (``isaac-schorr``) does not trip the gate."""
    real_author = _make_author("isaac-schorr", name="Isaac Schorr")
    _seed_authors(isolated_project["db"], [real_author])

    stages = _stub_stages(monkeypatch)

    # Should not raise; convergence + timeseries are the implicit defaults.
    run_analyze(author="isaac-schorr")

    # Sanity check: the orchestrator was actually called for this author.
    stages["full"].assert_called_once()
    _, kwargs = stages["full"].call_args
    assert kwargs.get("author_slug") == "isaac-schorr"


# ---------------------------------------------------------------------------
# edge case: shared byline without flag → gate trips
# ---------------------------------------------------------------------------


def test_analyze_refuses_shared_byline_without_flag(
    isolated_project: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """``--author mediaite-staff`` without ``--include-shared-bylines`` errors out."""
    shared_author = _make_author("mediaite-staff", name="Mediaite Staff", shared=True)
    _seed_authors(isolated_project["db"], [shared_author])

    stages = _stub_stages(monkeypatch)

    with pytest.raises(typer.BadParameter) as excinfo:
        run_analyze(author="mediaite-staff")

    msg = str(excinfo.value)
    assert "shared byline" in msg.lower()
    assert "--include-shared-bylines" in msg
    # No analysis stage should have run when the gate fires.
    stages["full"].assert_not_called()


# ---------------------------------------------------------------------------
# edge case: shared byline WITH flag → gate is bypassed
# ---------------------------------------------------------------------------


def test_analyze_allows_shared_byline_with_flag(
    isolated_project: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Operator-opt-in via ``--include-shared-bylines`` bypasses the gate."""
    shared_author = _make_author("mediaite-staff", name="Mediaite Staff", shared=True)
    _seed_authors(isolated_project["db"], [shared_author])

    stages = _stub_stages(monkeypatch)

    # No exception; full analysis runs for the shared byline.
    run_analyze(author="mediaite-staff", include_shared_bylines=True)

    stages["full"].assert_called_once()
    _, kwargs = stages["full"].call_args
    assert kwargs.get("author_slug") == "mediaite-staff"


# ---------------------------------------------------------------------------
# edge case: heuristic fallback fires when DB flag is missing
# ---------------------------------------------------------------------------


def test_analyze_refuses_unflagged_shared_via_heuristic(
    isolated_project: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Older DBs may have ``is_shared_byline=0`` even on group accounts.

    The slug heuristic must still trip the gate — the outlet-prefix rule
    fires on ``mediaite-staff`` regardless of the persisted flag.
    """
    unflagged = _make_author("mediaite-staff", name="Mediaite Staff", shared=False)
    _seed_authors(isolated_project["db"], [unflagged])

    stages = _stub_stages(monkeypatch)

    with pytest.raises(typer.BadParameter):
        run_analyze(author="mediaite-staff")

    stages["full"].assert_not_called()


# ---------------------------------------------------------------------------
# happy path: author=None bypasses gate (newsroom-wide invocation)
# ---------------------------------------------------------------------------


def test_analyze_without_author_bypasses_gate(
    isolated_project: dict[str, Path], monkeypatch: pytest.MonkeyPatch
) -> None:
    """The gate only applies to ``--author <slug>`` invocations.

    ``forensics analyze`` (no --author) iterates every configured author and
    relies on the survey gate / configured roster to filter bylines.
    """
    real_author = _make_author("isaac-schorr", name="Isaac Schorr")
    _seed_authors(isolated_project["db"], [real_author])

    stages = _stub_stages(monkeypatch)

    # No ``author=`` kwarg — gate must not fire.
    run_analyze()

    # The orchestrator runs once with author_slug=None (newsroom-wide).
    stages["full"].assert_called_once()
    _, kwargs = stages["full"].call_args
    assert kwargs.get("author_slug") is None


# ---------------------------------------------------------------------------
# extra: explicit signature contract
# ---------------------------------------------------------------------------


def test_run_analyze_accepts_include_shared_bylines_kwarg() -> None:
    """``run_analyze`` exposes ``include_shared_bylines`` for the typer wrapper."""
    import inspect

    sig = inspect.signature(run_analyze)
    assert "include_shared_bylines" in sig.parameters
    param = sig.parameters["include_shared_bylines"]
    assert param.default is False
    # Keyword-only — matches the rest of the signature.
    assert param.kind == inspect.Parameter.KEYWORD_ONLY
