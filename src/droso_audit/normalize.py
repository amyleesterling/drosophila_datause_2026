"""Identifier and title normalization plus record dedupe.

Kept dependency-light (stdlib + optional unidecode) so it is unit-testable
without the heavier pipeline dependencies.
"""
from __future__ import annotations

import hashlib
import re
from typing import Iterable, Optional

try:
    from unidecode import unidecode
except Exception:  # pragma: no cover - optional
    def unidecode(s: str) -> str:  # type: ignore
        return s


_DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"'<>]+", re.IGNORECASE)
_WS_RE = re.compile(r"\s+")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9 ]+")


def normalize_doi(value: Optional[str]) -> Optional[str]:
    """Return a bare lowercased DOI, or None.

    Handles full URLs (https://doi.org/...), ``doi:`` prefixes, trailing
    punctuation, and version suffixes are preserved (e.g. eLife reviewed
    preprints use ``.1``). Returns None when no DOI pattern is found.
    """
    if not value:
        return None
    s = str(value).strip()
    if not s or s.lower() in {"nan", "none", "null"}:
        return None
    # Strip common URL/prefix wrappers.
    s = re.sub(r"^https?://(dx\.)?doi\.org/", "", s, flags=re.IGNORECASE)
    s = re.sub(r"^doi:\s*", "", s, flags=re.IGNORECASE)
    m = _DOI_RE.search(s)
    if not m:
        return None
    doi = m.group(0).lower()
    # Strip trailing punctuation that is never part of a DOI.
    doi = doi.rstrip(".,;)]}>\"'")
    return doi


def normalize_pmid(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    s = re.sub(r"^pmid:?\s*", "", s, flags=re.IGNORECASE)
    m = re.search(r"\d{1,9}", s)
    return m.group(0) if m else None


def normalize_pmcid(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip().upper()
    m = re.search(r"PMC\d+", s)
    if m:
        return m.group(0)
    m = re.search(r"\b(\d{5,9})\b", s)
    return f"PMC{m.group(1)}" if m else None


def normalize_openalex_id(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    m = re.search(r"W\d+", s, re.IGNORECASE)
    return m.group(0).upper() if m else None


def normalize_title(value: Optional[str]) -> str:
    """Lowercase, transliterate, strip punctuation, collapse whitespace."""
    if value is None:
        return ""
    s = unidecode(str(value)).lower()
    s = s.replace("&", " and ")
    s = _NON_ALNUM_RE.sub(" ", s)
    s = _WS_RE.sub(" ", s).strip()
    return s


def record_id_for(
    doi: Optional[str] = None,
    pmid: Optional[str] = None,
    pmcid: Optional[str] = None,
    openalex_id: Optional[str] = None,
    title: Optional[str] = None,
) -> str:
    """Deterministic stable record id usable as a cache filename.

    Prefers the strongest identifier available; falls back to a hash of the
    normalized title so every record gets a stable id.
    """
    if doi:
        key = f"doi:{normalize_doi(doi)}"
    elif pmcid:
        key = f"pmcid:{normalize_pmcid(pmcid)}"
    elif pmid:
        key = f"pmid:{normalize_pmid(pmid)}"
    elif openalex_id:
        key = f"openalex:{normalize_openalex_id(openalex_id)}"
    else:
        key = f"title:{normalize_title(title)}"
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:16]


def dedupe_key(row: dict) -> str:
    """Return the best dedupe key for a record dict (post-normalization)."""
    for col in ("doi_normalized", "pmcid", "pmid", "openalex_id"):
        v = row.get(col)
        if v:
            return f"{col}:{v}"
    return f"title:{normalize_title(row.get('normalized_title') or row.get('title'))}"


def find_doi_column(columns: Iterable[str]) -> Optional[str]:
    """Heuristically find the column most likely to hold DOIs."""
    cols = list(columns)
    lowered = {c.lower().strip(): c for c in cols}
    for cand in ("doi", "doi_normalized", "article doi", "doi link", "doi/url", "url"):
        if cand in lowered:
            return lowered[cand]
    for low, orig in lowered.items():
        if "doi" in low:
            return orig
    return None


def find_title_column(columns: Iterable[str]) -> Optional[str]:
    lowered = {c.lower().strip(): c for c in columns}
    for cand in ("title", "article title", "paper title", "name"):
        if cand in lowered:
            return lowered[cand]
    for low, orig in lowered.items():
        if "title" in low:
            return orig
    return None
