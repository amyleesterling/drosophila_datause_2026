"""Optional: expand the citing-paper set from seed resource papers via OpenAlex."""
from __future__ import annotations

from typing import Iterator, Optional

from .config import SEED_PAPERS, SETTINGS
from .httpc import HostNotAllowed, get_json
from .metadata import openalex_by_doi
from .normalize import normalize_doi, normalize_openalex_id


def _mailto(extra: Optional[dict] = None) -> dict:
    p = dict(extra or {})
    if SETTINGS.openalex_mailto:
        p["mailto"] = SETTINGS.openalex_mailto
    return p


def iter_citing_works(openalex_id: str, *, max_pages: int = 50) -> Iterator[dict]:
    """Yield works that cite the given OpenAlex work id, via cursor paging."""
    cursor = "*"
    pages = 0
    while cursor and pages < max_pages:
        params = _mailto({
            "filter": f"cites:{openalex_id}",
            "per_page": 200,
            "cursor": cursor,
            "select": "id,doi,title,publication_year",
        })
        data = get_json(
            "https://api.openalex.org/works", params=params,
            cache_key=f"cites:{openalex_id}:{cursor}",
        )
        if not data:
            return
        for w in data.get("results", []):
            yield w
        cursor = (data.get("meta") or {}).get("next_cursor")
        pages += 1


def expand_from_seeds(seeds: Optional[list[dict]] = None) -> list[dict]:
    """Return deduped citing-work records across all seed resource papers."""
    seeds = seeds or SEED_PAPERS
    rows: dict[str, dict] = {}
    for seed in seeds:
        try:
            work = openalex_by_doi(seed["doi"])
        except HostNotAllowed:
            print("OpenAlex blocked by egress policy; cannot expand citations.")
            return list(rows.values())
        if not work:
            continue
        seed_oa = normalize_openalex_id(work.get("id"))
        if not seed_oa:
            continue
        for citing in iter_citing_works(seed_oa):
            oid = normalize_openalex_id(citing.get("id"))
            if not oid:
                continue
            if oid in rows:
                rows[oid]["seed_resource"] += f";{seed['resource']}"
                continue
            rows[oid] = {
                "seed_resource": seed["resource"],
                "seed_title": seed["title"],
                "seed_doi": seed["doi"],
                "citing_work_openalex_id": oid,
                "citing_work_doi": normalize_doi(citing.get("doi")),
                "citing_work_title": citing.get("title"),
                "year": citing.get("publication_year"),
            }
    return list(rows.values())
