#!/usr/bin/env python3
"""Stage 8: (re)build summary_counts.json/.md from an existing audit output."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pandas as pd  # noqa: E402

from droso_audit.summarize import write_summary  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--audit-csv", default="outputs/droso_data_use_audit.csv")
    args = ap.parse_args()
    p = Path(args.audit_csv)
    if not p.exists():
        print(f"Audit file not found: {p}. Run the pipeline first.", file=sys.stderr)
        return 1
    df = pd.read_csv(p)
    df.attrs["input_count"] = len(df)
    summary = write_summary(df)
    print("Wrote outputs/summary_counts.json and outputs/summary_counts.md")
    print(summary["estimates"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
