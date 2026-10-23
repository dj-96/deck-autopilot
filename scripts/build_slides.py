"""Build slides.html: a 10-slide reveal.js deck (reveal.js from a CDN, every image embedded).

    python scripts/build_slides.py

Numbers come from docs/evidence/ (same sources as report.html). Arrow keys move, F = full screen.
"""
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from build_report import (EV, LOADED_COST_PER_HOUR, MANUAL_HOURS_PER_REFRESH, R, REFRESHES_PER_MONTH,  # noqa: E402
                          REPO_URL, REVIEW_MINUTES_WITH_APP, img, money, pipeline_diagram)

REVEAL = "https://cdn.jsdelivr.net/npm/reveal.js@5.1.0"


def main() -> None:
    batch = json.loads((EV / "batch_runs.json").read_text(encoding="utf-8"))["runs"]
    cost = json.loads((EV / "cost_model.json").read_text(encoding="utf-8"))
    base = json.loads((EV / "baseline_single_prompt.json").read_text(encoding="utf-8"))
    abl = json.loads((EV / "batch_runs_maxfacts400.json").read_text(encoding="utf-8"))["runs"]
    clean = [r for r in batch if r["kind"] == "clean"]
    pois = [r for r in batch if r["kind"] == "poisoned"]
    tamp = [r for r in batch if r["kind"] == "tamper"]
    pr = cost["per_run"]
    mean_cost = pr["cost_usd"]["mean"]
    users = cost["users"]
    bsum = base["summary"]
    abl_cost = statistics.mean(r["cost_usd"] for r in abl)
    story = lambda rs, k: sum(r["stories"][k] for r in rs)  # noqa: E731
    app_hours = (pr["elapsed_s"]["mean"] / 60 + REVIEW_MINUTES_WITH_APP) / 60
    saved_month = (MANUAL_HOURS_PER_REFRESH - app_hours) * REFRESHES_PER_MONTH

    def tile(value: str, label: str, cls: str = "") -> str:
        return f'<div class="tile {cls}"><b>{value}</b><span>{label}</span></div>'

    slides = []

    # 1 Title
    slides.append(f"""
<section class="title">
  <div class="accent"></div>
  <h1><span class="pink">Deck</span> Autopilot</h1>
  <p class="pitch">Last month's client deck, refreshed in a minute,<br>with every number proven against the data.</p>
  <p class="byline">Jun Kim · Yale SOM · MGT 409 Final Project · October 2026</p>
  <p class="small muted">{REPO_URL}</p>
</section>""")

    # 2 Problem
    slides.append(f"""
<section>
  <h2>The problem: recurring decks eat junior time</h2>
  <div class="cols">
    <div>
      <p class="lead">Every month, the most junior consultant rebuilds the same client deck by hand:</p>
      <ol class="flow">
        <li>Export the new data</li><li>Recompute comparisons in Excel</li><li>Paste into charts</li>
        <li>Rewrite every title whose story changed</li><li><b class="pink">Re-check every number</b>: one wrong figure in front of a client costs credibility</li>
      </ol>
      <p class="small muted">From my own strategy-consulting work: general, recurring information, the same manual effort every cycle, and engagements that stop at advice because ongoing reporting is too expensive to keep up.</p>
    </div>
    <div class="stack">
      {tile(f"~{MANUAL_HOURS_PER_REFRESH:.0f} h", "per refresh, including checks")}
      {tile(f"~{MANUAL_HOURS_PER_REFRESH * REFRESHES_PER_MONTH:.0f} h", f"per consultant per month ({REFRESHES_PER_MONTH} refreshes)")}
      <p class="tiny muted">Estimates (assumptions), not measurements.</p>
    </div>
  </div>
</section>""")

    # 3 What is new
    slides.append(f"""
<section>
  <h2>What's new: the numbers in the story are proven</h2>
  <table class="cmp">
    <tr><th></th><th>Finds what changed</th><th>Writes the story</th><th>Checks the numbers in the text</th><th>Editable .pptx</th></tr>
    <tr><td>ChatGPT with data analysis</td><td class="y">Yes</td><td class="y">Yes</td><td class="n">No</td><td class="p">Partly</td></tr>
    <tr><td>Copilot in PowerPoint · Gamma</td><td class="n">Limited</td><td class="y">Yes</td><td class="n">No</td><td class="y">Yes</td></tr>
    <tr><td>think-cell · UpSlide</td><td class="n">No</td><td class="n">No</td><td class="p">Charts only</td><td class="y">Yes</td></tr>
    <tr class="me"><td><b>Deck Autopilot</b></td><td class="y">Yes, 2 raw files</td><td class="y">Action titles</td><td class="y"><b>Every number</b></td><td class="y">Native charts</td></tr>
  </table>
  <div class="callout">
    <b>Tested: paste both files into one prompt, same model, {bsum['runs']} decks.</b>
    {bsum['numbers'] - 1} of {bsum['numbers']} numbers right, but <b class="pink">1 deck in {bsum['runs']} had a wrong number</b>
    ("Accessories added $18,988"; truth: $8,988) <b>and nothing says which.</b> So someone still checks all ~55 by hand.
  </div>
</section>""")

    # 4 Agents
    slides.append(f"""
<section>
  <h2>How it works: AI decides, code proves</h2>
  <div class="card diagram">{pipeline_diagram()}</div>
  <div class="cols3 small">
    <div><b class="pink">Analyst agent</b><br>Calls 7 Python tools; every number becomes a fact with an ID. Never does math.</div>
    <div><b class="pink">Storyliner agent</b><br>Writes action titles and bullets that must cite fact IDs. Charts hold only IDs.</div>
    <div><b class="pink">Fact-checker</b><br>Matches every written number to its fact at the precision written; sends misses back.</div>
  </div>
  <p class="tiny muted">Model: gpt-6-luna for both agents (course key; automatic fallback to an OpenAI key). Fixed pipeline = predictable cost, every step testable.</p>
</section>""")

    # 5 Demo 1
    slides.append(f"""
<section>
  <h2>Demo: one click to a checked deck</h2>
  <div class="cols wide-left">
    <div class="shot">{img("02_result_summary.png", "Result screen")}</div>
    <div class="stack small">
      <p><b>Sample client, Sep → Oct.</b> 32 rows per month.</p>
      <p>Analyst: <b>25 tool calls</b>, 200 facts.<br>Storyliner: 6 slides.<br>Fact-checker: <b>42/42 verified</b>.</p>
      <p><b class="pink">{money(0.003969)}</b> and 44 s for the whole run.</p>
      <p class="muted">Agents light up live; the token meter runs along the bottom.</p>
    </div>
  </div>
</section>""")

    # 6 Demo 2
    slides.append(f"""
<section>
  <h2>Click any number to see where it came from</h2>
  <div class="cols">
    <div class="shot">{img("04_fact_trace.png", "Fact trace panel")}</div>
    <div class="shot">{img("pptx_slide5.png", "Exported PowerPoint slide")}<p class="tiny muted">Downloaded .pptx: native, editable chart; values pulled from the fact table, never from model text.</p></div>
  </div>
</section>""")

    # 7 Cost
    slides.append(f"""
<section>
  <h2>Cost to run: less than a cent a deck</h2>
  <div class="tiles4">
    {tile(money(mean_cost), f"per deck (mean of {len(clean)} runs)", "hot")}
    {tile(money(users['typical']['per_user_month'], 2), f"per user / month ({users['typical']['runs_per_month']} runs)")}
    {tile(f"${users['typical']['users_100']:,.0f}", "100 users / month")}
    {tile(f"${users['typical']['users_10000']:,.0f}", "10,000 users / month")}
  </div>
  <div class="cols small">
    <ul>
      <li>{pr['input_tokens']['mean']:,.0f} input tokens per run, <b>{cost['cache_share']:.0%} cached</b>; {pr['output_tokens']['mean']:,.0f} output</li>
      <li>Prompt caching saves {1 - mean_cost / cost['no_cache_cost_mean']:.0%}; math in Python keeps raw rows out of the prompt</li>
      <li>Plus hosting: ~${cost['hosting_usd_month']['100']} / ~${cost['hosting_usd_month']['10000']} a month (estimate)</li>
    </ul>
    <div class="callout tight"><b>A cost cut I reversed.</b> A 200-fact cap ran out in {sum(r['facts'] >= 200 for r in clean)}/{len(clean)} runs and missed the Footwear story in 2.
    At 400: all 3 planted stories in {story(abl, 'footwear_returns')}/{len(abl)} runs, for <b>+{abl_cost / mean_cost - 1:.0%}</b> ({money(abl_cost)}). Now the default.</div>
  </div>
</section>""")

    # 8 Safety
    slides.append(f"""
<section>
  <h2>Safety: defenses that fired in real runs</h2>
  <div class="cols wide-left">
    <div class="shot">{img("07_safety_log.png", "Safety log")}</div>
    <div class="stack">
      {tile(f"{len(pois)}/{len(pois)}", "hidden prompt injections quarantined; 0 leaked into a deck", "hot")}
      {tile(f"{len(tamp)}/{len(tamp)}", "planted fake numbers caught and fixed")}
      {tile("0 / 16", "runs shipped an unverified number")}
      <p class="tiny muted">Plus: 120K tokens/run, 10 turns, 30 tool calls, $1/day budget, 2 MB files. 43 offline tests.</p>
    </div>
  </div>
</section>""")

    # 9 Impact
    slides.append(f"""
<section>
  <h2>Impact: the numbers</h2>
  <div class="tiles4">
    {tile(f"{pr['elapsed_s']['mean']:.0f} s", "to a checked deck (measured)", "hot")}
    {tile(f"~{saved_month:.0f} h", "saved per consultant / month (estimate)")}
    {tile(f"${saved_month * LOADED_COST_PER_HOUR:,.0f}", f"of time / month at ${LOADED_COST_PER_HOUR}/h (estimate)")}
    {tile(money(users['typical']['per_user_month'], 2), "token cost / month (measured)")}
  </div>
  <div class="cols small">
    <div class="callout tight big"><b>Quality, measured:</b> single prompt put a wrong number in 1 of {bsum['runs']} decks with no warning; Deck Autopilot shipped <b class="pink">0 unverified numbers in 16 runs</b> and shows the formula behind each one.</div>
    <div class="callout tight big"><b>If the assumptions are off:</b> even at 1 hour per manual refresh it still saves ~{(1 - app_hours) * REFRESHES_PER_MONTH:.0f} h a month. The real question is trust, which is what the per-number trace is for.</div>
  </div>
  <p class="tiny muted">Assumptions: {MANUAL_HOURS_PER_REFRESH:.0f} h manual refresh, {REVIEW_MINUTES_WITH_APP} min review, {REFRESHES_PER_MONTH} refreshes / month. Not yet validated with a real user.</p>
</section>""")

    # 10 Next
    slides.append("""
<section>
  <h2>What's next</h2>
  <div class="cols">
    <div>
      <h3 class="pink">Doesn't work yet</h3>
      <ul class="small">
        <li>Not tested with a real user (kit is ready in the repo)</li>
        <li>Writes a fresh deck; doesn't update <i>your</i> template</li>
        <li>Strict checker rejects correct derived numbers (sums, shares)</li>
        <li>Two periods of tabular data; synthetic 32-row client</li>
      </ul>
    </div>
    <div>
      <h3 class="pink">With another month</h3>
      <ol class="small">
        <li><b>Template-aware refresh</b> of last month's .pptx</li>
        <li><b>Derived-number verifier</b>: model proposes, code recomputes</li>
        <li><b>Pilot with my former team</b>: measured before/after</li>
        <li>Multi-period trends, hosting, per-user budgets</li>
      </ol>
    </div>
  </div>
  <p class="closing"><span class="pink">AI decides what matters. Code proves every number.</span></p>
</section>""")

    assert len(slides) <= 10
    css = """
:root { --r-background-color: #0b0b0d; --r-main-color: #f4f4f5; --r-heading-color: #fff; --r-link-color: #ff2e93;
        --r-main-font: "Segoe UI", Inter, system-ui, sans-serif; --r-heading-font: "Segoe UI", Inter, system-ui, sans-serif;
        --r-main-font-size: 30px; --r-heading-font-weight: 800; --r-heading-text-transform: none; --r-heading-letter-spacing: -0.02em; }
html, body, .reveal-viewport { background: #0b0b0d; }
.reveal { font-size: 30px; font-family: "Segoe UI", Inter, system-ui, -apple-system, sans-serif; color: #f4f4f5; line-height: 1.35; }
.reveal h1, .reveal h2, .reveal h3 { font-family: inherit; color: #fff; font-weight: 800; letter-spacing: -0.02em; line-height: 1.15; }
.reveal b, .reveal strong { color: #fff; }
.reveal table.cmp td { color: #e4e4e7; }
.reveal .slides section { text-align: left; height: 100%; padding-top: 10px; }
.reveal h1 { font-size: 3.1em; margin: 0 0 .25em; }
.reveal h2 { font-size: 1.45em; margin: 0 0 .6em; padding-bottom: .25em; border-bottom: 4px solid #ff2e93; display: inline-block; }
.reveal h3 { font-size: 1em; margin: 0 0 .4em; }
.reveal .pink { color: #ff2e93; } .reveal .muted { color: #a1a1aa; }
.small { font-size: .78em; } .tiny { font-size: .55em; }
.reveal .title { display: flex !important; flex-direction: column; justify-content: center; }
.title .accent { width: 140px; height: 10px; background: #ff2e93; margin-bottom: 26px; }
.pitch { font-size: 1.25em; line-height: 1.35; margin: 0 0 1em; }
.byline { font-size: .8em; color: #ff2e93; margin: 0; }
.lead { margin: 0 0 .4em; }
.cols { display: grid; grid-template-columns: 1fr 1fr; gap: 36px; align-items: start; }
.cols.wide-left { grid-template-columns: 1.65fr 1fr; }
.cols3 { display: grid; grid-template-columns: repeat(3, 1fr); gap: 24px; margin-top: 18px; }
.stack { display: flex; flex-direction: column; gap: 14px; }
.stack p { margin: 0; }
.tile { background: #141418; border: 1px solid #2a2a31; border-radius: 14px; padding: 14px 18px; }
.tile b { display: block; font-size: 1.6em; line-height: 1.1; color: #fff; }
.tile span { color: #a1a1aa; font-size: .6em; }
.tile.hot { border-color: #ff2e93; background: rgba(255,46,147,.1); }
.tile.hot b { color: #ff2e93; }
.tiles4 { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 24px; }
ol.flow { margin: 0 0 .6em 1.1em; font-size: .85em; } ol.flow li { margin: .2em 0; }
.reveal ul, .reveal ol { margin-left: 1.1em; } .reveal li { margin: .25em 0; }
.callout { background: #141418; border-left: 5px solid #ff2e93; padding: 14px 18px; border-radius: 0 12px 12px 0; font-size: .72em; margin-top: 20px; line-height: 1.45; }
.callout.tight { margin-top: 0; }
.callout.big { font-size: .9em; padding: 20px 24px; }
.card { background: #fff; border-radius: 14px; padding: 14px 18px; }
.diagram svg { width: 100%; height: auto; display: block; }
.shot img { width: 100%; border-radius: 10px; border: 1px solid #2a2a31; display: block; }
.shot p { margin: .4em 0 0; }
table.cmp { width: 100%; border-collapse: collapse; font-size: .62em; }
table.cmp th { text-align: left; color: #a1a1aa; font-weight: 600; border-bottom: 2px solid #2a2a31; padding: 8px 10px; }
table.cmp td { border-bottom: 1px solid #2a2a31; padding: 9px 10px; }
table.cmp td.y { color: #4ade80; } table.cmp td.n { color: #71717a; } table.cmp td.p { color: #fbbf24; }
table.cmp tr.me td { background: rgba(255,46,147,.12); border-bottom: 2px solid #ff2e93; }
table.cmp tr.me td:first-child { color: #ff2e93; }
.closing { position: absolute; bottom: 30px; left: 0; font-size: 1.15em; font-weight: 800; }
.reveal .progress { color: #ff2e93; }
.reveal .slide-number { background: transparent; color: #71717a; font-size: 14px; }
.reveal .controls { color: #ff2e93; }
"""
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Deck Autopilot · Jun Kim · MGT 409</title>
<link rel="stylesheet" href="{REVEAL}/dist/reveal.css">
<style>{css}</style></head>
<body><div class="reveal"><div class="slides">{''.join(slides)}</div></div>
<script src="{REVEAL}/dist/reveal.js"></script>
<script>Reveal.initialize({{ hash: true, controls: true, progress: true, slideNumber: "c/t", center: false,
  width: 1280, height: 720, margin: 0.05, transition: "slide" }});</script>
</body></html>"""
    out = R / "slides.html"
    out.write_text(page, encoding="utf-8")
    print(f"wrote {out.relative_to(R)}: {len(slides)} slides, {out.stat().st_size / 1e6:.2f} MB")


if __name__ == "__main__":
    main()
