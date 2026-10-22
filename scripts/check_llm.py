"""Smoke test: confirm a key is found and the model answers. Run from the repo folder:

    python scripts/check_llm.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.llm import UsageMeter, call_model, gateway_status  # noqa: E402

status = gateway_status()
print("env files found:", status["env_files_found"] or "none")
print("keys present:   ", status["keys_present"])
print("gateway order:  ", status["order"])

meter = UsageMeter()
try:
    resp, gateway = call_model("smoke_test", meter, input="Reply with exactly: key works")
except Exception as err:  # noqa: BLE001
    sys.exit(f"FAILED: {err}")

s = meter.summary()
print(f"answer via {gateway}: {resp.output_text!r}")
print(f"tokens: {s['input_tokens']} in ({s['cached_tokens']} cached) / {s['output_tokens']} out, "
      f"cost ${s['cost_usd']:.6f}")
if gateway_status()["disabled"]:
    print("fell back because:", gateway_status()["disabled"])
