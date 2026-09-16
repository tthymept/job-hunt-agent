"""
run_daily_fetch.py
-------------------
One-shot script: run once, do the daily fetch + enrichment, exit.
Intended to be triggered by an external scheduler (Windows Task Scheduler /
Railway Cron / GitHub Actions) - this script itself does not loop or wait.
"""

import os
import sys
import psycopg2
from pathlib import Path
from dotenv import load_dotenv
from jobs_manager import run_daily_fetch

load_dotenv(dotenv_path=Path(__file__).parent / ".env")

DATABASE_URL = os.environ["DATABASE_URL"]

if __name__ == "__main__":
    conn = psycopg2.connect(DATABASE_URL)
    try:
        run_daily_fetch(conn)
        print("Daily fetch completed successfully.")
    except Exception as e:
        print(f"Daily fetch failed: {e}")
        sys.exit(1)  # non-zero exit code so the scheduler knows it failed
    finally:
        conn.close()