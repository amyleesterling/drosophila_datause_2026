"""Full-text acquisition: Europe PMC XML, publisher OA HTML/PDF, preprints, Unpaywall.

Tries sources in priority order and records *why* full text was/wasn't found.
All artifacts are cached on disk and reused on resume.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from .config import FULLTEXT_CACHE, PDF_CACHE, SETTINGS
from .httpc import HostNotAllowed, get_bytes, get_json, get_text


@dataclass
class FullTextResult:
    record_id: str
    full_text_status: str = "not_attempted"
    full_text_source: str = ""
    full_text_url: str = ""
    pdf_url: str = ""
    reason: str = ""
    xml_path: Optional[str] = None
    html_path: Optional[str] = None
    pdf_path: Optional[str] = None


def _looks_like_pdf(content: bytes) -> bool:
    return content[:5] == b"%PDF-"


def europepmc_fulltext_xml(record_id: str, pmcid: Optional[str]) -> Optional[Path]:
    if not pmcid:
        return None
    pmc_num = pmcid.replace("PMC", "")
    url = f"https://www.ebi.ac.uk/europepmc/webservices/rest/PMC{pmc_num}/fullTextXML"
    res = get_text(url)
    if not res:
        return None
    text, _ = res
    if "<article" not in text.lower():
        return None
    p = FULLTEXT_CACHE / f"{record_id}.xml"
    p.write_text(text, encoding="utf-8")
    return p


def fetch_html(record_id: str, url: str) -> Optional[Path]:
    res = get_text(url)
    if not res:
        return None
    text, ctype = res
    if "html" not in ctype.lower() and "<html" not in text.lower()[:2000]:
        return None
    p = FULLTEXT_CACHE / f"{record_id}.html"
    p.write_text(text, encoding="utf-8")
    return p


def fetch_pdf(record_id: str, url: str) -> Optional[Path]:
    content = get_bytes(url)
    if not content or not _looks_like_pdf(content):
        return None
    p = PDF_CACHE / f"{record_id}.pdf"
    p.write_bytes(content)
    return p


def biorxiv_pdf(record_id: str, doi: Optional[str]) -> Optional[Path]:
    """bioRxiv/medRxiv expose <doi>.full.pdf at the cosmos/connect endpoints."""
    if not doi:
        return None
    if "10.1101/" not in doi:
        return None
    for base in ("https://www.biorxiv.org/content", "https://www.medrxiv.org/content"):
        url = f"{base}/{doi}v1.full.pdf"
        p = fetch_pdf(record_id, url)
        if p:
            return p
    return None


def fetch_full_text(*, record_id: str, meta: dict) -> FullTextResult:
    """Acquire full text for one record. ``meta`` is the enriched metadata dict."""
    res = FullTextResult(record_id=record_id)
    pmcid = meta.get("pmcid")
    doi = meta.get("doi_normalized")
    oa_url = meta.get("best_oa_url")
    pdf_url = meta.get("best_pdf_url")
    res.full_text_url = oa_url or ""
    res.pdf_url = pdf_url or ""

    if not (pmcid or oa_url or pdf_url or doi):
        res.full_text_status = "not_attempted"
        res.reason = "no DOI" if not doi else "metadata only"
        return res

    blocked = False
    try:
        # 1) Europe PMC / PMC structured XML.
        xml = europepmc_fulltext_xml(record_id, pmcid)
        if xml:
            res.xml_path = str(xml)
            res.full_text_status = "found_xml_only"
            res.full_text_source = "europepmc_xml"
            res.reason = "OA XML found in PMC/Europe PMC"
            return res

        # 2) Publisher OA HTML.
        if oa_url:
            html = fetch_html(record_id, oa_url)
            if html:
                res.html_path = str(html)
                res.full_text_status = "found_html_only"
                res.full_text_source = "publisher_html"
                res.reason = "OA HTML found at publisher"
                return res

        # 3) OA PDF (Unpaywall/OpenAlex best_pdf_url).
        if pdf_url:
            pdf = fetch_pdf(record_id, pdf_url)
            if pdf:
                res.pdf_path = str(pdf)
                res.full_text_status = "found_pdf_only"
                res.full_text_source = "oa_pdf"
                res.reason = "OA PDF found via Unpaywall/OpenAlex"
                return res

        # 4) Preprint server.
        pre = biorxiv_pdf(record_id, doi)
        if pre:
            res.pdf_path = str(pre)
            res.full_text_status = "found_pdf_only"
            res.full_text_source = "preprint_pdf"
            res.reason = "preprint PDF found"
            return res
    except HostNotAllowed:
        blocked = True

    # Nothing worked.
    if blocked:
        res.full_text_status = "failed_download"
        res.reason = "egress policy blocked publisher/PMC hosts"
    elif meta.get("abstract"):
        res.full_text_status = "abstract_only"
        res.reason = "metadata only"
    else:
        res.full_text_status = "paywalled_or_unavailable"
        res.reason = "paywalled"
    return res


def existing_artifacts(record_id: str) -> dict:
    """Return cached artifact paths for resume support."""
    out = {}
    xml = FULLTEXT_CACHE / f"{record_id}.xml"
    html = FULLTEXT_CACHE / f"{record_id}.html"
    pdf = PDF_CACHE / f"{record_id}.pdf"
    if xml.exists():
        out["xml_path"] = str(xml)
    if html.exists():
        out["html_path"] = str(html)
    if pdf.exists():
        out["pdf_path"] = str(pdf)
    return out
