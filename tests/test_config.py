import pytest
from pydantic import ValidationError

from app.config import SearchConfig, load_config


def test_invalid_workplace_names_field():
    with pytest.raises(ValidationError) as exc:
        SearchConfig(queries=["AI"], workplace=["onsitee"])
    assert "workplace" in str(exc.value)


def test_invalid_experience_level_names_field():
    with pytest.raises(ValidationError) as exc:
        SearchConfig(queries=["AI"], experience_levels=["senior"])
    assert "experience_levels" in str(exc.value)


def test_missing_queries_fails():
    with pytest.raises(ValidationError) as exc:
        SearchConfig()
    assert "queries" in str(exc.value)


def test_empty_queries_fails():
    with pytest.raises(ValidationError) as exc:
        SearchConfig(queries=["   "])
    assert "queries" in str(exc.value)


def test_unknown_field_is_rejected():
    with pytest.raises(ValidationError) as exc:
        SearchConfig(queries=["AI"], unknown_field=1)
    assert "unknown_field" in str(exc.value)


def test_load_config_reads_search_section():
    config = load_config()
    assert config.search.queries
    assert config.search.max_pages_per_query >= 1
