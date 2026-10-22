"""Run the Guard + Analyst on two data files and print the fact table and findings.

    python scripts/run_analyst.py                 # sample data, Sept -> Oct
    python scripts/run_analyst.py --poisoned      # October file with a hidden prompt injection
    python scripts/run_analyst.py --prev a.csv --curr b.xlsx

Each run is saved to output/runs/ as JSON (trace, facts, findings, token usage).
"""
import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")  # Windows consoles default to cp1252

from app import config  # noqa: E402
from app.analyst import run_analyst  # noqa: E402
from app.context import RunContext  # noqa: E402
from app.guard import GuardError, guard  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--prev", type=Path, default=config.SAMPLE_DIR / "northwind_2026_09.csv")
    ap.add_argument("--curr", type=Path, default=config.SAMPLE_DIR / "northwind_2026_10.csv")
    ap.add_argument("--poisoned", action="store_true", help="use the October file with an injected note")
    args = ap.parse_args()
    if args.poisoned:
        args.curr = config.SAMPLE_DIR / "northwind_2026_10_poisoned.csv"

    ctx = RunContext()
    try:
        data = guard(args.prev, args.prev.name, args.curr, args.curr.name, ctx)
    except GuardError as err:
        sys.exit(f"Guard rejected the upload: {err}")

    print(f"\n== Guard: {data.prev_label} -> {data.curr_label}")
    print(f"   metrics:    {', '.join(data.metrics)}")
    print(f"   dimensions: {', '.join(data.dimensions)}   text: {', '.join(data.text_columns) or '-'}")
    for ev in ctx.safety:
        print(f"   BLOCKED: {ev['detail']}\n            excerpt: {ev.get('excerpt', '')!r}")

    started = time.time()
    result = run_analyst(data, ctx)
    elapsed = time.time() - started

    print("\n== Analyst tool calls")
    for ev in ctx.trace:
        if ev["agent"] == "analyst" and ev["kind"] == "tool_call":
            print(f"   {ev['detail']}")

    cited = {fid for f in result.findings for fid in f["fact_ids"]}
    print(f"\n== Fact table ({len(result.facts)} facts, {len(cited)} cited; * = cited)")
    for f in result.facts.facts.values():
        mark = "*" if f.id in cited else " "
        print(f" {mark} {f.id:>4}  {f.display:>12}  {f.label}")

    print("\n== Findings")
    for i, f in enumerate(sorted(result.findings, key=lambda x: -x["importance"]), 1):
        print(f" {i}. [{f['importance']}] {f['finding']}  ({', '.join(f['fact_ids'])})")
        if f.get("explanation"):
            print(f"      why: {f['explanation']}")

    s = ctx.meter.summary()
    print(f"\n== Usage: {s['calls']} model calls, {result.tool_calls} tool calls, {elapsed:.1f}s, "
          f"via {', '.join(s['gateways'])}")
    print(f"   {s['input_tokens']:,} input ({s['cached_tokens']:,} cached) / {s['output_tokens']:,} output tokens"
          f"  ->  ${s['cost_usd']:.5f}")

    out_dir = config.OUTPUT_DIR / "runs"
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"{time.strftime('%Y%m%d_%H%M%S')}_analyst{'_poisoned' if args.poisoned else ''}.json"
    out.write_text(json.dumps({
        "prev": args.prev.name, "curr": args.curr.name, "elapsed_s": round(elapsed, 2),
        "usage": s, "safety": ctx.safety, "trace": ctx.trace,
        "facts": result.facts.to_list(), "findings": result.findings,
    }, indent=2, default=str), encoding="utf-8")
    print(f"   saved {out.relative_to(config.REPO_DIR)}")


if __name__ == "__main__":
    main()
