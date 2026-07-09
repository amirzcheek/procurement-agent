"""Тест MockProvider и site-фильтра — без сети."""
import search
from config import Settings


def _settings():
    return Settings(search_provider="mock", max_prices_per_item=3,
                    marketplaces=["satu.kz", "technodom.kz", "sulpak.kz"])


def test_mock_provider_deterministic():
    p = search.MockProvider(_settings())
    a = p.search("Бумага А4")
    b = p.search("Бумага А4")
    assert len(a) == 3
    assert [x.url for x in a] == [x.url for x in b]  # детерминизм
    assert all(x.source in {"satu.kz", "technodom.kz", "sulpak.kz"} for x in a)


def test_site_filter():
    f = search._site_filter(["satu.kz", "kaspi.kz"])
    assert f == "(site:satu.kz OR site:kaspi.kz)"


def test_domain_extraction():
    assert search._domain("https://www.technodom.kz/p/123") == "technodom.kz"
    assert search._domain("https://kaspi.kz/shop/p/x") == "kaspi.kz"
