"""Analysis package import smoke tests (stubs until Phase 5)."""


def test_analysis_submodules_importable() -> None:
    import forensics.analysis.changepoint  # noqa: F401
    import forensics.analysis.comparison  # noqa: F401
    import forensics.analysis.convergence  # noqa: F401
    import forensics.analysis.drift  # noqa: F401
    import forensics.analysis.statistics  # noqa: F401
    import forensics.analysis.timeseries  # noqa: F401
