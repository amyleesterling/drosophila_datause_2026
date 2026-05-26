#!/usr/bin/env python3
"""Stage 1: load the input spreadsheet (local file or Google Sheet) and normalize."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from droso_audit import config  # noqa: E402
from droso_audit.io import load_input  # noqa: E402
from droso_audit.run_all import normalize_df  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--input")
    ap.add_argument("--google-sheet-url")
    args = ap.parse_args()

    config.ensure_dirs()
    df = load_input(input_path=args.input, google_sheet_url=args.google_sheet_url)
    print(f"Loaded {len(df)} rows. Columns: {list(df.columns)}")
    norm = normalize_df(df)
    print(f"{len(norm)} rows after dedupe.")
    try:
        norm.to_parquet(config.NORMALIZED_PARQUET)
        print(f"Wrote {config.NORMALIZED_PARQUET}")
    except Exception as e:
        out = config.CACHE_DIR / "normalized_records.csv"
        norm.to_csv(out, index=False)
        print(f"(parquet unavailable: {e}) Wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
