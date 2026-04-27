"""Package-level monkeypatch propagation for ``forensics.analysis.orchestrator``."""

from __future__ import annotations

from collections.abc import Callable

import pytest

import forensics.analysis.orchestrator as orch
from forensics.analysis.orchestrator import comparison as comp_mod
from forensics.analysis.orchestrator import parallel as par_mod
from forensics.analysis.orchestrator import per_author as pa_mod
from forensics.analysis.orchestrator import sensitivity as sens_mod
from forensics.analysis.orchestrator import staleness as stal_mod


@pytest.fixture(autouse=True)
def _resync_orchestrator_patches() -> object:
    yield
    orch._sync_patchable_globals()


def _sentinel(name: str):
    def _fn(*_a: object, **_k: object) -> str:
        return name

    return _fn


_PATCH_SETTERS: dict[str, tuple[str, object]] = {
    "uuid4": ("uuid4", lambda: "sentinel-uuid"),
    "datetime": ("datetime", _sentinel("sentinel-dt")),
    "_clean_feature_series": ("_clean_feature_series", _sentinel("sentinel-clean")),
    "_run_per_author_analysis": ("_run_per_author_analysis", _sentinel("sentinel-rpaa")),
    "_resolve_parallel_refresh_workers": (
        "_resolve_parallel_refresh_workers",
        _sentinel("sentinel-rprw"),
    ),
    "_isolated_author_worker": ("_isolated_author_worker", _sentinel("sentinel-iso")),
    "_validate_and_promote_isolated_outputs": (
        "_validate_and_promote_isolated_outputs",
        _sentinel("sentinel-val"),
    ),
}


def _check_uuid4() -> bool:
    return par_mod.uuid4() == "sentinel-uuid" and pa_mod.uuid4() == "sentinel-uuid"


def _check_datetime() -> bool:
    return (
        par_mod.datetime is orch.datetime
        and pa_mod.datetime is orch.datetime
        and stal_mod.datetime is orch.datetime
    )


def _check_clean() -> bool:
    return pa_mod._clean_feature_series() == "sentinel-clean"


def _check_rpaa() -> bool:
    return (
        par_mod._run_per_author_analysis() == "sentinel-rpaa"
        and sens_mod._run_per_author_analysis() == "sentinel-rpaa"
    )


def _check_rprw() -> bool:
    return par_mod._resolve_parallel_refresh_workers() == "sentinel-rprw"


def _check_iso() -> bool:
    return par_mod._isolated_author_worker() == "sentinel-iso"


def _check_val() -> bool:
    return par_mod._validate_and_promote_isolated_outputs() == "sentinel-val"


_PATCH_ASSERTS: dict[str, Callable[[], bool]] = {
    "uuid4": _check_uuid4,
    "datetime": _check_datetime,
    "_clean_feature_series": _check_clean,
    "_run_per_author_analysis": _check_rpaa,
    "_resolve_parallel_refresh_workers": _check_rprw,
    "_isolated_author_worker": _check_iso,
    "_validate_and_promote_isolated_outputs": _check_val,
}


@pytest.mark.parametrize("name", list(_PATCH_SETTERS))
def test_patch_target_propagates_to_submodules(name: str, monkeypatch: pytest.MonkeyPatch) -> None:
    attr, value = _PATCH_SETTERS[name]
    monkeypatch.setattr(orch, attr, value)
    orch._sync_patchable_globals()
    assert _PATCH_ASSERTS[name]()


def test_non_patch_surface_symbol_not_forwarded_from_package(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    orig = comp_mod._resolve_targets_and_controls
    monkeypatch.setattr(orch, "_resolve_targets_and_controls", lambda *a, **k: "nope")
    orch._sync_patchable_globals()
    assert comp_mod._resolve_targets_and_controls is orig
