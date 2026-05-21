#!/usr/bin/env python3
"""Stage 2: metadata enrichment, with optional citation expansion from seeds."""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import pandas as pd  # noqa: E402

from droso_audit import config  # noqa: E402
from droso_audit.citation_expansion import expand_from_seeds  # noqa: E402
from droso_audit.metadata import enrich_record  # noqa: E402


def _load_normalized() -> pd.DataFrame:
    if config.NORMALIZED_PARQUET.exists():
        return pd.read_parquet(config.NORMALIZED_PARQUET)
    csv = config.CACHE_DIR / "normalized_records.csv"
    if csv.exists():
        return pd.read_csv(csv)
    raise FileNotFoundError("Run scripts/01_load_sheet.py first.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--expand-citations-from-seeds", action="store_true")
    ap.add_argument("--max-records", type=int, default=0)
    args = ap.parse_args()
    config.ensure_dirs()

    if args.expand_citations_from_seeds:
        rows = expand_from_seeds()
        out = config.CACHE_DIR / "citing_works.csv"
        pd.DataFrame(rows).to_csv(out, index=False)
        print(f"Citation expansion found {len(rows)} unique citing works -> {out}")

    df = _load_normalized()
    if args.max_records:
        df = df.head(args.max_records).copy()

    enriched = []
    for _, row in df.iterrows():
        meta = enrich_record(
            doi=row.get("doi_normalized"), title=row.get("title") or row.get("normalized_title"),
            pmid=row.get("pmid"), pmcid=row.get("pmcid"),
        )
        meta["doi_normalized"] = row.get("doi_normalized")
        enriched.append(meta)
    ed = pd.DataFrame(enriched)
    try:
        ed.to_parquet(config.ENRICHED_PARQUET)
        print(f"Wrote {config.ENRICHED_PARQUET} ({len(ed)} rows)")
    except Exception:
        ed.to_csv(config.CACHE_DIR / "enriched_records.csv", index=False)
        print(f"Wrote enriched_records.csv ({len(ed)} rows)")
    if ed.get("_metadata_blocked", pd.Series([False])).any():
        print("WARNING: some metadata hosts were blocked by the egress policy.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
