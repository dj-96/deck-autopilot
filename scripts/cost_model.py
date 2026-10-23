"""Turn measured runs into cost per run, per user per month, and at 100 / 10,000 users.

Inputs: docs/evidence/batch_runs.json (scripts/batch_runs.py) and
        docs/evidence/baseline_single_prompt.json (scripts/baseline_single_prompt.py).
Writes docs/evidence/cost_model.json and docs/evidence/cost_model.md.

Every assumption is a named constant below so the report can quote it.
"""
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from app import config  # noqa: E402

EVIDENCE = config.REPO_DIR / "docs" / "evidence"
P = config.PRICES

# --- Usage assumptions (estimates, stated in the report) ----------------------------------
# A consultant on 2 client engagements, each with a weekly status deck and a monthly review
# (2 x (4 + 1) = 10 recurring refreshes), re-running each about twice after data fixes.
RUNS_PER_USER_MONTH = {"light": 5, "typical": 20, "heavy": 60}
WORKDAYS_PER_MONTH = 21
HOSTING_USD_MONTH = {100: 25, 10_000: 400}  # small VM vs. autoscaled containers + queue (estimate)
SAMPLE_ROWS_PER_FILE = 32


def cost(inp: float, cached: float, out: float) -> float:
    return ((inp - cached) * P["input"] + cached * P["cached_input"] + out * P["output"]) / 1e6


def pct(vals, q):
    vals = sorted(vals)
    return vals[min(len(vals) - 1, round(q * (len(vals) - 1)))]


def main() -> None:
    runs = json.loads((EVIDENCE / "batch_runs.json").read_text(encoding="utf-8"))["runs"]
    base = json.loads((EVIDENCE / "baseline_single_prompt.json").read_text(encoding="utf-8"))["runs"]
    clean = [r for r in runs if r["kind"] == "clean"]

    def stats(rs, key):
        v = [r[key] for r in rs]
        return {"mean": statistics.mean(v), "median": statistics.median(v), "p90": pct(v, .9),
                "min": min(v), "max": max(v)}

    per_run = {k: stats(clean, k) for k in ("input_tokens", "cached_tokens", "output_tokens", "cost_usd",
                                            "elapsed_s", "model_calls", "tool_calls")}
    mean_cost = per_run["cost_usd"]["mean"]
    fix_round = [r for r in runs if r["kind"] == "tamper"]
    fix_cost = statistics.mean(r["cost_usd"] for r in fix_round) if fix_round else None

    agents = {}
    for a in ("analyst", "storyliner"):
        rows = [r["per_agent"][a] for r in clean]
        agents[a] = {k: statistics.mean(x[k] for x in rows) for k in ("calls", "input", "cached", "output", "cost")}

    # Caching: what the same tokens would cost with no cache hits.
    no_cache = statistics.mean(cost(r["input_tokens"], 0, r["output_tokens"]) for r in clean)
    cache_share = sum(r["cached_tokens"] for r in clean) / sum(r["input_tokens"] for r in clean)

    users = {}
    for profile, n in RUNS_PER_USER_MONTH.items():
        users[profile] = {"runs_per_month": n, "per_user_month": n * mean_cost,
                          "users_100": n * mean_cost * 100, "users_10000": n * mean_cost * 10_000}
    typical = RUNS_PER_USER_MONTH["typical"]
    runs_per_day_10k = typical * 10_000 / WORKDAYS_PER_MONTH

    b_in = statistics.mean(r["input_tokens"] for r in base)
    b_cost = statistics.mean(r["cost_usd"] for r in base)
    tokens_per_row = b_in / (2 * SAMPLE_ROWS_PER_FILE)  # rough: prompt overhead is small next to the CSVs
    scale = []
    for rows in (32, 500, 5_000):
        single_in = tokens_per_row * rows * 2
        scale.append({"rows_per_file": rows, "single_prompt_input_tokens": round(single_in),
                      "single_prompt_cost": cost(single_in, 0, statistics.mean(r["output_tokens"] for r in base)),
                      "pipeline_cost_note": "tool results are aggregates capped at 25 groups per call and 200 facts per run, so input is bounded (not measured on large files)"})

    model = {"prices_per_1m": P, "per_run": per_run, "per_agent_mean": agents,
             "fix_round_run_cost_mean": fix_cost, "no_cache_cost_mean": no_cache, "cache_share": cache_share,
             "users": users, "hosting_usd_month": HOSTING_USD_MONTH, "runs_per_day_at_10k": runs_per_day_10k,
             "daily_cap_runs_at_default": config.DAILY_BUDGET_USD / mean_cost,
             "baseline": {"input_tokens_mean": b_in, "cost_mean": b_cost, "tokens_per_row": tokens_per_row},
             "scale_with_rows": scale, "n_clean_runs": len(clean)}
    (EVIDENCE / "cost_model.json").write_text(json.dumps(model, indent=2), encoding="utf-8")

    r = per_run
    md = [f"# Cost model (from {len(clean)} measured clean runs on the sample data)", "",
          f"Prices: ${P['input']}/1M input, ${P['cached_input']}/1M cached input, ${P['output']}/1M output (gpt-6-luna).", "",
          "## One run", "", "| | mean | median | p90 | min | max |", "|---|---|---|---|---|---|"]
    for k, label, f in [("input_tokens", "Input tokens", "{:,.0f}"), ("cached_tokens", "of which cached", "{:,.0f}"),
                        ("output_tokens", "Output tokens", "{:,.0f}"), ("model_calls", "Model calls", "{:.1f}"),
                        ("tool_calls", "Tool calls", "{:.1f}"), ("elapsed_s", "Seconds", "{:.1f}"),
                        ("cost_usd", "Cost (USD)", "${:.4f}")]:
        md.append(f"| {label} | " + " | ".join(f.format(r[k][s]) for s in ("mean", "median", "p90", "min", "max")) + " |")
    md += ["", "By agent (mean per run):", "", "| Agent | Calls | Input | Cached | Output | Cost |", "|---|---|---|---|---|---|"]
    for a, x in agents.items():
        md.append(f"| {a} | {x['calls']:.1f} | {x['input']:,.0f} | {x['cached']:,.0f} | {x['output']:,.0f} | ${x['cost']:.4f} |")
    md += ["", f"- A run that needs one fact-check fix round costs ${fix_cost:.4f} on average (tamper runs)." if fix_cost else "",
           f"- Prompt caching: {cache_share:.0%} of input tokens were cache hits. Without caching the same runs would cost "
           f"${no_cache:.4f} (caching saves {1 - mean_cost / no_cache:.0%}).",
           "", "## Per user and at scale (token cost only)", "",
           "| Usage profile | Runs / user / month | Per user / month | 100 users / month | 10,000 users / month |",
           "|---|---|---|---|---|"]
    for p, u in users.items():
        md.append(f"| {p} | {u['runs_per_month']} | ${u['per_user_month']:.3f} | ${u['users_100']:.2f} | ${u['users_10000']:,.0f} |")
    md += ["", f"Hosting estimate: ~${HOSTING_USD_MONTH[100]}/month at 100 users, ~${HOSTING_USD_MONTH[10_000]}/month at 10,000 users.",
           f"At 10,000 typical users that is ~{runs_per_day_10k:,.0f} runs per workday; the default $"
           f"{config.DAILY_BUDGET_USD:.2f} daily cap covers ~{config.DAILY_BUDGET_USD / mean_cost:,.0f} runs, so at scale the cap "
           "becomes per user rather than global.", "",
           "## Versus pasting the data into one prompt", "",
           f"Single prompt (same model, both CSVs pasted): ${b_cost:.4f} per deck, {b_in:,.0f} input tokens "
           f"(~{tokens_per_row:.0f} tokens per CSV row). The pipeline costs ${mean_cost:.4f}: about "
           f"{mean_cost / b_cost:.1f}x more on this small sample, for verification and traceability.", "",
           "| Rows per file | Single-prompt input tokens | Single-prompt cost / deck | Pipeline |", "|---|---|---|---|"]
    for s in scale:
        md.append(f"| {s['rows_per_file']:,} | {s['single_prompt_input_tokens']:,} | ${s['single_prompt_cost']:.4f} | "
                  f"~${mean_cost:.4f} (bounded by tool caps; not measured) |")
    md += ["", "Rows above 32 are extrapolated from tokens per row, not measured. 5,000 rows per file would also exceed what fits comfortably in one prompt. Pipeline cost at large row counts is bounded by its tool caps but has not been measured."]
    (EVIDENCE / "cost_model.md").write_text("\n".join(x for x in md if x is not None), encoding="utf-8")
    print("\n".join(md))


if __name__ == "__main__":
    main()
