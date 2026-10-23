"""Capture report screenshots of the running app with headless Edge/Chrome, from saved runs (?replay=).

    python -m app.main                      # in another terminal (or set --base)
    python scripts/capture_screenshots.py --clean 725179b32f --demo d8d0094aec

Writes PNGs to docs/screenshots/.
"""
import argparse
import shutil
import subprocess
import tempfile
import time
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config  # noqa: E402

OUT = config.REPO_DIR / "docs" / "screenshots"
BROWSERS = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            r"C:\Program Files\Google\Chrome\Application\chrome.exe",
            "msedge", "google-chrome", "chromium", "chrome"]


def browser() -> str:
    for b in BROWSERS:
        if Path(b).is_file() or shutil.which(b):
            return b
    sys.exit("No Edge or Chrome found.")


def shot(exe: str, url: str, path: Path, size: str) -> None:
    # One throwaway profile per shot: with a shared profile, Edge hands later calls to the
    # still-running first instance and those screenshots are silently dropped.
    profile = Path(tempfile.mkdtemp(prefix="da_shot_"))
    path.unlink(missing_ok=True)
    try:
        subprocess.run([exe, "--headless=new", "--disable-gpu", "--hide-scrollbars", "--force-device-scale-factor=1",
                        "--no-first-run", f"--user-data-dir={profile}", f"--window-size={size}",
                        "--virtual-time-budget=6000", f"--screenshot={path}", url],
                       check=True, capture_output=True, timeout=60)
        for _ in range(40):  # the file can land a moment after the process exits
            if path.is_file() and path.stat().st_size:
                break
            time.sleep(0.25)
        else:
            raise RuntimeError(f"No screenshot written for {url}")
    finally:
        shutil.rmtree(profile, ignore_errors=True)
    print(f"  {path.name}  <- {url}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("--clean", required=True, help="job id of a saved clean web run")
    ap.add_argument("--demo", required=True, help="job id of a saved poisoned+tamper web run")
    ap.add_argument("--only", help="capture just this screenshot name")
    args = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    b, c, d = args.base, args.clean, args.demo
    plan = {
        "01_start_screen": (f"{b}/", "1440,900"),
        "01b_agents_running": (f"{b}/?replay={c}&upto=14", "1440,900"),
        "02_result_summary": (f"{b}/?replay={c}&slide=1", "1440,1000"),
        "03_result_chart_slide": (f"{b}/?replay={c}&slide=3", "1440,1000"),
        "04_fact_trace": (f"{b}/?replay={c}&slide=1&open=facts&bullet=0", "1440,1250"),
        "05_what_changed": (f"{b}/?replay={c}&slide=0&open=changes", "1440,1400"),
        "06_demo_badges": (f"{b}/?replay={d}&slide=1&demo=poisoned,tamper", "1440,1000"),
        "07_safety_log": (f"{b}/?replay={d}&tab=safety", "1440,900"),
        "08_usage": (f"{b}/?replay={d}&tab=usage", "1440,900"),
    }
    exe = browser()
    for name, (url, size) in plan.items():
        if args.only and name != args.only:
            continue
        shot(exe, url, OUT / f"{name}.png", size)


if __name__ == "__main__":
    main()
