"""Baseline: "just paste the data into ChatGPT". One prompt, same model, no tools, no fact-checker.

Pastes both CSVs into a single prompt and asks for the same deck. Then every number it wrote
is checked against an exhaustive reference fact table (~1,000 facts computed in Python:
totals, every 1-, 2- and 3-way breakdown, and the standard ratios). A number that matches
no fact at the precision written is counted as unverifiable.

    python scripts/baseline_single_prompt.py --runs 5

Writes docs/evidence/baseline_single_prompt.json.
"""
import argparse
import itertools
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from app import config, facts as facts_mod, tools as tools_mod  # noqa: E402
from app.context import RunContext  # noqa: E402
from app.deck import Deck  # noqa: E402
from app.factcheck import check_deck, context_numbers_from  # noqa: E402
from app.facts import FactTable  # noqa: E402
from app.guard import guard  # noqa: E402
from app.llm import call_model  # noqa: E402
from app.tools import AnalysisTools  # noqa: E402

EVIDENCE = config.REPO_DIR / "docs" / "evidence"
SEPT = config.SAMPLE_DIR / "northwind_2026_09.csv"
OCT = config.SAMPLE_DIR / "northwind_2026_10.csv"

PROMPT = """You are a strategy consultant. Below are last month's and this month's data for a client.
Write this month's business-review deck: a deck title, a subtitle, an executive summary of 3-5 bullets,
and 4-6 slides. Each slide has an action title (the so-what, with the key number), 2-4 bullets, and
speaker notes. Use specific numbers from the data. Set every fact_ids list to [] and every chart to null.

## Last month (2026-09)
{sept}

## This month (2026-10)
{oct}
"""


def reference_facts() -> tuple[FactTable, set[str]]:
    """Every number a reasonable analyst might quote, computed exactly."""
    tools_mod.MAX_GROUPS = 100  # no truncation for the reference table
    facts_mod.MAX_FACTS = 10_000
    data = guard(SEPT, SEPT.name, OCT, OCT.name, RunContext())
    ft = FactTable()
    t = AnalysisTools(data, ft)
    t.define_metric("gross_profit_usd", "revenue_usd", "-", "cogs_usd")
    dims = data.dimensions
    for m in data.metrics:
        t.compare_total(m)
        for n in (1, 2, 3):
            for combo in itertools.combinations(dims, n):
                t.compare_by(m, list(combo), top_n=100)
    ratios = [("returns_usd", "revenue_usd", "Return rate"), ("gross_profit_usd", "revenue_usd", "Gross margin"),
              ("marketing_usd", "revenue_usd", "Marketing % of revenue"),
              ("new_customers", "orders", "New-customer share"), ("cogs_usd", "revenue_usd", "COGS % of revenue")]
    for num, den, name in ratios:
        t.compare_ratio(num, den, name)
        for d in dims:
            t.compare_ratio(num, den, name, d)
    text_cells = [str(v) for df in (data.prev, data.curr) for c in data.text_columns + dims for v in df[c].dropna()]
    return ft, context_numbers_from(data.prev_label, data.curr_label, *text_cells)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=int, default=5)
    args = ap.parse_args()
    ref, context = reference_facts()
    print(f"reference fact table: {len(ref):,} facts")
    prompt = PROMPT.format(sept=SEPT.read_text(encoding="utf-8"), oct=OCT.read_text(encoding="utf-8"))

    runs = []
    for i in range(args.runs):
        ctx = RunContext()
        t0 = time.time()
        resp, gateway = call_model("baseline", ctx.meter, structured=Deck, input=prompt)
        deck: Deck = resp.output_parsed
        report = check_deck(deck, ref, context)  # no citations: every number must match *some* fact
        u = ctx.meter.summary()
        runs.append({
            "i": i, "elapsed_s": round(time.time() - t0, 1), "gateway": gateway,
            "input_tokens": u["input_tokens"], "cached_tokens": u["cached_tokens"],
            "output_tokens": u["output_tokens"], "cost_usd": u["cost_usd"],
            "numbers": report.numbers_checked, "verified": report.verified,
            "unverifiable": len(report.violations), "violations": report.violations,
            "deck": deck.model_dump(),
        })
        print(f"  run {i}: {report.verified}/{report.numbers_checked} numbers match the data, "
              f"{len(report.violations)} unverifiable, ${u['cost_usd']:.4f}, {runs[-1]['elapsed_s']}s")
        for v in report.violations[:6]:
            print(f"      x {v['number']!r} in: {v['text'][:110]}")

    total = sum(r["numbers"] for r in runs)
    bad = sum(r["unverifiable"] for r in runs)
    decks_with_error = sum(1 for r in runs if r["unverifiable"])
    print(f"\nTOTAL: {bad}/{total} numbers unverifiable ({bad / max(total, 1):.1%}); "
          f"{decks_with_error}/{len(runs)} decks contain at least one")
    EVIDENCE.mkdir(parents=True, exist_ok=True)
    (EVIDENCE / "baseline_single_prompt.json").write_text(json.dumps(
        {"reference_facts": len(ref), "runs": runs,
         "summary": {"numbers": total, "unverifiable": bad, "decks_with_error": decks_with_error,
                     "runs": len(runs)}}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
