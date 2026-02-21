"""
fxlens/scheduler.py
====================
Keeps the database fresh by running fetch_data.py on a schedule.

Usage:
    python scheduler.py          # runs forever, fetches every 6 hours

Or use cron instead (recommended for production):
    0 */6 * * * cd /path/to/fxlens && python fetch_data.py >> logs/fetch.log 2>&1

Or use GitHub Actions (free, runs in the cloud):
    See .github/workflows/fetch.yml
"""

import time
import subprocess
import os
import datetime

FETCH_INTERVAL_HOURS = 6  # how often to refresh
LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")


def run_fetch():
    os.makedirs(LOG_DIR, exist_ok=True)
    log_file = os.path.join(LOG_DIR, f"fetch_{datetime.date.today()}.log")

    print(f"\n[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}] Running fetch...")

    result = subprocess.run(
        ["python3", os.path.join(os.path.dirname(__file__), "fetch_data.py")],
        capture_output=True,
        text=True,
    )

    with open(log_file, "a") as f:
        f.write(f"\n--- {datetime.datetime.now().isoformat()} ---\n")
        f.write(result.stdout)
        if result.stderr:
            f.write("STDERR:\n" + result.stderr)

    if result.returncode == 0:
        print("  ✓ Fetch complete")
    else:
        print(f"  ✗ Fetch FAILED (see {log_file})")


if __name__ == "__main__":
    print(f"fxlens scheduler — fetching every {FETCH_INTERVAL_HOURS} hours")
    print("Press Ctrl+C to stop\n")

    run_fetch()  # run immediately on start

    while True:
        sleep_seconds = FETCH_INTERVAL_HOURS * 3600
        next_run = datetime.datetime.now() + datetime.timedelta(hours=FETCH_INTERVAL_HOURS)
        print(f"  Next fetch: {next_run.strftime('%Y-%m-%d %H:%M')}")
        time.sleep(sleep_seconds)
        run_fetch()
