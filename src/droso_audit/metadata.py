"""Metadata enrichment via OpenAlex, Crossref, Semantic Scholar, Europe PMC, Unpaywall.

Each source is queried defensively; any single failure (network, 404, blocked
host) degrades gracefully and the pipeline continues with whatever it has.
"""
from __future__ import annotations

import urllib.parse
from typing import Optional

from .config import SETTINGS
from .httpc import HostNotAllowed, get_json
from .normalize import (
    normalize_doi,
    normalize_openalex_id,
    normalize_pmcid,
    normalize_pmid,
)


def _mailto_params(extra: Optional[dict] = None) -> dict:
    p = dict(extra or {})
    if SETTINGS.openalex_mailto:
        p["mailto"] = SETTINGS.openalex_mailto
    return p


# --------------------------------------------------------------------------- #
# OpenAlex
# --------------------------------------------------------------------------- #
def openalex_by_doi(doi: str) -> Optional[dict]:
    doi = normalize_doi(doi)
    if not doi:
        return None
    url = f"https://api.openalex.org/works/https://doi.org/{doi}"
    return get_json(url, params=_mailto_params(), cache_key=f"openalex_doi:{doi}")


def openalex_by_title(title: str) -> Optional[dict]:
    if not title:
        return None
    params = _mailto_params({"filter": f"title.search:{title}", "per_page": 1})
    data = get_json("https://api.openalex.org/works", params=params, cache_key=f"openalex_title:{title[:120]}")
    if data and data.get("results"):
        return data["results"][0]
    return None


def _reconstruct_abstract(inverted_index: Optional[dict]) -> str:
    if not inverted_index:
        return ""
    positions: list[tuple[int, str]] = []
    for word, idxs in inverted_index.items():
        for i in idxs:
            positions.append((i, word))
    positions.sort()
    return " ".join(w for _, w in positions)


def parse_openalex(work: dict) -> dict:
    if not work:
        return {}
    ids = work.get("ids", {}) or {}
    best_oa = work.get("best_oa_location") or work.get("primary_location") or {}
    host = (work.get("primary_location") or {}).get("source") or {}
    return {
        "openalex_id": normalize_openalex_id(work.get("id")),
        "doi_normalized": normalize_doi(work.get("doi")),
        "pmid": normalize_pmid(ids.get("pmid")),
        "pmcid": normalize_pmcid(ids.get("pmcid")),
        "year": work.get("publication_year"),
        "journal_or_source": host.get("display_name"),
        "abstract": _reconstruct_abstract(work.get("abstract_inverted_index")),
        "is_oa": bool(work.get("open_access", {}).get("is_oa")),
        "best_oa_url": (best_oa or {}).get("landing_page_url"),
        "best_pdf_url": (best_oa or {}).get("pdf_url"),
        "cited_by_count": work.get("cited_by_count"),
        "type": work.get("type"),
        "_source": "openalex",
    }


# --------------------------------------------------------------------------- #
# Crossref
# --------------------------------------------------------------------------- #
def crossref_by_doi(doi: str) -> Optional[dict]:
    doi = normalize_doi(doi)
    if not doi:
        return None
    params = {"mailto": SETTINGS.crossref_mailto} if SETTINGS.crossref_mailto else None
    data = get_json(f"https://api.crossref.org/works/{urllib.parse.quote(doi)}",
                    params=params, cache_key=f"crossref_doi:{doi}")
    return (data or {}).get("message")


def parse_crossref(msg: dict) -> dict:
    if not msg:
        return {}
    title = (msg.get("title") or [""])[0]
    year = None
    for k in ("published-print", "published-online", "issued", "created"):
        parts = (msg.get(k) or {}).get("date-parts")
        if parts and parts[0] and parts[0][0]:
            year = parts[0][0]
            break
    return {
        "doi_normalized": normalize_doi(msg.get("DOI")),
        "title_crossref": title,
        "year": year,
        "journal_or_source": (msg.get("container-title") or [None])[0],
        "type": msg.get("type"),
        "cited_by_count": msg.get("is-referenced-by-count"),
        "_source": "crossref",
    }


# --------------------------------------------------------------------------- #
# Semantic Scholar
# --------------------------------------------------------------------------- #
def semantic_scholar(doi: Optional[str] = None, title: Optional[str] = None) -> Optional[dict]:
    fields = "title,year,venue,externalIds,openAccessPdf,abstract,citationCount,isOpenAccess"
    headers = {"x-api-key": SETTINGS.semantic_scholar_key} if SETTINGS.semantic_scholar_key else None
    doi = normalize_doi(doi) if doi else None
    if doi:
        url = f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}"
        return get_json(url, params={"fields": fields}, headers=headers, cache_key=f"s2_doi:{doi}")
    if title:
        data = get_json(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            params={"query": title, "limit": 1, "fields": fields},
            headers=headers, cache_key=f"s2_title:{title[:120]}",
        )
        if data and data.get("data"):
            return data["data"][0]
    return None


def parse_semantic_scholar(paper: dict) -> dict:
    if not paper:
        return {}
    ext = paper.get("externalIds", {}) or {}
    oa = paper.get("openAccessPdf") or {}
    return {
        "semantic_scholar_id": paper.get("paperId"),
        "doi_normalized": normalize_doi(ext.get("DOI")),
        "pmid": normalize_pmid(ext.get("PubMed")),
        "pmcid": normalize_pmcid(ext.get("PubMedCentral")),
        "year": paper.get("year"),
        "journal_or_source": paper.get("venue"),
        "abstract": paper.get("abstract") or "",
        "best_pdf_url": oa.get("url"),
        "is_oa": bool(paper.get("isOpenAccess")),
        "cited_by_count": paper.get("citationCount"),
        "_source": "semantic_scholar",
    }


# --------------------------------------------------------------------------- #
# Europe PMC
# --------------------------------------------------------------------------- #
def europepmc(doi: Optional[str] = None, title: Optional[str] = None) -> Optional[dict]:
    if doi:
        query = f"DOI:{normalize_doi(doi)}"
    elif title:
        query = f'TITLE:"{title}"'
    else:
        return None
    data = get_json(
        "https://www.ebi.ac.uk/europepmc/webservices/rest/search",
        params={"query": query, "format": "json", "resultType": "core", "pageSize": 1},
        cache_key=f"epmc:{query[:120]}",
    )
    results = (((data or {}).get("resultList") or {}).get("result")) or []
    return results[0] if results else None


def parse_europepmc(rec: dict) -> dict:
    if not rec:
        return {}
    return {
        "doi_normalized": normalize_doi(rec.get("doi")),
        "pmid": normalize_pmid(rec.get("pmid")),
        "pmcid": normalize_pmcid(rec.get("pmcid")),
        "year": int(rec["pubYear"]) if rec.get("pubYear", "").isdigit() else None,
        "journal_or_source": (rec.get("journalInfo", {}) or {}).get("journal", {}).get("title"),
        "abstract": rec.get("abstractText", "") or "",
        "is_oa": rec.get("isOpenAccess") == "Y",
        "has_pmc_fulltext": rec.get("hasTextMinedTerms") == "Y" or bool(rec.get("pmcid")),
        "_source": "europepmc",
    }


# --------------------------------------------------------------------------- #
# Unpaywall
# --------------------------------------------------------------------------- #
def unpaywall(doi: str) -> Optional[dict]:
    doi = normalize_doi(doi)
    if not doi or not SETTINGS.unpaywall_email:
        return None
    return get_json(
        f"https://api.unpaywall.org/v2/{doi}",
        params={"email": SETTINGS.unpaywall_email},
        cache_key=f"unpaywall:{doi}",
    )


def parse_unpaywall(rec: dict) -> dict:
    if not rec:
        return {}
    best = rec.get("best_oa_location") or {}
    return {
        "is_oa": bool(rec.get("is_oa")),
        "best_oa_url": best.get("url_for_landing_page") or best.get("url"),
        "best_pdf_url": best.get("url_for_pdf"),
        "oa_status": rec.get("oa_status"),
        "_source": "unpaywall",
    }


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def _merge(base: dict, new: dict) -> dict:
    """Fill empty fields in base from new (do not overwrite existing values)."""
    for k, v in new.items():
        if k == "_source":
            continue
        if v in (None, "", []) :
            continue
        if base.get(k) in (None, "", [], 0) or k not in base:
            base[k] = v
    return base


def enrich_record(*, doi: Optional[str], title: Optional[str],
                  pmid: Optional[str] = None, pmcid: Optional[str] = None) -> dict:
    """Query metadata sources in priority order and merge results."""
    out: dict = {
        "doi_normalized": normalize_doi(doi),
        "pmid": normalize_pmid(pmid),
        "pmcid": normalize_pmcid(pmcid),
        "year": None,
        "journal_or_source": None,
        "openalex_id": None,
        "semantic_scholar_id": None,
        "abstract": "",
        "is_oa": False,
        "best_oa_url": None,
        "best_pdf_url": None,
        "cited_by_count": None,
        "meta_sources": [],
    }
    blocked = False

    def try_source(fn, parser, *args):
        nonlocal blocked
        try:
            raw = fn(*args)
        except HostNotAllowed:
            blocked = True
            return
        except Exception:
            return
        if raw:
            _merge(out, parser(raw))
            out["meta_sources"].append(parser(raw).get("_source", "?"))

    d = out["doi_normalized"]
    if d:
        try_source(openalex_by_doi, parse_openalex, d)
    if not out["openalex_id"] and title:
        try_source(openalex_by_title, parse_openalex, title)
    if d:
        try_source(crossref_by_doi, parse_crossref, d)
    try_source(semantic_scholar, parse_semantic_scholar, d, title)
    try_source(europepmc, parse_europepmc, d, title)
    if d:
        try_source(unpaywall, parse_unpaywall, d)

    out["meta_sources"] = ";".join(dict.fromkeys(out["meta_sources"]))
    out["_metadata_blocked"] = blocked
    return out
