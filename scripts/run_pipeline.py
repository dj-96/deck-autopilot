"""Run the full pipeline and print the checked slide content.

    python scripts/run_pipeline.py                # sample data, Sept -> Oct
    python scripts/run_pipeline.py --tamper       # slip a made-up number into draft 1 to watch the checker
    python scripts/run_pipeline.py --poisoned     # October file with a hidden prompt injection
    python scripts/run_pipeline.py --prev a.csv --curr b.xlsx

Saves output/runs/<time>_pipeline.json and appends a line to output/usage_log.jsonl.
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to cp1252

from app import config  # noqa: E402
from app.guard import GuardError  # noqa: E402
from app.pipeline import run_pipeline  # noqa: E402
from app.usage_log import DailyBudgetExceeded  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prev", type=Path, default=config.SAMPLE_DIR / "northwind_2026_09.csv")
    ap.add_argument("--curr", type=Path, default=config.SAMPLE_DIR / "northwind_2026_10.csv")
    ap.add_argument("--poisoned", action="store_true")
    ap.add_argument("--tamper", action="store_true")
    args = ap.parse_args()
    if args.poisoned:
        args.curr = config.SAMPLE_DIR / "northwind_2026_10_poisoned.csv"

    try:
        r = run_pipeline(args.prev, args.prev.name, args.curr, args.curr.name, tamper=args.tamper)
    except (GuardError, DailyBudgetExceeded) as err:
        sys.exit(f"Stopped: {err}")

    facts = r.analyst.facts
    print("\n== Steps")
    for ev in r.ctx.trace:
        if ev["kind"] == "tool_call" or (ev["agent"] == "analyst" and ev["kind"] == "model_call"):
            continue
        print(f"   [{ev['agent']}] {ev['detail']}")

    d = r.deck
    print(f"\n== {d.deck_title}\n   {d.subtitle}")
    bad = {(v["where"]) for v in r.check.violations}

    def show(where: str, text: str, ids: list[str], indent: str = "   ") -> None:
        mark = "!!" if where in bad else "ok"
        print(f"{indent}[{mark}] {text}  ({', '.join(ids) or '-'})")

    print("\n   Executive summary")
    for i, b in enumerate(d.executive_summary, 1):
        show(f"executive summary bullet {i}", b.text, b.fact_ids, "     ")
    for s_i, s in enumerate(d.slides, 1):
        print(f"\n   Slide {s_i}:")
        show(f"slide {s_i} title", s.title, s.title_fact_ids)
        for b_i, b in enumerate(s.bullets, 1):
            show(f"slide {s_i} bullet {b_i}", b.text, b.fact_ids, "     ")
        if s.chart:
            pts = ", ".join(f"{p.label}={facts.get(p.fact_id).display if facts.get(p.fact_id) else '??'}"
                            for p in s.chart.points)
            print(f"     chart ({s.chart.type}): {s.chart.title}: {pts}")
        print(f"     notes: {s.speaker_notes}")

    print("\n== Fact-check rounds")
    for rd in r.check_rounds:
        print(f"   draft {rd['draft']}: {rd['verified']}/{rd['numbers_checked']} verified, "
              f"{len(rd['auto_cited'])} auto-cited, {len(rd['violations'])} violation(s)")
        for v in rd["violations"]:
            print(f"      x {v['where']}: \"{v['number']}\" — {v['reason']}")
    print(f"   final: {'ALL NUMBERS VERIFIED' if r.check.passed else 'UNVERIFIED NUMBERS FLAGGED'}")

    s = r.ctx.meter.summary()
    print(f"\n== Usage: {s['calls']} model calls in {r.elapsed_s:.1f}s via {', '.join(s['gateways'])}")
    by_agent: dict[str, dict] = {}
    for c in s["by_agent"]:
        a = by_agent.setdefault(c["agent"], {"calls": 0, "input": 0, "cached": 0, "output": 0, "cost": 0.0})
        a["calls"] += 1
        a["input"] += c["input_tokens"]
        a["cached"] += c["cached_tokens"]
        a["output"] += c["output_tokens"]
        a["cost"] += c["cost_usd"]
    for name, a in by_agent.items():
        print(f"   {name:<11} {a['calls']} calls  {a['input']:>7,} in ({a['cached']:>6,} cached)  "
              f"{a['output']:>6,} out  ${a['cost']:.5f}")
    print(f"   {'TOTAL':<11} {s['calls']} calls  {s['input_tokens']:>7,} in ({s['cached_tokens']:>6,} cached)  "
          f"{s['output_tokens']:>6,} out  ${s['cost_usd']:.5f}")

    out_dir = config.OUTPUT_DIR / "runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    tag = "_tamper" if args.tamper else ("_poisoned" if args.poisoned else "")
    out = out_dir / f"{time.strftime('%Y%m%d_%H%M%S')}_pipeline{tag}.json"
    out.write_text(json.dumps({
        "prev": args.prev.name, "curr": args.curr.name, "elapsed_s": round(r.elapsed_s, 2),
        "usage": s, "safety": r.ctx.safety, "trace": r.ctx.trace, "check_rounds": r.check_rounds,
        "facts": facts.to_list(), "findings": r.analyst.findings, "deck": r.deck.model_dump(),
    }, indent=2, default=str), encoding="utf-8")
    print(f"   saved {out.relative_to(config.REPO_DIR)}; usage appended to "
          f"{config.USAGE_LOG.relative_to(config.REPO_DIR)}")


if __name__ == "__main__":
    main()
