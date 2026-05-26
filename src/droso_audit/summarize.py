"""Build summary_counts.json and summary_counts.md from the audited dataframe."""
from __future__ import annotations

import json
from collections import Counter

import pandas as pd

from .config import OUTPUTS_DIR, USE_CATEGORIES


FULL_TEXT_FOUND_STATUSES = {
    "found_oa_full_text", "found_pdf_only", "found_html_only", "found_xml_only",
}


def _count_col(df: pd.DataFrame, col: str) -> dict:
    if col not in df.columns:
        return {}
    return {str(k): int(v) for k, v in df[col].fillna("(blank)").value_counts().items()}


def _semicolon_counts(df: pd.DataFrame, col: str) -> dict:
    if col not in df.columns:
        return {}
    c: Counter = Counter()
    for val in df[col].fillna(""):
        for token in str(val).split(";"):
            token = token.strip()
            if token and token not in ("", "none_detected", "unknown"):
                c[token] += 1
    return dict(c.most_common())


def build_summary(df: pd.DataFrame) -> dict:
    total = len(df)
    uses = df.get("actually_uses_connectome_data", pd.Series(dtype=str)).fillna("")
    cats = df.get("use_category", pd.Series(dtype=str)).fillna("")
    fts = df.get("full_text_status", pd.Series(dtype=str)).fillna("")

    use_counts = {v: int((uses == v).sum()) for v in ["yes", "probably_yes", "unclear", "probably_no", "no"]}
    cat_counts = {c: int((cats == c).sum()) for c in USE_CATEGORIES}
    full_text_found = int(fts.isin(FULL_TEXT_FOUND_STATUSES).sum())
    full_text_unavailable = total - full_text_found

    strict = cat_counts["A_direct_connectome_data_analysis"] + cat_counts["C_tool_or_method_using_connectome_dataset"]
    broad = strict + cat_counts["B_connectome_derived_biological_result"]
    weak = cat_counts["D_reuses_published_stats_or_figures_only"]
    not_use = cat_counts["E_background_citation_only"] + cat_counts["F_review_perspective_commentary"]
    unknown = cat_counts["G_unclassifiable_no_full_text"] + use_counts["unclear"]

    summary = {
        "total_input_papers": int(df.attrs.get("input_count", total)),
        "unique_papers_after_dedupe": total,
        "full_text_found": full_text_found,
        "full_text_unavailable": full_text_unavailable,
        "use_counts": use_counts,
        "manual_review_needed": int((df.get("manual_review_needed", pd.Series(dtype=str)) == "yes").sum()),
        "category_counts": cat_counts,
        "resource_cited": _semicolon_counts(df, "resource_cited"),
        "resource_detected_in_text": _semicolon_counts(df, "resource_detected_in_text"),
        "by_year": _count_col(df, "year"),
        "by_journal_or_source": dict(Counter(_count_col(df, "journal_or_source")).most_common(30)),
        "by_full_text_status": _count_col(df, "full_text_status"),
        "estimates": {
            "strict_data_use": strict,
            "broad_data_use": broad,
            "weak_or_contextual_use": weak,
            "not_data_use": not_use,
            "unknown_or_manual": unknown,
        },
    }
    return summary


def _pct(n: int, d: int) -> str:
    return f"{(100.0 * n / d):.1f}%" if d else "0.0%"


def summary_to_markdown(s: dict) -> str:
    total = s["unique_papers_after_dedupe"]
    est = s["estimates"]
    uc = s["use_counts"]
    lines = [
        "# Drosophila Connectome Data-Use Audit Summary",
        "",
        f"Input records: {s['total_input_papers']}",
        f"Unique papers after dedupe: {total}",
        f"Full text found: {s['full_text_found']} ({_pct(s['full_text_found'], total)})",
        f"Full text unavailable: {s['full_text_unavailable']} ({_pct(s['full_text_unavailable'], total)})",
        "",
        f"Strict direct data-use papers: {est['strict_data_use']}",
        f"Broad data-use papers: {est['broad_data_use']}",
        f"Weak/contextual reuse only: {est['weak_or_contextual_use']}",
        f"Background/review only: {est['not_data_use']}",
        f"Unknown/manual review: {est['unknown_or_manual']}",
        "",
        "## Classification (actually_uses_connectome_data)",
        f"- yes: {uc['yes']}",
        f"- probably_yes: {uc['probably_yes']}",
        f"- unclear: {uc['unclear']}",
        f"- probably_no: {uc['probably_no']}",
        f"- no: {uc['no']}",
        f"- manual review needed: {s['manual_review_needed']}",
        "",
        "## Use categories",
    ]
    for cat, n in s["category_counts"].items():
        lines.append(f"- {cat}: {n}")
    lines += ["", "## Resources actually detected in text"]
    for res, n in s["resource_detected_in_text"].items():
        lines.append(f"- {res}: {n}")
    lines += [
        "",
        "Interpretation:",
        f"This first-pass full-text audit suggests that {est['strict_data_use']}–{est['broad_data_use']} "
        f"papers materially use Drosophila connectome resources, compared with {est['not_data_use']} papers "
        f"that cite them as background or reviews. {est['unknown_or_manual']} papers remain unknown or need "
        "manual review (often due to missing full text).",
        "",
        "Strict = direct data analysis (A) + tool/method using the dataset (C).",
        "Broad = A + C + connectome-derived biological results (B).",
    ]
    return "\n".join(lines)


def write_summary(df: pd.DataFrame) -> dict:
    s = build_summary(df)
    (OUTPUTS_DIR / "summary_counts.json").write_text(json.dumps(s, indent=2))
    (OUTPUTS_DIR / "summary_counts.md").write_text(summary_to_markdown(s))
    return s
