from datetime import datetime

from raiseplug import store


def test_parse_accepts_partial_dates_models_cite():
    assert store.parse("2024") == datetime(2024, 1, 1) and store.parse("2025-08") == datetime(2025, 8, 1)


def test_same_fact_twice_is_stored_once():
    from conftest import fresh
    from raiseplug import tools
    d = fresh()
    a = tools.add_evidence(d, None, None, 1, kind="deal", claim="Led X seed", source_url="https://f.example")
    assert tools.add_evidence(d, None, None, 1, kind="deal", claim="Led X seed", source_url="https://f.example") == a
