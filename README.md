# Deck Autopilot

Upload last period's and this period's business data, and get back a refreshed consulting deck: action titles, charts, and a "what changed" list. Every number on every slide is checked against the data before you see it.

> Status: work in progress (MGT 409 final project). The web app is not built yet.

## Run it locally

You need Python 3.11+ and one API key.

1. **Get the code**
   ```bash
   git clone <repo-url> deck-autopilot
   cd deck-autopilot
   ```
2. **Add your key.** Put a `.env` file in this folder or in the folder above it (see `.env.example`). The app needs `PORTKEY_API_KEY` or `OPENAI_API_KEY`. It tries Portkey first and switches to OpenAI automatically if Portkey is missing or out of budget.
3. **Create a virtual environment and install packages**
   ```bash
   python -m venv .venv
   ```
   Windows: `.venv\Scripts\activate` · macOS/Linux: `source .venv/bin/activate`
   ```bash
   pip install -r requirements.txt
   ```
4. **Check the key works**
   ```bash
   python scripts/check_llm.py
   ```
   You should see `answer via portkey` (or `via openai`) and a token count.

## Sample data

`data/sample/` holds a fictional client, Northwind Outdoor Co. (32 rows per month: region x category x channel):

| File | What it is |
|---|---|
| `northwind_2026_09.csv` | September (the "last month" deck) |
| `northwind_2026_10.csv` | October (the "this month" refresh) |
| `northwind_2026_10_poisoned.csv` | October with a prompt injection hidden in a notes cell, for the safety demo |

Regenerate them with `python scripts/make_sample_data.py` (fixed seed, same output every time).

## Model and cost

All agents use `gpt-6-luna`. Prices used for cost reporting: $0.10 / 1M input, $0.01 / 1M cached input, $0.50 / 1M output tokens.
