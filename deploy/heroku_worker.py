#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
===============================================================================
ANTItrading Heroku Background Worker Daemon
===============================================================================
Runs 24/7 on a Heroku Eco/Basic Dyno.
Executes the trading pass every hour at the scheduled minute (default: minute 15),
syncs portfolio state to GitHub, and dispatches real-time Discord notifications.
===============================================================================
"""

import os
import sys
import time
import subprocess
import datetime

# Ensure repository root is on sys.path
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

TARGET_MINUTE = int(os.environ.get("SCHEDULE_MINUTE", "15"))


def run_pass() -> int:
    """Executes the heroku_run.sh script and returns the exit code."""
    now_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print(f"\n[{now_str}] 🚀 Triggering scheduled trading pass...")
    sys.stdout.flush()

    script_path = os.path.join(ROOT_DIR, "deploy", "heroku_run.sh")
    result = subprocess.run(["bash", script_path], cwd=ROOT_DIR)
    print(f"[{now_str}] 🏁 Pass exited with code: {result.returncode}")
    sys.stdout.flush()
    return result.returncode


def seconds_until_next_target_minute(target_min: int) -> int:
    """Calculates seconds remaining until the next occurrence of the target minute."""
    now = datetime.datetime.now(datetime.timezone.utc)
    target = now.replace(minute=target_min, second=0, microsecond=0)
    if target <= now:
        target += datetime.timedelta(hours=1)
    return max(1, int((target - now).total_seconds()))


def main() -> None:
    """Main daemon loop."""
    print("=================================================================")
    print("🚀 ANTItrading Heroku Background Worker Daemon Started")
    print(f"⏰ Target Schedule: Minute :{TARGET_MINUTE:02d} of every hour (UTC)")
    print(f"📁 Root Directory: {ROOT_DIR}")
    print("=================================================================")
    sys.stdout.flush()

    # Execute pass once on worker startup
    print("⚡ Running initial trading pass on startup...")
    run_pass()

    # Loop indefinitely
    while True:
        wait_seconds = seconds_until_next_target_minute(TARGET_MINUTE)
        next_run_time = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(seconds=wait_seconds)
        print(f"⏳ Sleeping for {wait_seconds}s (~{wait_seconds // 60}m). Next run at: {next_run_time.strftime('%Y-%m-%d %H:%M:%S UTC')}")
        sys.stdout.flush()

        time.sleep(wait_seconds)

        try:
            run_pass()
        except Exception as err:
            print(f"❌ Error during trading pass execution: {err}")
            sys.stdout.flush()


if __name__ == "__main__":
    main()
