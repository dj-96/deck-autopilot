"""Fact-checker: plain Python, no model. Every number on every slide must match a fact.

For each title and bullet it extracts the numbers ($64K, 7.7%, +0.8 pp, 1,954), works out
the precision the writer used, and compares against the facts that sentence cites:
  - matches a cited fact          -> verified
  - matches a fact it didn't cite -> verified, citation added automatically
  - matches nothing               -> violation (sent back to the Storyliner)
Chart points must reference real facts that all share one unit.
"""
import re
from dataclasses import dataclass, field

from app.deck import Bullet, Deck
from app.facts import FactTable

NUMBER_RE = re.compile(
    r"(?P<sign>[+\-−–])?\s?(?P<dollar>\$)?(?P<num>\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?)"
    r"(?P<suffix>\s?(?:%|percent\b|pp\b|percentage[- ]points?\b|points?\b|pts?\b)"
    r"|\s?(?:[KMB]\b|thousand\b|million\b|billion\b))?",
    re.IGNORECASE,
)
MULTIPLIERS = {"k": 1e3, "thousand": 1e3, "m": 1e6, "million": 1e6, "b": 1e9, "billion": 1e9}
SMALL_COUNT_MAX = 12  # "3 regions", "two-thirds" -- counting words, not data claims


@dataclass
class Number:
    raw: str
    value: float  # absolute value, multiplier applied
    tolerance: float
    kind: str  # usd | pct | pp | count


@dataclass
class CheckReport:
    numbers_checked: int = 0
    verified: int = 0
    auto_cited: list[dict] = field(default_factory=list)
    violations: list[dict] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.violations

    def problems(self) -> list[str]:
        return [f"{v['where']}: \"{v['number']}\" in \"{v['text']}\" — {v['reason']}" for v in self.violations]

    def to_dict(self) -> dict:
        return {"numbers_checked": self.numbers_checked, "verified": self.verified,
                "auto_cited": self.auto_cited, "violations": self.violations, "passed": self.passed}


def extract_numbers(text: str, context_numbers: set[str]) -> list[Number]:
    out = []
    for m in NUMBER_RE.finditer(text):
        raw_num = m.group("num")
        suffix = (m.group("suffix") or "").strip().lower()
        dollar = bool(m.group("dollar"))
        # Skip things that aren't data claims: dates/periods/notes text, years, small counts.
        start, end = m.span("num")
        if not dollar and not suffix:
            if raw_num in context_numbers:
                continue
            before, after = text[max(0, start - 2):start], text[end:end + 2]
            if (len(before) == 2 and before[1] in "-/" and before[0].isdigit()) or \
                    (len(after) == 2 and after[0] in "-/" and after[1].isdigit()):
                continue  # part of a date like 2026-10 or 10/17
            n = float(raw_num.replace(",", ""))
            if (1900 <= n <= 2100 and "," not in raw_num) or (n <= SMALL_COUNT_MAX and "." not in raw_num):
                continue
        digits = raw_num.replace(",", "")
        decimals = len(digits.split(".")[1]) if "." in digits else 0
        mult = 1.0
        kind = "usd" if dollar else "count"
        if suffix in ("%", "percent"):
            kind = "pct"
        elif suffix in ("pp", "point", "points", "pt", "pts") or suffix.startswith("percentage"):
            kind = "pp"
        elif suffix:
            mult = MULTIPLIERS[suffix.lower()]
        value = float(digits) * mult
        # Half a unit of the last written digit, e.g. $2.04M -> +/- $5K; 7.7% -> +/- 0.05.
        tolerance = 0.5 * (10 ** -decimals) * mult + 1e-9
        out.append(Number(m.group(0).strip(), value, tolerance, kind))
    return out


def _matches(num: Number, fact) -> bool:
    if fact is None:
        return False
    compatible = {"usd": {"usd"}, "pct": {"pct"}, "pp": {"pp"}, "count": {"count"}}[num.kind]
    # "Margin rose 0.2 points" may be written as % by habit; accept pp facts for "%" too.
    if num.kind == "pct":
        compatible = {"pct", "pp"}
    return fact.unit in compatible and abs(abs(fact.value) - num.value) <= num.tolerance


def _check_text(text: str, cited: list[str], where: str, facts: FactTable, context: set[str],
                report: CheckReport, cite_into: list[str] | None) -> None:
    for num in extract_numbers(text, context):
        report.numbers_checked += 1
        if any(_matches(num, facts.get(fid)) for fid in cited):
            report.verified += 1
            continue
        found = next((f for f in facts.facts.values() if _matches(num, f)), None)
        if found:
            report.verified += 1
            report.auto_cited.append({"where": where, "number": num.raw, "fact": found.id})
            if cite_into is not None and found.id not in cite_into:
                cite_into.append(found.id)
            continue
        unknown = [fid for fid in cited if facts.get(fid) is None]
        reason = (f"cites unknown fact IDs {unknown}" if unknown and not any(facts.get(f) for f in cited)
                  else "no fact in the table has this value")
        report.violations.append({"where": where, "text": text, "number": num.raw, "reason": reason})


def check_deck(deck: Deck, facts: FactTable, context_numbers: set[str]) -> CheckReport:
    """Check (and lightly repair citations in) a deck. Mutates fact_ids to add auto-citations."""
    report = CheckReport()

    def bullets(where: str, items: list[Bullet]) -> None:
        for i, b in enumerate(items, 1):
            _check_text(b.text, b.fact_ids, f"{where} bullet {i}", facts, context_numbers, report, b.fact_ids)

    _check_text(deck.deck_title, [], "deck title", facts, context_numbers, report, None)
    _check_text(deck.subtitle, [], "subtitle", facts, context_numbers, report, None)
    bullets("executive summary", deck.executive_summary)
    for s_i, slide in enumerate(deck.slides, 1):
        where = f"slide {s_i}"
        slide_facts = (slide.title_fact_ids + [f for b in slide.bullets for f in b.fact_ids]
                       + ([p.fact_id for p in slide.chart.points] if slide.chart else []))
        _check_text(slide.title, slide_facts, f"{where} title", facts, context_numbers, report,
                    slide.title_fact_ids)
        bullets(where, slide.bullets)
        if slide.chart:
            units = set()
            for p in slide.chart.points:
                fact = facts.get(p.fact_id)
                if fact is None:
                    report.violations.append({"where": f"{where} chart", "text": slide.chart.title,
                                              "number": p.fact_id, "reason": "chart point cites an unknown fact"})
                else:
                    units.add(fact.unit)
            if len(units) > 1:
                report.violations.append({"where": f"{where} chart", "text": slide.chart.title,
                                          "number": "/".join(sorted(units)),
                                          "reason": "chart mixes units; use facts with one unit"})
    return report


def context_numbers_from(*texts: str) -> set[str]:
    """Numbers that legitimately appear in non-fact text (period labels, client notes, e.g. 'Oct 3-17')."""
    found = set()
    for t in texts:
        found.update(m.group(0) for m in re.finditer(r"\d+(?:\.\d+)?", t or ""))
    return found
