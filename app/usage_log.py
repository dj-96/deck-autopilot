"""Append-only token log (one JSON line per run) and the daily spending cap built on it."""
import json
import time
from datetime import date

from app import config


class DailyBudgetExceeded(RuntimeError):
    pass


def spent_today() -> float:
    if not config.USAGE_LOG.is_file():
        return 0.0
    today = date.today().isoformat()
    total = 0.0
    for line in config.USAGE_LOG.read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if rec.get("date") == today:
            total += rec.get("usage", {}).get("cost_usd", 0.0)
    return total


def check_daily_budget() -> None:
    spent = spent_today()
    if spent >= config.DAILY_BUDGET_USD:
        raise DailyBudgetExceeded(
            f"Daily budget reached: ${spent:.4f} spent today, cap is ${config.DAILY_BUDGET_USD:.2f}. "
            "Try again tomorrow or raise DAILY_BUDGET_USD.")


def log_run(record: dict) -> None:
    config.USAGE_LOG.parent.mkdir(parents=True, exist_ok=True)
    record = {"date": date.today().isoformat(), "time": time.strftime("%H:%M:%S"), **record}
    with config.USAGE_LOG.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, default=str) + "\n")
