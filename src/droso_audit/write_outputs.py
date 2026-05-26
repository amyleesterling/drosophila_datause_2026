"""Write the audited spreadsheet, manual-review sheet, and supporting CSVs."""
from __future__ import annotations

import pandas as pd

from .config import ADDED_COLUMNS, OUTPUTS_DIR


def write_audit(df: pd.DataFrame, *, out_xlsx: str = "outputs/droso_data_use_audit.xlsx") -> None:
    """Write the main audited workbook (xlsx + csv twin)."""
    OUTPUTS_DIR.mkdir(parents=True, exist_ok=True)
    xlsx_path = out_xlsx
    csv_path = out_xlsx.rsplit(".", 1)[0] + ".csv"
    # Ensure all added columns exist even if empty.
    for col in ADDED_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df.to_excel(xlsx_path, index=False)
    df.to_csv(csv_path, index=False)
    # Canonical names too.
    if xlsx_path != str(OUTPUTS_DIR / "droso_data_use_audit.xlsx"):
        df.to_excel(OUTPUTS_DIR / "droso_data_use_audit.xlsx", index=False)
        df.to_csv(OUTPUTS_DIR / "droso_data_use_audit.csv", index=False)


def write_manual_review(df: pd.DataFrame) -> None:
    """Write the prioritized manual-review queue."""
    review = df[df.get("manual_review_needed", "no") == "yes"].copy()
    cols = [
        "title", "doi_normalized", "year", "journal_or_source", "resource_cited",
        "resource_detected_in_text", "actually_uses_connectome_data", "use_category",
        "evidence_quote", "manual_review_reason", "full_text_url", "pdf_url",
    ]
    # title may live under a different original column; map gracefully.
    if "title" not in review.columns:
        for c in review.columns:
            if c.lower().strip() == "title":
                review["title"] = review[c]
                break
        else:
            review["title"] = review.get("normalized_title", "")
    if "doi" not in review.columns:
        review["doi"] = review.get("doi_normalized", "")
    for c in cols:
        if c not in review.columns:
            review[c] = ""

    # Sort priority: citations desc, year desc, unclear first, no-full-text, missing quote.
    cite = pd.to_numeric(review.get("cited_by_count", 0), errors="coerce").fillna(0)
    yr = pd.to_numeric(review.get("year", 0), errors="coerce").fillna(0)
    unclear = (review["actually_uses_connectome_data"] == "unclear").astype(int)
    no_ft = review["use_category"].eq("G_unclassifiable_no_full_text").astype(int)
    no_quote = review["evidence_quote"].fillna("").eq("").astype(int)
    review = review.assign(_cite=cite, _yr=yr, _unclear=unclear, _noft=no_ft, _noquote=no_quote)
    review = review.sort_values(
        by=["_cite", "_yr", "_unclear", "_noft", "_noquote"],
        ascending=[False, False, False, False, False],
    )
    review[cols].to_csv(OUTPUTS_DIR / "needs_manual_review.csv", index=False)


def write_full_text_inventory(df: pd.DataFrame) -> None:
    cols = [
        "record_id", "title", "doi_normalized", "year", "full_text_status",
        "full_text_source", "full_text_url", "pdf_url", "text_extraction_status",
    ]
    inv = df.copy()
    if "title" not in inv.columns:
        inv["title"] = inv.get("normalized_title", "")
    for c in cols:
        if c not in inv.columns:
            inv[c] = ""
    inv[cols].to_csv(OUTPUTS_DIR / "full_text_inventory.csv", index=False)


def write_evidence(evidence_rows: list[dict]) -> None:
    cols = ["record_id", "title", "doi", "resource_term", "section",
            "sentence_window", "start_char", "end_char"]
    ev = pd.DataFrame(evidence_rows)
    if ev.empty:
        ev = pd.DataFrame(columns=cols)
    for c in cols:
        if c not in ev.columns:
            ev[c] = ""
    ev[cols].to_csv(OUTPUTS_DIR / "evidence_snippets.csv", index=False)
