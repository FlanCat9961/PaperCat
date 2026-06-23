from papercat.core.sources.yandere import YandereSource


def test_yandere_metadata() -> None:
    source = YandereSource()

    assert source.id == "yandere"
    assert source.display_name == "yande.re"
    assert source.BASE_URL == "https://yande.re"
    assert source.default_min_interval_sec == 1.2
