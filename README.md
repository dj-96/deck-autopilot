# Deck Autopilot

Upload last period's and this period's business data, and get back a refreshed consulting deck: action titles, charts, and a "what changed" list. Every number on every slide is checked against the data before you see it. Download it as an editable PowerPoint.

## Run it locally (about 3 minutes)

You need Python 3.11+ and one API key.

1. **Get the code**
   ```bash
   git clone <repo-url> deck-autopilot
   cd deck-autopilot
   ```
2. **Add your key.** Put a `.env` file in this folder **or in the folder above it** (see `.env.example`). The app needs `PORTKEY_API_KEY` or `OPENAI_API_KEY`. It tries Portkey first and switches to OpenAI automatically if Portkey is missing or out of budget.
3. **Create a virtual environment and install packages**
   ```bash
   python -m venv .venv
   ```
   Windows: `.venv\Scripts\activate` · macOS/Linux: `source .venv/bin/activate`
   ```bash
   pip install -r requirements.txt
   ```
4. **Start the app**
   ```bash
   python -m app.main
   ```
   Open **http://127.0.0.1:8000** in your browser.
5. **Use it:** click **Use sample client**, then **Refresh my deck**. In about a minute you get the slide preview, the fact-check badges, and a **Download .pptx** button. To see the safety defenses fire, open **Safety demos** before you click Refresh and tick one or both boxes, then check the **Safety log** tab.

To use your own data, drop two CSV or Excel files (same columns, one per period) into **Last period** and **This period**. Numeric columns are treated as metrics; short text columns (region, product, channel) as dimensions; long text (notes) as context.

Port 8000 busy? Run `PORT=8010 python -m app.main` (Windows PowerShell: `$env:PORT=8010; python -m app.main`).

## How it works

```
Upload → Guard → Analyst agent → Storyliner agent ⇄ Fact-checker → Renderer → web preview + .pptx
         (code)   (LLM + tools)   (LLM)             (code, ≤2 fixes)  (code)
```

- **Guard** (Python): file size, row, and type limits; both files must share columns; any text cell that reads like an instruction to the AI is quarantined before a model sees it.
- **Analyst agent** (gpt-6-luna with 7 Python tools): compares totals, breaks changes down by dimensions, computes ratios. The model never does arithmetic; every number it can use is a *fact* with an ID (F1, F2, …).
- **Storyliner agent** (gpt-6-luna, structured output): writes action titles, bullets, and chart specs that cite fact IDs. Charts hold only fact IDs, so they can't show a number the data doesn't contain.
- **Fact-checker** (Python): extracts every number on every slide and matches it to the cited facts at the precision written. Mismatches go back to the Storyliner (up to 2 rounds); anything still wrong is flagged in red.
- **Renderer** (Python): editable .pptx with native charts; speaker notes list the facts behind each slide.

Spending limits: 120K tokens per run, 10 Analyst turns / 30 tool calls, 2 concurrent runs, and a daily cap (`DAILY_BUDGET_USD`, default $1.00) checked before every run. Every run's token usage is logged to `output/usage_log.jsonl` and shown on the **Usage** tab.

## Command-line tools

| Command | What it does |
|---|---|
| `python scripts/check_llm.py` | Confirms a key is found and the model answers |
| `python scripts/run_pipeline.py` | Full run on the sample data; prints the checked deck and token use by agent |
| `python scripts/run_pipeline.py --poisoned` | Same, with a prompt injection hidden in the October notes |
| `python scripts/run_pipeline.py --tamper` | Plants a made-up number in the first draft to show the fact-checker rejecting it |
| `python scripts/run_pipeline.py --prev a.csv --curr b.xlsx` | Your own files |
| `python -m pytest -q` | Offline tests (no key needed) |

## Sample data

`data/sample/` holds a fictional client, Northwind Outdoor Co. (32 rows per month: region × category × channel):

| File | What it is |
|---|---|
| `northwind_2026_09.csv` | September (the "last month" deck) |
| `northwind_2026_10.csv` | October (the "this month" refresh) |
| `northwind_2026_10_poisoned.csv` | October with a prompt injection hidden in a notes cell, for the safety demo |

Regenerate them with `python scripts/make_sample_data.py` (fixed seed, same output every time).

## Model and cost

All agents use `gpt-6-luna`. Prices used for cost reporting: $0.10 / 1M input, $0.01 / 1M cached input, $0.50 / 1M output tokens. A typical sample run uses about 30K input tokens (about half cached) and 5–7K output tokens: about **$0.004–0.005 per deck**.
