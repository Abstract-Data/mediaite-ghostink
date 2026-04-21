"""Feature extraction package import smoke tests (stubs until Phase 4)."""


def test_features_submodules_importable() -> None:
    import forensics.features.content  # noqa: F401
    import forensics.features.embeddings  # noqa: F401
    import forensics.features.lexical  # noqa: F401
    import forensics.features.pipeline  # noqa: F401
    import forensics.features.productivity  # noqa: F401
    import forensics.features.readability  # noqa: F401
    import forensics.features.structural  # noqa: F401
