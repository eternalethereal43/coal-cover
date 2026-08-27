"""Checks on the derived measures and on the parser's alignment guard."""
import pytest

from scraper import normalize, parse_xls


def plant(**kw):
    base = dict(
        plant="TEST TPS", state="Odisha", utility="NTPC", section="A",
        mode_of_transport="RAIL", capacity_mw=1000.0, plf_pct=70.0,
        norm_days=22.0, daily_req_kt=10.0, norm_stock_kt=220.0,
        stock_indigenous_kt=100.0, stock_import_kt=0.0, stock_total_kt=100.0,
        receipt_kt=8.0, consumption_kt=12.0, critical_flag=False, remarks="",
    )
    base.update(kw)
    return base


def test_cover_days_use_the_right_denominator():
    e = normalize.enrich(plant())
    assert e["cover_days_normative"] == 10.0                          # 100 / 10
    assert e["cover_days_actual"] == pytest.approx(8.33, abs=0.01)    # 100 / 12


def test_drawdown_projects_days_to_empty():
    e = normalize.enrich(plant())
    assert e["net_change_kt"] == -4.0
    assert e["days_to_empty"] == 25.0
    assert normalize.enrich(plant(receipt_kt=20.0))["days_to_empty"] is None


def test_critical_bands_follow_cea_thresholds():
    assert normalize.enrich(plant(stock_total_kt=50.0))["is_critical"]        # 22.7%
    assert not normalize.enrich(plant(stock_total_kt=60.0))["is_critical"]    # 27.3%
    assert normalize.enrich(plant(stock_total_kt=20.0))["is_supercritical"]   # 9.1%


def test_report_asterisk_wins_even_above_the_threshold():
    assert normalize.enrich(plant(stock_total_kt=200.0, critical_flag=True))["is_critical"]


def test_percent_of_normative_is_derived_when_missing():
    assert normalize.enrich(plant())["pct_of_norm"] == pytest.approx(45.5, abs=0.1)


def test_ownership_routing():
    assert normalize.enrich(plant(utility="NTPC"))["ownership"] == "Central"
    assert normalize.enrich(plant(utility="IPP"))["ownership"] == "Private / IPP"
    assert normalize.enrich(plant(utility="Odisha"))["ownership"] == "State"


def test_summary_excludes_idle_stations():
    rows = [normalize.enrich(plant()),
            normalize.enrich(plant(plant="IDLE TPS", section="C", capacity_mw=0.0))]
    assert normalize.summarise(rows)["plants"] == 1


def test_alignment_guard_rejects_shifted_columns():
    """normative stock must equal daily requirement x normative days."""
    parse_xls.validate([plant() for _ in range(25)])  # does not raise
    with pytest.raises(parse_xls.ParseError):
        parse_xls.validate([plant(norm_stock_kt=999.0) for _ in range(25)])


def test_number_coercion():
    assert parse_xls.to_num("1,234.5") == 1234.5
    assert parse_xls.to_num("74%") == 74.0
    assert parse_xls.to_num("null") is None
    assert parse_xls.to_num("RAIL") is None


# --- output layout ---------------------------------------------------------

def test_daily_snapshots_drop_nulls_and_recomputable_fields():
    from scraper import build_site
    rec = normalize.enrich(plant(remarks="", stock_import_kt=0.0))
    rec["section_name"] = "Domestic coal"
    slim = build_site._compact(rec)
    assert "section_name" not in slim          # derivable from `section`
    assert "days_to_empty" in slim             # this station is drawing down
    assert "remarks" not in slim               # empty string dropped
    assert "is_supercritical" not in slim      # False dropped
    assert slim["stock_import_kt"] == 0.0      # a real zero is kept


def test_months_touched_maps_dates_to_partitions():
    from scraper import build_site
    assert build_site._months_touched(
        ["2026-07-14", "2026-07-31", "2026-08-01"]
    ) == {"2026-07", "2026-08"}
