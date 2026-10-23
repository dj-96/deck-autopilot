# Evidence for the report

Everything here comes from real runs of the app on 2026-10-22 (model gpt-6-luna; Portkey was out of budget, so all calls went through the OpenAI fallback). Regenerate with the scripts named below.

| File | What it shows | Made by |
|---|---|---|
| `batch_runs.json` | 16 full runs (10 clean, 3 with a hidden prompt injection, 3 with a planted fake number): tokens by agent, cost, time, fact-check rounds, whether the injection leaked, which planted stories the deck found | `scripts/batch_runs.py` |
| `cost_model.md` / `.json` | Cost per run, per user per month, at 100 and 10,000 users; caching savings; comparison with a single prompt | `scripts/cost_model.py` |
| `baseline_single_prompt.json` | 5 decks from "paste both CSVs into one prompt" with every number checked, plus a hand review of the numbers the checker couldn't verify | `scripts/baseline_single_prompt.py` |
| `../screenshots/*.png` | App screenshots from saved real runs (`?replay=<id>`) | `scripts/capture_screenshots.py` |
| `../user_test/` | Real-user test script, kit, and timing sheet | `scripts/make_user_test_kit.py` |

## Headline numbers

**Cost (10 clean runs):** mean $0.0041 per deck (median $0.0040, p90 $0.0044); 26.5K input tokens of which 53% cached, 5.5K output tokens; 47.5 s. Typical user (20 runs/month): $0.08 per month; 100 users $8.23/month; 10,000 users $823/month in tokens.

**Safety (16 runs):**
- Prompt injection: quarantined in 3/3 poisoned runs; "500%", "admin mode", and "system prompt" appeared in 0 decks.
- Planted fake number: caught and fixed in 3/3 tamper runs (one extra draft, +$0.0007 per run).
- Clean runs: 10/10 passed the fact-check on the first draft; 0 unverified numbers shipped in any of the 16 runs.

**Quality (10 clean runs; stories planted in the sample data):** Northeast online Camping promo found 10/10, West store decline 10/10, Footwear returns 8/10.

**Single-prompt baseline (5 decks, 266 numbers):** 265 correct and 1 wrong ("Accessories added $18,988"; the truth is $8,988), so 1 in 5 decks contained a wrong number, and nothing in the output says which one. It costs $0.0020 per deck, about half the pipeline's, but its input grows with every row pasted.
