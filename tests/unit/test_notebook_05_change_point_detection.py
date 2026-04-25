"""Smoke tests for ``notebooks/05_change_point_detection.ipynb``.

These tests do not re-execute the notebook (kernel + nbclient are not first-party
dev deps). Instead they verify the committed notebook is well-formed and that any
cached outputs do not include error tracebacks. They also exercise the small set
of registries that the notebook leans on so a refactor that broke the cell
sources would also break a fast unit test.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

NB_PATH = Path(__file__).resolve().parents[2] / "notebooks" / "05_change_point_detection.ipynb"


def _load_notebook() -> dict:
    return json.loads(NB_PATH.read_text(encoding="utf-8"))


def test_notebook_file_exists() -> None:
    assert NB_PATH.is_file(), f"notebook not found: {NB_PATH}"


def test_notebook_is_valid_nbformat() -> None:
    nb = _load_notebook()
    assert nb.get("nbformat") == 4
    assert isinstance(nb.get("cells"), list)
    assert len(nb["cells"]) >= 5, "notebook should have several cells, not just a stub"


def test_notebook_has_parameters_cell() -> None:
    nb = _load_notebook()
    param_cells = [
        c
        for c in nb["cells"]
        if c.get("cell_type") == "code"
        and "parameters" in (c.get("metadata", {}).get("tags") or [])
    ]
    assert len(param_cells) == 1, "exactly one Quarto parameters cell is required"
    src = "".join(param_cells[0]["source"])
    assert "author_slug" in src, "parameters cell must expose author_slug for Quarto"


def test_notebook_loads_all_authors_not_just_first() -> None:
    """Guard against regressing to the placeholder ``settings.authors[0]`` form."""
    nb = _load_notebook()
    body = "\n".join("".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code")
    assert "settings.authors[0]" not in body, (
        "notebook 05 must iterate every author; do not pin to settings.authors[0]"
    )
    assert "_result.json" in body, "notebook should consume *_result.json artifacts"


def test_notebook_executed_outputs_have_no_errors() -> None:
    nb = _load_notebook()
    errors: list[tuple[int, str, str]] = []
    for idx, cell in enumerate(nb["cells"]):
        if cell.get("cell_type") != "code":
            continue
        for out in cell.get("outputs", []):
            if out.get("output_type") == "error":
                errors.append((idx, out.get("ename", ""), out.get("evalue", "")))
    assert not errors, f"notebook contains error outputs: {errors}"


def test_feature_family_registry_covers_notebook_palette() -> None:
    """The notebook's family palette must list every family the registry knows."""
    from forensics.analysis.feature_families import FEATURE_FAMILIES

    nb = _load_notebook()
    body = "\n".join("".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "code")
    for family in set(FEATURE_FAMILIES.values()):
        assert family in body, (
            f"feature family {family!r} is not represented in the notebook palette; "
            "update FAMILY_PALETTE when adding/renaming families"
        )


@pytest.mark.parametrize(
    "needle",
    [
        "PELT",
        "BOCPD",
        "per-family BH",
        "Methodology",
    ],
)
def test_notebook_documents_methodology(needle: str) -> None:
    nb = _load_notebook()
    body = "\n".join("".join(c["source"]) for c in nb["cells"] if c["cell_type"] == "markdown")
    # Some needles use mixed case; do a case-insensitive contains.
    assert needle.lower() in body.lower(), f"notebook must document methodology keyword: {needle!r}"
