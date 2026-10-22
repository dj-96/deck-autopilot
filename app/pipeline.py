"""The whole run: Guard -> Analyst -> Storyliner <-> Fact-checker (max 2 fixes) -> usage log.

Used by both the command line and the web app.
"""
import time
from dataclasses import dataclass
from pathlib import Path

from app import config
from app.analyst import AnalystResult, run_analyst
from app.context import RunContext
from app.deck import Deck
from app.factcheck import CheckReport, check_deck, context_numbers_from
from app.guard import GuardedData, guard
from app.storyliner import StorylinerSession
from app.usage_log import check_daily_budget, log_run

# Used by --tamper to prove the checker works: a made-up number slipped into draft 1.
TAMPER_SENTENCE = " Customer satisfaction reached 93.7%."


@dataclass
class PipelineResult:
    data: GuardedData
    analyst: AnalystResult
    deck: Deck
    check: CheckReport
    check_rounds: list[dict]
    elapsed_s: float
    ctx: RunContext


def run_pipeline(prev_src: Path | bytes, prev_name: str, curr_src: Path | bytes, curr_name: str,
                 ctx: RunContext | None = None, tamper: bool = False) -> PipelineResult:
    ctx = ctx or RunContext()
    check_daily_budget()
    started = time.time()
    data = guard(prev_src, prev_name, curr_src, curr_name, ctx)
    analyst = run_analyst(data, ctx)

    text_cells = [str(v) for df in (data.prev, data.curr) for c in data.text_columns + data.dimensions
                  for v in df[c].dropna()]
    context = context_numbers_from(data.prev_label, data.curr_label, *text_cells)

    story = StorylinerSession(analyst.findings, analyst.facts, data.prev_label, data.curr_label, ctx)
    deck = story.draft()
    if tamper and deck.executive_summary:
        deck.executive_summary[0].text += TAMPER_SENTENCE
        ctx.log("pipeline", "tamper", f"Test mode: inserted a made-up number into draft 1:{TAMPER_SENTENCE}")

    rounds = []
    for attempt in range(config.MAX_FIX_ROUNDS + 1):
        report = check_deck(deck, analyst.facts, context)
        rounds.append({"draft": attempt + 1, **report.to_dict()})
        ctx.log("factchecker", "check",
                f"Draft {attempt + 1}: {report.verified}/{report.numbers_checked} numbers verified, "
                f"{len(report.auto_cited)} citation(s) added, {len(report.violations)} violation(s).")
        for v in report.violations:
            ctx.safety_event("factcheck", f"Draft {attempt + 1}, {v['where']}: \"{v['number']}\" — {v['reason']}",
                             text=v["text"])
        if report.passed or attempt == config.MAX_FIX_ROUNDS:
            break
        deck = story.fix(report.problems())

    if not report.passed:
        ctx.log("factchecker", "unresolved",
                f"{len(report.violations)} number(s) still unverified after {config.MAX_FIX_ROUNDS} fixes; "
                "they will be flagged on the slides.")

    elapsed = time.time() - started
    usage = ctx.meter.summary()
    log_run({"prev": prev_name, "curr": curr_name, "elapsed_s": round(elapsed, 2), "tamper": tamper,
             "slides": len(deck.slides), "facts": len(analyst.facts),
             "drafts": len(rounds), "verified": report.passed,
             "quarantined": len(data.quarantined), "usage": usage})
    return PipelineResult(data, analyst, deck, report, rounds, elapsed, ctx)
