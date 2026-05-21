"""Build the evidence-snippet table from detected mentions."""
from __future__ import annotations

from .detect_resources import Mention


def mentions_to_rows(record_id: str, title: str, doi: str, mentions: list[Mention]) -> list[dict]:
    rows = []
    for m in mentions:
        rows.append({
            "record_id": record_id,
            "title": title,
            "doi": doi or "",
            "resource_term": m.resource_term,
            "section": m.section,
            "sentence_window": m.sentence_window,
            "start_char": m.start_char,
            "end_char": m.end_char,
            "is_weak": m.is_weak,
        })
    return rows


def evidence_windows_for_llm(mentions: list[Mention], limit: int = 25) -> list[str]:
    """Prefer methods/results windows; dedupe; cap count for the LLM payload."""
    priority = {"methods": 0, "results": 1, "data_availability": 1, "figure_caption": 2,
                "abstract": 3, "introduction": 4, "discussion": 4}
    ordered = sorted(mentions, key=lambda m: (m.is_weak, priority.get(m.section, 9)))
    seen: set[str] = set()
    out: list[str] = []
    for m in ordered:
        w = (m.sentence_window or "").strip()
        if not w or w in seen:
            continue
        seen.add(w)
        out.append(f"[{m.section}] {w}")
        if len(out) >= limit:
            break
    return out
