from app.browser.search import build_search_url, expand_searches
from app.config import SearchConfig


def _params(**overrides):
    data = {"queries": ["AI Engineer"], "locations": ["India"]}
    data.update(overrides)
    return expand_searches(SearchConfig(**data))[0]


def test_basic_url_encoding():
    url = build_search_url(_params())
    assert "keywords=AI+Engineer" in url
    assert "location=India" in url


def test_recency_and_workplace_filters():
    url = build_search_url(_params(posted_within_days=1, workplace=["remote"]))
    assert "f_WT=2" in url
    assert "f_TPR=r86400" in url


def test_experience_filter():
    url = build_search_url(_params(experience_levels=["entry"]))
    assert "f_E=2" in url


def test_multiple_workplace_and_experience_codes():
    url = build_search_url(
        _params(workplace=["remote", "hybrid"], experience_levels=["entry", "associate"])
    )
    assert "f_WT=2,3" in url
    assert "f_E=2,3" in url


def test_pagination_start():
    url = build_search_url(_params(), page_index=2)
    assert "start=50" in url


def test_no_location_omits_param():
    url = build_search_url(_params(locations=[""]))
    assert "location=" not in url


def test_one_url_per_query_location():
    search = SearchConfig(queries=["AI Engineer", "SDE"], locations=["India", "Remote"])
    params = expand_searches(search)
    assert len(params) == 4
    assert {(p.query, p.location) for p in params} == {
        ("AI Engineer", "India"),
        ("AI Engineer", "Remote"),
        ("SDE", "India"),
        ("SDE", "Remote"),
    }
