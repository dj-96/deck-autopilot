"""Web app: FastAPI backend + one static page.

    python -m app.main          # then open http://127.0.0.1:8000

POST /api/run starts a background job; the page polls GET /api/jobs/{id} for the live
agent trace, then shows the checked deck and offers the .pptx download.
"""
import json
import os
import re
import threading
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from app import config
from app.analyst import AnalystFailed
from app.context import RunContext
from app.guard import GuardError
from app.llm import BudgetExceeded, NoGatewayAvailable, gateway_status
from app.pipeline import run_pipeline
from app.render_pptx import chart_values, render_pptx
from app.usage_log import DailyBudgetExceeded, spent_today

STATIC = Path(__file__).parent / "static"
MAX_ACTIVE_JOBS = 2  # concurrent runs; more get "busy" instead of piling up spend
MAX_KEPT_JOBS = 20

app = FastAPI(title="Deck Autopilot")
app.mount("/static", StaticFiles(directory=STATIC), name="static")
jobs: dict[str, dict] = {}
jobs_lock = threading.Lock()

USER_ERRORS = {  # exception -> shown to the user as-is (messages are written to be safe)
    GuardError: "upload",
    DailyBudgetExceeded: "budget",
    BudgetExceeded: "budget",
    NoGatewayAvailable: "model",
    AnalystFailed: "agent",
}


def _payload(r, ctx: RunContext) -> dict:
    facts = r.analyst.facts
    return {
        "periods": {"previous": r.data.prev_label, "current": r.data.curr_label},
        "deck": r.deck.model_dump(),
        "charts": chart_values(r.deck, facts),
        "facts": {f.id: {"display": f.display, "label": f.label, "unit": f.unit, "source": f.source, "value": f.value}
                  for f in facts.facts.values()},
        "findings": r.analyst.findings,
        "check": r.check.to_dict(),
        "check_rounds": r.check_rounds,
        "quarantined": r.data.quarantined,
        "safety": ctx.safety,
        "usage": ctx.meter.summary(),
        "elapsed_s": round(r.elapsed_s, 1),
        "stats": {"facts": len(facts), "tool_calls": r.analyst.tool_calls, "rows": len(r.data.curr),
                  "metrics": r.data.metrics, "dimensions": r.data.dimensions},
    }


def _worker(job_id: str, prev: tuple, curr: tuple, tamper: bool) -> None:
    job = jobs[job_id]
    ctx: RunContext = job["ctx"]
    job["status"] = "running"
    try:
        r = run_pipeline(prev[0], prev[1], curr[0], curr[1], ctx=ctx, tamper=tamper)
        pptx = render_pptx(r.deck, r.analyst.facts, r.check)
        ctx.log("renderer", "done", f"Built {len(r.deck.slides) + 2}-slide .pptx with "
                                    f"{sum(1 for s in r.deck.slides if s.chart)} native chart(s).")
        job["pptx"] = pptx
        job["result"] = _payload(r, ctx)
        job["status"] = "done"
        _save_run(job_id, job["result"], ctx)
    except Exception as err:  # noqa: BLE001 - every failure must reach the page as a clean message
        kind = next((k for t, k in USER_ERRORS.items() if isinstance(err, t)), None)
        job["error"] = {"kind": kind or "internal",
                        "message": str(err) if kind else f"Something went wrong ({type(err).__name__}). "
                                                          "Try again, or check the server log."}
        ctx.log("pipeline", "error", job["error"]["message"])
        job["status"] = "error"
    finally:
        job["finished"] = time.time()


def _save_run(job_id: str, result: dict, ctx: RunContext) -> None:
    out = config.OUTPUT_DIR / "runs"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{time.strftime('%Y%m%d_%H%M%S')}_web_{job_id}.json").write_text(
        json.dumps(result | {"trace": ctx.trace}, indent=2, default=str), encoding="utf-8")


async def _read_upload(f: UploadFile | None, label: str) -> tuple[bytes, str]:
    if f is None or not f.filename:
        raise HTTPException(400, f"Add the {label} file, or use the sample data.")
    raw = await f.read(config.MAX_UPLOAD_BYTES + 1)
    if len(raw) > config.MAX_UPLOAD_BYTES:
        raise HTTPException(413, f"{f.filename} is over {config.MAX_UPLOAD_BYTES // 1_000_000} MB.")
    return raw, Path(f.filename).name


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/status")
def status() -> dict:
    g = gateway_status()
    return {"model": config.MODEL_NAME, "keys_present": g["keys_present"], "gateway_order": g["order"],
            "gateways_disabled": list(g["disabled"]), "spent_today_usd": round(spent_today(), 5),
            "daily_budget_usd": config.DAILY_BUDGET_USD, "max_tokens_per_run": config.MAX_TOKENS_PER_RUN}


@app.get("/api/usage")
def usage_history() -> dict:
    rows = []
    if config.USAGE_LOG.is_file():
        for line in config.USAGE_LOG.read_text(encoding="utf-8").splitlines()[-25:]:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return {"runs": rows[::-1]}


@app.post("/api/run")
async def start_run(mode: str = Form("sample"), tamper: bool = Form(False),
                    prev: UploadFile | None = File(None), curr: UploadFile | None = File(None)) -> dict:
    with jobs_lock:
        active = sum(1 for j in jobs.values() if j["status"] in ("queued", "running"))
        if active >= MAX_ACTIVE_JOBS:
            raise HTTPException(429, "Two decks are already being built. Try again in a minute.")
    if mode in ("sample", "poisoned"):
        prev_t = (config.SAMPLE_DIR / "northwind_2026_09.csv", "northwind_2026_09.csv")
        name = "northwind_2026_10_poisoned.csv" if mode == "poisoned" else "northwind_2026_10.csv"
        curr_t = (config.SAMPLE_DIR / name, name)
    elif mode == "upload":
        prev_t = await _read_upload(prev, "previous-period")
        curr_t = await _read_upload(curr, "current-period")
    else:
        raise HTTPException(400, "Unknown mode.")

    job_id = uuid.uuid4().hex[:10]
    with jobs_lock:
        for old in sorted(jobs, key=lambda k: jobs[k]["created"])[:-MAX_KEPT_JOBS]:
            if jobs[old]["status"] in ("done", "error"):
                jobs.pop(old)
        jobs[job_id] = {"status": "queued", "ctx": RunContext(), "created": time.time(),
                        "inputs": {"prev": prev_t[1], "curr": curr_t[1], "tamper": tamper}}
    threading.Thread(target=_worker, args=(job_id, prev_t, curr_t, tamper), daemon=True).start()
    return {"job_id": job_id}


@app.get("/api/jobs/{job_id}")
def job_status(job_id: str) -> JSONResponse:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "Run not found (the server may have restarted).")
    ctx: RunContext = job["ctx"]
    return JSONResponse({
        "status": job["status"], "inputs": job["inputs"],
        "elapsed_s": round((job.get("finished") or time.time()) - job["created"], 1),
        "trace": [{k: v for k, v in e.items() if k != "result"} for e in ctx.trace],
        "usage": ctx.meter.summary(),
        "result": job.get("result"), "error": job.get("error"),
    })


@app.get("/api/replay/{name}")
def replay(name: str) -> JSONResponse:
    """A saved web run (output/runs/*_web_<id>.json), shown read-only with ?replay=<id>. Used for screenshots."""
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", name):
        raise HTTPException(400, "Bad replay name.")
    matches = sorted((config.OUTPUT_DIR / "runs").glob(f"*_web_{name}.json"))
    if not matches:
        raise HTTPException(404, "No saved run with that id.")
    saved = json.loads(matches[-1].read_text(encoding="utf-8"))
    trace = saved.pop("trace", [])
    return JSONResponse({"status": "done", "trace": trace, "usage": saved["usage"],
                         "elapsed_s": saved["elapsed_s"], "result": saved, "error": None})


@app.get("/api/jobs/{job_id}/deck.pptx")
def download(job_id: str) -> Response:
    job = jobs.get(job_id)
    if job is None or "pptx" not in job:
        raise HTTPException(404, "Deck not ready.")
    name = f"deck_{job['result']['periods']['current']}.pptx".replace(" ", "_")
    return Response(job["pptx"], headers={"Content-Disposition": f'attachment; filename="{name}"'},
                    media_type="application/vnd.openxmlformats-officedocument.presentationml.presentation")


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8000"))
    print(f"\n  Deck Autopilot running at http://127.0.0.1:{port}\n")
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")
