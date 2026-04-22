"""Phase 8: reporting utilities, Quarto metadata, and notebook import hygiene."""

from __future__ import annotations

import ast
import importlib
import json
import re
import sqlite3
from datetime import date
from pathlib import Path

import plotly.graph_objects as go
import pytest

from forensics.config import get_project_root
from forensics.config.settings import AuthorConfig, ForensicsSettings, ReportConfig, ScrapingConfig
from forensics.reporting import (
    _analysis_artifacts_ok,
    _quarto_bin,
    resolve_notebook_path,
)
from forensics.utils import charts as charts_mod
from forensics.utils.charts import apply_baseline_shading, apply_change_point_annotations
from forensics.utils.provenance import (
    compute_config_hash,
    compute_corpus_hash,
    load_corpus_custody,
    verify_corpus_hash,
    write_corpus_custody,
)


def _minimal_forensics_settings(**kwargs) -> ForensicsSettings:
    authors = [
        AuthorConfig(
            name="A",
            slug="a",
            outlet="mediaite.com",
            role="target",
            archive_url="https://example.com/a/",
            baseline_start=date(2020, 1, 1),
            baseline_end=date(2021, 1, 1),
        )
    ]
    return ForensicsSettings(authors=authors, **kwargs)


def test_chart_theme_loads() -> None:
    charts_mod.register_forensics_template(set_default=True)
    import plotly.io as pio

    assert "forensics" in pio.templates
    assert pio.templates.default == "forensics"


def test_change_point_annotations() -> None:
    charts_mod.register_forensics_template(set_default=True)
    fig = go.Figure()
    fig.add_scatter(x=["2020-01-01", "2021-01-01"], y=[1, 2])
    before = len(fig.layout.shapes) if fig.layout.shapes else 0
    apply_change_point_annotations(
        fig,
        [{"timestamp": "2020-06-01", "feature_name": "ttr"}],
    )
    after_shapes = fig.layout.shapes
    assert after_shapes is not None
    assert len(after_shapes) >= before


def test_baseline_shading() -> None:
    charts_mod.register_forensics_template(set_default=True)
    fig = go.Figure()
    fig.add_scatter(x=["2019-01-01", "2021-01-01"], y=[1, 2])
    apply_baseline_shading(fig, "2019-06-01", "2020-01-01")
    assert fig.layout.shapes


def test_notebook_imports() -> None:
    root = get_project_root()
    nb_dir = root / "notebooks"
    mods: set[str] = set()
    for path in sorted(nb_dir.glob("*.ipynb")):
        nb = json.loads(path.read_text(encoding="utf-8"))
        for cell in nb.get("cells", []):
            if cell.get("cell_type") != "code":
                continue
            src = "".join(cell.get("source") or [])
            try:
                ast.parse(src)
            except SyntaxError as exc:
                pytest.fail(f"Syntax error in {path.name}: {exc}\n{src}")
            for m in re.finditer(r"^from (forensics(?:\.\w+)+) import", src, re.MULTILINE):
                mods.add(m.group(1))
            if re.search(r"^import forensics\b", src, re.MULTILINE):
                mods.add("forensics")
    for mod in sorted(mods):
        importlib.import_module(mod)


def test_report_config_validation() -> None:
    r = ReportConfig(title="T", output_format="html", include_sections=["executive"])
    assert r.chart_theme in ("plotly_white", "forensics")
    with pytest.raises(ValueError):
        ReportConfig(title="T", include_sections=["not-a-real-section"])


def test_quarto_config_exists() -> None:
    text = (get_project_root() / "quarto.yml").read_text(encoding="utf-8")
    assert "project:" in text
    assert "book:" in text
    assert text.count(".ipynb") == 10


def test_provenance_hash_deterministic(tmp_path: Path) -> None:
    db = tmp_path / "t.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE articles (id INTEGER PRIMARY KEY, content_hash TEXT NOT NULL)",
    )
    conn.execute("INSERT INTO articles(content_hash) VALUES ('a'), ('b')")
    conn.commit()
    conn.close()
    s = _minimal_forensics_settings()
    h1 = compute_corpus_hash(db)
    h2 = compute_corpus_hash(db)
    assert h1 == h2
    assert compute_config_hash(s) == compute_config_hash(s)


def test_provenance_hash_changes(tmp_path: Path) -> None:
    db = tmp_path / "t.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE articles (id INTEGER PRIMARY KEY, content_hash TEXT NOT NULL)",
    )
    conn.execute("INSERT INTO articles(content_hash) VALUES ('x')")
    conn.commit()
    conn.close()
    h1 = compute_corpus_hash(db)
    conn = sqlite3.connect(db)
    conn.execute("INSERT INTO articles(content_hash) VALUES ('y')")
    conn.commit()
    conn.close()
    assert compute_corpus_hash(db) != h1

    s1 = _minimal_forensics_settings()
    s2 = _minimal_forensics_settings(scraping=ScrapingConfig(rate_limit_seconds=9.0))
    assert compute_config_hash(s1) != compute_config_hash(s2)


def test_corpus_custody_verify(tmp_path: Path) -> None:
    db = tmp_path / "c.db"
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE articles (id INTEGER PRIMARY KEY, content_hash TEXT NOT NULL)",
    )
    conn.execute("INSERT INTO articles(content_hash) VALUES ('z')")
    conn.commit()
    conn.close()
    adir = tmp_path / "analysis"
    write_corpus_custody(db, adir)
    assert load_corpus_custody(adir) is not None
    ok, msg = verify_corpus_hash(db, adir)
    assert ok and "matches" in msg


def test_index_qmd_exists() -> None:
    text = (get_project_root() / "index.qmd").read_text(encoding="utf-8")
    assert "Mediaite" in text
    assert "Pre-Registration" in text


def test_resolve_notebook_path() -> None:
    root = get_project_root()
    p = resolve_notebook_path(root, "05")
    assert p is not None
    assert p.name.startswith("05_")


def test_resolve_notebook_path_digit_sorted_first(tmp_path: Path) -> None:
    nb = tmp_path / "notebooks"
    nb.mkdir(parents=True)
    (nb / "01_alpha.ipynb").write_text("{}", encoding="utf-8")
    (nb / "01_beta.ipynb").write_text("{}", encoding="utf-8")
    p = resolve_notebook_path(tmp_path, "1")
    assert p is not None
    assert p.name == "01_alpha.ipynb"


def test_resolve_notebook_path_by_filename_under_notebooks(tmp_path: Path) -> None:
    nb = tmp_path / "notebooks"
    nb.mkdir(parents=True)
    target = nb / "chapter.ipynb"
    target.write_text("{}", encoding="utf-8")
    assert resolve_notebook_path(tmp_path, "chapter.ipynb") == target


def test_resolve_notebook_path_strips_whitespace(tmp_path: Path) -> None:
    nb = tmp_path / "notebooks"
    nb.mkdir(parents=True)
    (nb / "02_x.ipynb").write_text("{}", encoding="utf-8")
    p = resolve_notebook_path(tmp_path, "  2  ")
    assert p is not None
    assert p.name == "02_x.ipynb"


def test_resolve_notebook_path_fallback_repo_root(tmp_path: Path) -> None:
    (tmp_path / "notebooks").mkdir(parents=True)
    loose = tmp_path / "only_at_root.ipynb"
    loose.write_text("{}", encoding="utf-8")
    assert resolve_notebook_path(tmp_path, "only_at_root.ipynb") == loose


def test_resolve_notebook_path_not_found(tmp_path: Path) -> None:
    (tmp_path / "notebooks").mkdir(parents=True)
    assert resolve_notebook_path(tmp_path, "99") is None
    assert resolve_notebook_path(tmp_path, "missing.ipynb") is None


def test_analysis_artifacts_ok_complete(tmp_path: Path) -> None:
    analysis = tmp_path / "analysis"
    analysis.mkdir()
    (analysis / "a_result.json").write_text("{}", encoding="utf-8")
    ok, msg = _analysis_artifacts_ok(_minimal_forensics_settings(), analysis)
    assert ok is True
    assert msg == ""


def test_analysis_artifacts_ok_missing(tmp_path: Path) -> None:
    analysis = tmp_path / "analysis"
    analysis.mkdir()
    ok, msg = _analysis_artifacts_ok(_minimal_forensics_settings(), analysis)
    assert ok is False
    assert "Missing analysis artifacts" in msg
    assert "a_result.json" in msg


def test_analysis_artifacts_ok_multiple_authors(tmp_path: Path) -> None:
    authors = [
        AuthorConfig(
            name="A",
            slug="a",
            outlet="mediaite.com",
            role="target",
            archive_url="https://example.com/a/",
            baseline_start=date(2020, 1, 1),
            baseline_end=date(2021, 1, 1),
        ),
        AuthorConfig(
            name="B",
            slug="b",
            outlet="mediaite.com",
            role="control",
            archive_url="https://example.com/b/",
            baseline_start=date(2020, 1, 1),
            baseline_end=date(2021, 1, 1),
        ),
    ]
    settings = ForensicsSettings(authors=authors)
    analysis = tmp_path / "analysis"
    analysis.mkdir()
    (analysis / "a_result.json").write_text("{}", encoding="utf-8")
    ok, msg = _analysis_artifacts_ok(settings, analysis)
    assert ok is False
    assert "b_result.json" in msg


def test_quarto_bin_delegates_to_which(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "forensics.reporting.shutil.which",
        lambda cmd: "/fake/quarto" if cmd == "quarto" else None,
    )
    assert _quarto_bin() == "/fake/quarto"


def test_settings_proxy_db_path() -> None:
    from forensics.config import settings as settings_proxy

    with pytest.warns(DeprecationWarning, match="get_settings"):
        p = settings_proxy.db_path
    assert p.name == "articles.db"
