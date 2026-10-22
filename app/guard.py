"""Guard: plain-Python checks that run before any model sees the data.

1. Size caps: file bytes and row counts, so a huge upload can't burn the token budget.
2. Schema: both periods must share columns; numeric columns become metrics, text columns dimensions.
3. Prompt-injection scan: any text cell that reads like an instruction to the AI is quarantined
   (replaced by a placeholder) and logged. The model never sees the original text.
"""
import io
import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from app import config
from app.context import RunContext

QUARANTINE_TEXT = "[quarantined by guard: looked like an instruction to the AI]"
MAX_CELL_CHARS = 200
PERIOD_COLUMNS = ("month", "period", "date", "quarter", "week", "year")

# Phrases that address the AI rather than describe the business. Kept broad on purpose:
# a false positive only hides one note; a miss could steer the deck.
INJECTION_PATTERNS = [
    r"\bignore\b.{0,40}\b(instruction|prompt|rule|above|previous|prior)s?\b",
    r"\bdisregard\b.{0,40}\b(instruction|prompt|rule|above|previous|prior)s?\b",
    r"\bforget\b.{0,40}\b(instruction|prompt|rule|everything)s?\b",
    r"\b(system|developer)\s+(prompt|message|instruction)s?\b",
    r"\byou\s+are\s+now\b",
    r"\b(admin|developer|god|jailbreak|dan)\s+mode\b",
    r"\bact\s+as\b.{0,30}\b(ai|assistant|model|gpt|admin)\b",
    r"\b(reveal|print|show|repeat)\b.{0,30}\b(prompt|instructions|api\s*key|secret)s?\b",
    r"\b(report|say|state|claim|write)\s+that\b.{0,60}\b\d+\s*%",
    r"^\s*(assistant|system|user)\s*:",
    r"<\s*/?\s*(script|system|instructions?)\b",
    r"\bnew\s+instructions?\b",
]
_INJECTION_RE = re.compile("|".join(INJECTION_PATTERNS), re.IGNORECASE)


class GuardError(ValueError):
    """Upload rejected; message is safe to show the user."""


@dataclass
class GuardedData:
    prev: pd.DataFrame
    curr: pd.DataFrame
    prev_label: str
    curr_label: str
    dimensions: list[str]
    metrics: list[str]
    text_columns: list[str]
    quarantined: list[dict] = field(default_factory=list)


def looks_like_injection(text: str) -> bool:
    return bool(_INJECTION_RE.search(text))


def read_table(source: Path | bytes, filename: str) -> pd.DataFrame:
    """Read a CSV or Excel file from a path or uploaded bytes, enforcing the size caps."""
    raw = source.read_bytes() if isinstance(source, Path) else source
    if len(raw) > config.MAX_UPLOAD_BYTES:
        raise GuardError(f"{filename} is {len(raw) / 1e6:.1f} MB; the limit is "
                         f"{config.MAX_UPLOAD_BYTES / 1e6:.0f} MB.")
    suffix = Path(filename).suffix.lower()
    try:
        if suffix == ".csv":
            df = pd.read_csv(io.BytesIO(raw))
        elif suffix in (".xlsx", ".xlsm"):
            df = pd.read_excel(io.BytesIO(raw))
        else:
            raise GuardError(f"{filename}: upload a .csv or .xlsx file.")
    except GuardError:
        raise
    except Exception as err:  # noqa: BLE001 - parser errors vary by format
        raise GuardError(f"Couldn't read {filename}: {type(err).__name__}.") from err
    if df.empty:
        raise GuardError(f"{filename} has no rows.")
    if len(df) > config.MAX_ROWS:
        raise GuardError(f"{filename} has {len(df):,} rows; the limit is {config.MAX_ROWS:,}.")
    df.columns = [str(c).strip() for c in df.columns]
    return df


def _period_label(df: pd.DataFrame, fallback: str) -> tuple[str, str | None]:
    """Use a single-valued period column (e.g. month=2026-10) as the label if there is one."""
    for col in df.columns:
        if col.lower() in PERIOD_COLUMNS and df[col].nunique() == 1:
            return str(df[col].iloc[0]), col
    return fallback, None


def _scan_text(df: pd.DataFrame, cols: list[str], label: str, ctx: RunContext) -> list[dict]:
    hits = []
    for col in cols:
        for idx, value in df[col].items():
            if not isinstance(value, str) or not value.strip():
                continue
            if looks_like_injection(value):
                hits.append({"period": label, "row": int(idx) + 2, "column": col,  # +2: header + 1-based
                             "excerpt": value[:120]})
                df.at[idx, col] = QUARANTINE_TEXT
                ctx.safety_event("guard_injection",
                                 f"Quarantined {label} row {int(idx) + 2}, column '{col}': looked like an "
                                 f"instruction to the AI.", excerpt=value[:120])
            elif len(value) > MAX_CELL_CHARS:
                df.at[idx, col] = value[:MAX_CELL_CHARS] + "..."
    return hits


def guard(prev_src: Path | bytes, prev_name: str, curr_src: Path | bytes, curr_name: str,
          ctx: RunContext) -> GuardedData:
    prev = read_table(prev_src, prev_name)
    curr = read_table(curr_src, curr_name)

    prev_label, prev_pcol = _period_label(prev, Path(prev_name).stem)
    curr_label, curr_pcol = _period_label(curr, Path(curr_name).stem)
    if prev_label == curr_label:
        prev_label, curr_label = f"{prev_label} (previous)", f"{curr_label} (current)"
    if prev_pcol:
        prev = prev.drop(columns=[prev_pcol])
    if curr_pcol:
        curr = curr.drop(columns=[curr_pcol])

    missing = set(prev.columns) ^ set(curr.columns)
    if missing:
        raise GuardError(f"The two files need the same columns. Only in one file: {', '.join(sorted(missing))}.")

    metrics = [c for c in curr.columns
               if pd.api.types.is_numeric_dtype(curr[c]) and pd.api.types.is_numeric_dtype(prev[c])]
    if not metrics:
        raise GuardError("No numeric columns found to analyze.")
    others = [c for c in curr.columns if c not in metrics]
    # Short repeated labels (region, channel) are dimensions; long free text (notes) is not.
    dimensions, text_columns = [], []
    for c in others:
        values = pd.concat([prev[c], curr[c]]).dropna().astype(str)
        is_dim = values.str.len().max() <= 40 and values.nunique() <= max(50, len(values) // 2)
        (dimensions if is_dim else text_columns).append(c)

    quarantined = (_scan_text(prev, others, prev_label, ctx) + _scan_text(curr, others, curr_label, ctx))
    ctx.log("guard", "done",
            f"Checked {len(prev)} + {len(curr)} rows; {len(metrics)} metrics, {len(dimensions)} dimensions; "
            f"{len(quarantined)} cell(s) quarantined.")
    return GuardedData(prev, curr, prev_label, curr_label, dimensions, metrics, text_columns, quarantined)
