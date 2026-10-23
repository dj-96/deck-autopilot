# Cost model (from 10 measured clean runs on the sample data)

Prices: $0.1/1M input, $0.01/1M cached input, $0.5/1M output (gpt-6-luna).

## One run

| | mean | median | p90 | min | max |
|---|---|---|---|---|---|
| Input tokens | 26,526 | 26,906 | 29,876 | 21,373 | 35,239 |
| of which cached | 14,054 | 14,888 | 16,855 | 8,943 | 22,183 |
| Output tokens | 5,459 | 5,246 | 5,897 | 4,463 | 7,968 |
| Model calls | 6.7 | 7.0 | 7.0 | 6.0 | 8.0 |
| Tool calls | 22.4 | 22.0 | 23.0 | 21.0 | 24.0 |
| Seconds | 47.5 | 45.9 | 50.5 | 37.8 | 69.2 |
| Cost (USD) | $0.0041 | $0.0040 | $0.0044 | $0.0035 | $0.0054 |

By agent (mean per run):

| Agent | Calls | Input | Cached | Output | Cost |
|---|---|---|---|---|---|
| analyst | 5.7 | 19,612 | 13,016 | 2,038 | $0.0018 |
| storyliner | 1.0 | 6,914 | 1,038 | 3,420 | $0.0023 |

- A run that needs one fact-check fix round costs $0.0048 on average (tamper runs).
- Prompt caching: 53% of input tokens were cache hits. Without caching the same runs would cost $0.0054 (caching saves 23%).

## Per user and at scale (token cost only)

| Usage profile | Runs / user / month | Per user / month | 100 users / month | 10,000 users / month |
|---|---|---|---|---|
| light | 5 | $0.021 | $2.06 | $206 |
| typical | 20 | $0.082 | $8.23 | $823 |
| heavy | 60 | $0.247 | $24.70 | $2,470 |

Hosting estimate: ~$25/month at 100 users, ~$400/month at 10,000 users.
At 10,000 typical users that is ~9,524 runs per workday; the default $1.00 daily cap covers ~243 runs, so at scale the cap becomes per user rather than global.

## Versus pasting the data into one prompt

Single prompt (same model, both CSVs pasted): $0.0020 per deck, 2,730 input tokens (~43 tokens per CSV row). The pipeline costs $0.0041: about 2.1x more on this small sample, for verification and traceability.

| Rows per file | Single-prompt input tokens | Single-prompt cost / deck | Pipeline |
|---|---|---|---|
| 32 | 2,730 | $0.0022 | ~$0.0041 (bounded by tool caps; not measured) |
| 500 | 42,656 | $0.0062 | ~$0.0041 (bounded by tool caps; not measured) |
| 5,000 | 426,562 | $0.0446 | ~$0.0041 (bounded by tool caps; not measured) |

Rows above 32 are extrapolated from tokens per row, not measured. 5,000 rows per file would also exceed what fits comfortably in one prompt. Pipeline cost at large row counts is bounded by its tool caps but has not been measured.