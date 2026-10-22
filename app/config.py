"""Paths, model, prices, and the limits that keep a run cheap and bounded."""
import os
from pathlib import Path

from dotenv import load_dotenv

REPO_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_DIR / "data"
SAMPLE_DIR = DATA_DIR / "sample"
OUTPUT_DIR = REPO_DIR / "output"

# Look for .env in the repo folder first, then one folder up (where the teaching
# staff keep theirs). load_dotenv never overrides a name that is already set,
# so the repo's own .env wins if both define the same key.
ENV_FILES = [REPO_DIR / ".env", REPO_DIR.parent / ".env"]
for env_file in ENV_FILES:
    if env_file.is_file():
        load_dotenv(env_file)

# --- Model -----------------------------------------------------------------
# The course key only allows gpt-6-luna; the OpenAI fallback uses the same model
# so results and costs stay comparable.
MODEL_NAME = "gpt-6-luna"
PORTKEY_BASE_URL = "https://api.portkey.ai/v1"

# USD per 1M tokens (OpenAI standard pricing, MGT 409 Lecture 11).
PRICES = {"input": 0.10, "cached_input": 0.01, "output": 0.50}

# --- Limits ----------------------------------------------------------------
MAX_TOKENS_PER_RUN = 120_000  # hard stop across every agent call in one run
MAX_OUTPUT_TOKENS_PER_CALL = 6_000
REQUEST_TIMEOUT_S = 90
MAX_UPLOAD_BYTES = 2_000_000  # per file
MAX_ROWS = 5_000  # per file


def env(name: str) -> str | None:
    value = os.getenv(name, "").strip()
    return value or None
