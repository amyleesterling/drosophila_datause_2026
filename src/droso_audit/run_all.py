"""End-to-end pipeline runner.

    python -m droso_audit.run_all --input data/input/droso_data_use.xlsx \
        --out outputs/droso_data_use_audit.xlsx --use-llm --max-records 25

Each stage caches to disk so the run is resumable after interruption.
"""
from __future__ import annotations

import argparse
import datetime as dt
import sys

import pandas as pd
from tqdm import tqdm

from . import config
from .classify import Classification, llm_classify, merge_classification, rule_preclassify
from .detect_resources import detect_in_sections, resources_detected
from .evidence import evidence_windows_for_llm, mentions_to_rows
from .extract_text import extract_record, load_parsed
from .fulltext import existing_artifacts, fetch_full_text
from .io import load_input
from .metadata import enrich_record
from .normalize import (
    dedupe_key,
    find_doi_column,
    find_title_column,
    normalize_doi,
    normalize_title,
    record_id_for,
)
from .summarize import write_summary
from .write_outputs import (
    write_audit,
    write_evidence,
    write_full_text_inventory,
    write_manual_review,
)

TODAY = dt.date.today().isoformat()
FULL_TEXT_FOUND = {"found_oa_full_text", "found_pdf_only", "found_html_only", "found_xml_only"}


def normalize_df(df: pd.DataFrame) -> pd.DataFrame:
    """Add normalized identifiers and dedupe."""
    doi_col = find_doi_column(df.columns)
    title_col = find_title_column(df.columns)
    df = df.copy()
    df["__orig_doi"] = df[doi_col] if doi_col else ""
    df["__orig_title"] = df[title_col] if title_col else ""
    df["doi_normalized"] = df["__orig_doi"].map(normalize_doi)
    df["normalized_title"] = df["__orig_title"].map(normalize_title)
    if "title" not in df.columns and title_col:
        df["title"] = df[title_col]
    df.attrs["input_count"] = len(df)

    # Dedupe by best available key.
    df["__dedupe_key"] = df.apply(lambda r: dedupe_key(r.to_dict()), axis=1)
    before = len(df)
    df = df.drop_duplicates(subset="__dedupe_key", keep="first").reset_index(drop=True)
    df.attrs["input_count"] = before
    return df


def detect_resource_cited(row: dict) -> str:
    """Best-effort guess of which resource the paper cites, from input columns."""
    blob = " ".join(str(v) for v in row.values()).lower()
    found = []
    for label, keys in {
        "hemibrain": ["hemibrain"],
        "FAFB": ["fafb"],
        "FlyWire": ["flywire"],
        "MANC": ["manc"],
        "FANC": ["fanc"],
    }.items():
        if any(k in blob for k in keys):
            found.append(label)
    return ";".join(found) if found else "unknown"


def process_record(row: dict, *, use_llm: bool, fetch: bool) -> tuple[dict, list[dict]]:
    """Run metadata -> full text -> extract -> detect -> classify for one row."""
    title = row.get("title") or row.get("__orig_title") or ""
    doi = row.get("doi_normalized")
    rid = record_id_for(doi=doi, title=title)

    # 1) Metadata.
    meta = enrich_record(doi=doi, title=title,
                         pmid=row.get("pmid"), pmcid=row.get("pmcid"))

    # 2) Full text (cached/resumable).
    artifacts = existing_artifacts(rid)
    ft_status = "not_attempted"
    ft_source = ft_url = pdf_url = ""
    if fetch and not artifacts:
        ft = fetch_full_text(record_id=rid, meta=meta)
        ft_status, ft_source = ft.full_text_status, ft.full_text_source
        ft_url, pdf_url = ft.full_text_url, ft.pdf_url
        artifacts = {k: v for k, v in {
            "xml_path": ft.xml_path, "html_path": ft.html_path, "pdf_path": ft.pdf_path
        }.items() if v}
    elif artifacts:
        ft_status = "found_xml_only" if "xml_path" in artifacts else (
            "found_html_only" if "html_path" in artifacts else "found_pdf_only")
        ft_source = "cache"
    ft_url = ft_url or meta.get("best_oa_url") or ""
    pdf_url = pdf_url or meta.get("best_pdf_url") or ""

    # 3) Extract text.
    parsed = load_parsed(rid)
    if parsed is None:
        parsed = extract_record(record_id=rid, title=title, artifacts=artifacts,
                                abstract_fallback=meta.get("abstract", ""))
    sections = parsed.get("sections", [])
    extraction_status = parsed.get("text_extraction_status", "not_attempted")
    has_full_text = ft_status in FULL_TEXT_FOUND and any(
        s.get("section") not in ("abstract", "unknown") for s in sections)

    # 4) Detect mentions.
    mentions = detect_in_sections(sections)
    resource_in_text = resources_detected(mentions)
    evidence_rows = mentions_to_rows(rid, title, doi or "", mentions)

    # 5) Classify.
    mention_dicts = [{
        "resource_term": m.resource_term, "section": m.section,
        "sentence_window": m.sentence_window, "is_weak": m.is_weak,
    } for m in mentions]
    rules = rule_preclassify(
        has_full_text=has_full_text, title=title,
        abstract=meta.get("abstract", ""), mentions=mention_dicts,
        resource_detected=resource_in_text,
    )
    llm = None
    if use_llm:
        data_avail = " ".join(s["text"] for s in sections if s["section"] == "data_availability")
        fig_caps = " ".join(s["text"] for s in sections if s["section"] == "figure_caption")
        llm = llm_classify(
            title=title, abstract=meta.get("abstract", ""),
            evidence_windows=evidence_windows_for_llm(mentions),
            data_availability=data_avail, figure_captions=fig_caps,
            has_full_text=has_full_text,
        )
    final = merge_classification(rules, llm, has_full_text)

    out = {
        "openalex_id": meta.get("openalex_id"),
        "semantic_scholar_id": meta.get("semantic_scholar_id"),
        "pmid": meta.get("pmid"),
        "pmcid": meta.get("pmcid"),
        "year": meta.get("year"),
        "journal_or_source": meta.get("journal_or_source"),
        "cited_by_count": meta.get("cited_by_count"),
        "resource_cited": detect_resource_cited(row),
        "resource_detected_in_text": final.resource_detected_in_text or resource_in_text,
        "full_text_status": ft_status,
        "full_text_source": ft_source,
        "full_text_url": ft_url,
        "pdf_url": pdf_url,
        "text_extraction_status": extraction_status,
        "actually_uses_connectome_data": final.actually_uses_connectome_data,
        "use_category": final.use_category,
        "use_subcategory": final.use_subcategory,
        "evidence_quote": final.evidence_quote,
        "evidence_section": final.evidence_section,
        "evidence_location": final.evidence_location,
        "confidence": final.confidence,
        "manual_review_needed": final.manual_review_needed,
        "manual_review_reason": final.manual_review_reason,
        "classifier_notes": (final.classifier_notes + f" [src={final.source}]").strip(),
        "last_checked_date": TODAY,
        "record_id": rid,
    }
    return out, evidence_rows


def run(args: argparse.Namespace) -> int:
    config.ensure_dirs()
    df = load_input(input_path=args.input, google_sheet_url=args.google_sheet_url)
    print(f"Loaded {len(df)} rows from input.")
    df = normalize_df(df)
    print(f"{len(df)} rows after dedupe.")
    df.to_parquet(config.NORMALIZED_PARQUET) if _can_parquet() else None

    if args.max_records and args.max_records > 0:
        df = df.head(args.max_records).copy()
        print(f"Limiting to first {len(df)} records.")

    use_llm = args.use_llm and config.SETTINGS.has_llm
    if args.use_llm and not config.SETTINGS.has_llm:
        print("--use-llm requested but no LLM API key found; running rules-only.", file=sys.stderr)

    all_evidence: list[dict] = []
    enriched_rows: list[dict] = []
    for _, row in tqdm(df.iterrows(), total=len(df), desc="auditing"):
        out, ev = process_record(row.to_dict(), use_llm=use_llm, fetch=not args.no_fetch)
        enriched_rows.append(out)
        all_evidence.extend(ev)

    enriched_df = pd.DataFrame(enriched_rows)
    # Merge added columns back onto the original (preserving original columns).
    result = pd.concat([df.reset_index(drop=True), enriched_df.reset_index(drop=True)], axis=1)
    # Drop helper columns from the visible output.
    result = result.drop(columns=[c for c in ("__orig_doi", "__orig_title", "__dedupe_key") if c in result.columns])
    result.attrs["input_count"] = df.attrs.get("input_count", len(df))

    write_audit(result, out_xlsx=args.out)
    write_manual_review(result)
    write_full_text_inventory(result)
    write_evidence(all_evidence)
    summary = write_summary(result)

    print("\n=== SUMMARY ===")
    est = summary["estimates"]
    print(f"Unique papers: {summary['unique_papers_after_dedupe']}")
    print(f"Full text found: {summary['full_text_found']}")
    print(f"Strict data-use: {est['strict_data_use']} | Broad: {est['broad_data_use']} "
          f"| Background/review: {est['not_data_use']} | Unknown/manual: {est['unknown_or_manual']}")
    print(f"Outputs written to {config.OUTPUTS_DIR}/")
    return 0


def _can_parquet() -> bool:
    try:
        import pyarrow  # noqa: F401
        return True
    except Exception:
        return False


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="droso_audit.run_all", description="Drosophila connectome data-use audit.")
    p.add_argument("--input", help="Path to local .xlsx or .csv export of the sheet.")
    p.add_argument("--google-sheet-url", help="Google Sheet URL (attempts xlsx export).")
    p.add_argument("--out", default="outputs/droso_data_use_audit.xlsx", help="Output xlsx path.")
    p.add_argument("--use-llm", action="store_true", help="Use LLM classification when a key is configured.")
    p.add_argument("--no-fetch", action="store_true", help="Skip network full-text fetch (use cache only).")
    p.add_argument("--max-records", type=int, default=0, help="Limit records (0 = no limit).")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
