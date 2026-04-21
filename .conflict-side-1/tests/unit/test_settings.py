"""Configuration loading."""


def test_get_settings_from_fixture(settings) -> None:
    assert len(settings.authors) == 1
    assert settings.authors[0].slug == "fixture-author"
    assert settings.scraping.max_retries == 3
