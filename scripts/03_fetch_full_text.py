#!/usr/bin/env python3
"""Stage 3: fetch full text. Stages 3-7 are coupled via per-record caches, so
this delegates to the integrated runner with fetch enabled (cache is reused).

    python scripts/03_fetch_full_text.py --input data/input/droso_data_use.xlsx --max-records 25
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from droso_audit.run_all import main as run_main  # noqa: E402

if __name__ == "__main__":
    # Forward all flags; the runner fetches+caches full text as part of the run.
    raise SystemExit(run_main())
