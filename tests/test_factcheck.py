"""Offline tests for the fact-checker and the daily budget cap."""
import json

import pytest

from app import config, usage_log
from app.deck import Bullet, Chart, ChartPoint, Deck, Slide
from app.factcheck import check_deck, context_numbers_from, extract_numbers
from app.facts import FactTable


@pytest.fixture
def facts():
    t = FactTable()
    t.add("Total revenue_usd, 2026-10", 2_042_729, "usd", "s")                      # F1 $2.04M
    t.add("Change in Total revenue_usd, 2026-09 to 2026-10", 64_110, "usd", "s")      # F2 +$64K
    t.add("Change in Total revenue_usd (%), 2026-09 to 2026-10", 3.24, "pct", "s")    # F3 +3.2%
    t.add("Return rate (total), 2026-10", 6.02, "pct", "s")                           # F4 6.0%
    t.add("Change in Return rate (total), 2026-09 to 2026-10", 0.81, "pp", "s")       # F5 +0.8 pp
    t.add("Change in revenue_usd, West, 2026-09 to 2026-10", -18_402, "usd", "s")     # F6 -$18K
    t.add("Total orders, 2026-10", 25_245, "count", "s")                             # F7 25,245
    return t


def _deck(bullets, title="Revenue grew 3.2% to $2.04M", title_ids=("F1", "F3"), chart=None):
    return Deck(deck_title="Northwind review", subtitle="Monthly business review: 2026-09 vs 2026-10",
                executive_summary=[Bullet(text=t, fact_ids=list(ids)) for t, ids in bullets],
                slides=[Slide(title=title, title_fact_ids=list(title_ids), bullets=[], chart=chart,
                              speaker_notes="")])


def test_correct_numbers_pass(facts):
    deck = _deck([("Revenue rose $64K (+3.2%) to $2.04M", ["F1", "F2", "F3"]),
                  ("Return rate up 0.8 percentage points to 6.0%", ["F4", "F5"]),
                  ("West fell -$18K; orders reached 25,245", ["F6", "F7"])])
    report = check_deck(deck, facts, set())
    assert report.passed and report.verified == report.numbers_checked == 9


def test_made_up_number_is_caught(facts):
    deck = _deck([("Revenue rose $64K. Customer satisfaction reached 93.7%.", ["F2"])])
    report = check_deck(deck, facts, set())
    assert not report.passed
    assert report.violations[0]["number"] == "93.7%"
    assert "no fact" in report.violations[0]["reason"]


def test_wrongly_rounded_number_is_caught(facts):
    # True value is +$64K; "$70K" is not a rounding of it at the precision written.
    report = check_deck(_deck([("Revenue rose $70K", ["F2"])]), facts, set())
    assert [v["number"] for v in report.violations] == ["$70K"]


def test_missing_citation_is_repaired_not_rejected(facts):
    deck = _deck([("Orders reached 25,245", [])])
    report = check_deck(deck, facts, set())
    assert report.passed and report.auto_cited[0]["fact"] == "F7"
    assert deck.executive_summary[0].fact_ids == ["F7"]


def test_dates_and_note_numbers_are_not_claims(facts):
    context = context_numbers_from("2026-09", "2026-10", "Cold-weather promo ran Oct 3-17")
    deck = _deck([("Promo ran Oct 3-17 in 2026-10 across 3 regions", [])], title="Promo lifted sales", title_ids=())
    report = check_deck(deck, facts, context)
    assert report.numbers_checked == 0 and report.passed


def test_chart_with_unknown_fact_or_mixed_units_fails(facts):
    chart = Chart(type="column", title="Mixed", points=[ChartPoint(label="Rev", fact_id="F1"),
                                                        ChartPoint(label="Rate", fact_id="F4"),
                                                        ChartPoint(label="Ghost", fact_id="F99")])
    report = check_deck(_deck([], chart=chart), facts, set())
    reasons = " ".join(v["reason"] for v in report.violations)
    assert "unknown fact" in reasons and "mixes units" in reasons


def test_number_parsing_variants():
    nums = {n.raw: (n.value, n.kind) for n in extract_numbers("$2.04 million, 36.6K units, -0.2 pp, 12.5%", set())}
    assert nums["$2.04 million"] == (2_040_000, "usd")
    assert nums["36.6K"] == (36_600, "count")
    assert nums["-0.2 pp"] == (0.2, "pp")
    assert nums["12.5%"] == (12.5, "pct")


def test_daily_budget_blocks_new_runs(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "USAGE_LOG", tmp_path / "usage.jsonl")
    monkeypatch.setattr(config, "DAILY_BUDGET_USD", 0.01)
    usage_log.check_daily_budget()  # nothing spent yet
    usage_log.log_run({"usage": {"cost_usd": 0.006}})
    usage_log.log_run({"usage": {"cost_usd": 0.006}})
    assert usage_log.spent_today() == pytest.approx(0.012)
    with pytest.raises(usage_log.DailyBudgetExceeded):
        usage_log.check_daily_budget()
    lines = (tmp_path / "usage.jsonl").read_text().splitlines()
    assert len(lines) == 2 and "date" in json.loads(lines[0])
