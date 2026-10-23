# Real-user test: script (about 25 minutes)

**Goal:** measure how long a recurring deck refresh takes today versus with Deck Autopilot, how many numbers go wrong each way, and whether a real consultant would trust and use the result. This is the evidence for report section 7 (Impact) and Tier 3.

**Who:** someone who has refreshed a recurring client or management deck: a former consulting colleague is ideal; an analyst, banker, or ops manager also works. One person is enough; two is better.

**Kit** (`docs/user_test/kit/`):

| File | Use |
|---|---|
| `northwind_september_deck.pptx` | "Last month's deck" (built by the app from Aug → Sep data) |
| `northwind_2026_10.csv` | This month's data |
| `answer_key.csv` | Correct October numbers, for scoring Task A |
| `timing_sheet.xlsx` | Fill in as you go; the Summary tab computes the before/after |

**Before the session:** have the app running (`python -m app.main`), the kit files on the participant's desktop, a clock with seconds, and `timing_sheet.xlsx` open on your side. Ask permission to time them, take notes, and quote them (record the answer on tab 1).

---

## 1. Warm-up (2 min) → tab 1

- What's your role, and how often did you refresh recurring decks?
- Roughly how long does one refresh take you, start to finish? *(write their estimate; it's a second data point)*

## 2. Task A: the way it's done today (15 min timebox) → tab 2

Say: *"Here's last month's deck for a client and this month's data. Please update the deck for October, the way you normally would. Update the numbers, and change a title if the story changed. Go slide by slide; I'll stop you at 15 minutes."*

- They may use Excel and PowerPoint, but not the app.
- Log the clock time when each slide starts and ends. Count the numbers they change per slide.
- Afterwards, check each number they wrote against `answer_key.csv` and log the wrong ones.
- Stop at 15 minutes even mid-slide (log only finished slides). The sheet projects the full-deck time from minutes per slide.

## 3. Task B: with Deck Autopilot (5–8 min) → tab 3

Say only: *"Now do the same job with this app."* Don't explain the screen. If they're stuck for more than 60 seconds, give one hint and record it.

- Log the clock time at each step on tab 3 (start, data chosen, Refresh clicked, deck ready, done reviewing, downloaded).
- "Done reviewing" is their call: when they'd be comfortable sending it to their manager.
- Note whether they click a bullet to see its facts, and whether they find any number they believe is wrong.

## 4. Ratings and quotes (5 min) → tab 4

Read each statement and get a 1–5 rating plus "why". Then ask:

- What would stop you from using this?
- What's missing?
- Would you or your firm pay for this? How much?

Write the best quote **word for word**.

## 5. After the session

- Open tab 5 (Summary) for the before/after numbers.
- Take one photo or screenshot during the session (with permission) for the report.
- Save the filled sheet as `docs/user_test/results_<initials>.xlsx`. Commit it only if they agreed to be named; otherwise keep it local and report initials.

## Caveats to state honestly in the report

- Order effect: they do the manual task first, so they know the data when they reach the app. That favors the manual time on any repeat, so the measured saving is if anything understated for the app.
- Synthetic client: the data is fictional, so the test measures the workflow, not domain judgment about a real client.
- n = 1 or 2: the result is a case study, not a statistic.
