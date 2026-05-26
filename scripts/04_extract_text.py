#!/usr/bin/env python3
"""Stage wrapper. Stages 3-7 are coupled via per-record caches; this delegates
to the integrated runner (`python -m droso_audit.run_all`), which performs
text extraction, resource detection, classification, and output writing in one
resumable pass. Pass the same flags you would give run_all."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from droso_audit.run_all import main as run_main  # noqa: E402

if __name__ == "__main__":
    raise SystemExit(run_main())
