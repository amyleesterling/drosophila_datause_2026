"""Extract clean, sectioned text from XML / HTML / PDF full-text artifacts."""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from .config import PARSED_CACHE

# Heavy parsers are imported lazily so the package imports without them.

SECTION_MAP = [
    ("abstract", ["abstract", "summary"]),
    ("introduction", ["introduction", "background"]),
    ("methods", ["method", "materials and methods", "experimental", "star methods", "procedures"]),
    ("results", ["result", "findings"]),
    ("discussion", ["discussion", "conclusion"]),
    ("data_availability", ["data availability", "data and code", "code availability", "data access"]),
]


def classify_heading(heading: str) -> str:
    h = (heading or "").strip().lower()
    for canonical, keys in SECTION_MAP:
        if any(k in h for k in keys):
            return canonical
    return "unknown"


# --------------------------------------------------------------------------- #
# JATS / Europe PMC XML
# --------------------------------------------------------------------------- #
def parse_jats_xml(path: Path) -> list[dict]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="ignore"), "lxml-xml")
    sections: list[dict] = []

    abstract = soup.find("abstract")
    if abstract:
        sections.append({"section": "abstract", "heading": "Abstract", "text": abstract.get_text(" ", strip=True)})

    body = soup.find("body")
    if body:
        for sec in body.find_all("sec", recursive=True):
            title_tag = sec.find("title", recursive=False)
            heading = title_tag.get_text(" ", strip=True) if title_tag else ""
            # Collect paragraph text directly under this sec.
            paras = [p.get_text(" ", strip=True) for p in sec.find_all("p", recursive=False)]
            text = " ".join(paras).strip()
            if text:
                sections.append({"section": classify_heading(heading), "heading": heading, "text": text})

    # Figure captions.
    captions = [c.get_text(" ", strip=True) for c in soup.find_all("caption")]
    if captions:
        sections.append({"section": "figure_caption", "heading": "Figure captions",
                         "text": "\n".join(captions)})

    # Data availability statements often live in <notes> or <sec>.
    return sections


# --------------------------------------------------------------------------- #
# HTML
# --------------------------------------------------------------------------- #
def parse_html(path: Path) -> list[dict]:
    raw = path.read_text(encoding="utf-8", errors="ignore")
    text = None
    try:
        import trafilatura

        text = trafilatura.extract(raw, include_comments=False, include_tables=False)
    except Exception:
        text = None
    if not text:
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(raw, "lxml")
        for tag in soup(["script", "style", "nav", "header", "footer"]):
            tag.decompose()
        text = soup.get_text(" ", strip=True)
    return _heuristic_sections(text or "")


# --------------------------------------------------------------------------- #
# PDF
# --------------------------------------------------------------------------- #
def parse_pdf(path: Path) -> list[dict]:
    text = ""
    try:
        import fitz  # pymupdf

        with fitz.open(path) as doc:
            text = "\n".join(page.get_text() for page in doc)
    except Exception:
        text = ""
    if not text.strip():
        try:
            from pypdf import PdfReader

            reader = PdfReader(str(path))
            text = "\n".join((page.extract_text() or "") for page in reader.pages)
        except Exception:
            text = ""
    return _heuristic_sections(text)


_HEADING_RE = re.compile(
    r"^\s*(\d+\.?\s+)?(abstract|introduction|background|results?|methods?|materials and methods|"
    r"discussion|conclusions?|data availability|references|acknowledg)",
    re.IGNORECASE | re.MULTILINE,
)


def _heuristic_sections(text: str) -> list[dict]:
    """Split a flat text blob into rough sections using heading keywords."""
    if not text or not text.strip():
        return []
    matches = list(_HEADING_RE.finditer(text))
    if not matches:
        return [{"section": "unknown", "heading": "", "text": text.strip()}]
    sections: list[dict] = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        heading = m.group(2)
        body = text[start:end].strip()
        sections.append({"section": classify_heading(heading), "heading": heading.title(), "text": body})
    # Capture any preamble (often title/abstract) before the first heading.
    if matches[0].start() > 200:
        sections.insert(0, {"section": "unknown", "heading": "", "text": text[: matches[0].start()].strip()})
    return sections


# --------------------------------------------------------------------------- #
# Orchestration
# --------------------------------------------------------------------------- #
def extract_record(*, record_id: str, title: str, artifacts: dict,
                   abstract_fallback: str = "") -> dict:
    """Produce the structured parsed-text JSON for a record. Caches to disk."""
    out_path = PARSED_CACHE / f"{record_id}.json"
    sections: list[dict] = []
    status = "not_attempted"
    raw_path = None

    try:
        if artifacts.get("xml_path"):
            sections = parse_jats_xml(Path(artifacts["xml_path"]))
            raw_path = artifacts["xml_path"]
        elif artifacts.get("html_path"):
            sections = parse_html(Path(artifacts["html_path"]))
            raw_path = artifacts["html_path"]
        elif artifacts.get("pdf_path"):
            sections = parse_pdf(Path(artifacts["pdf_path"]))
            raw_path = artifacts["pdf_path"]
        status = "ok" if sections else "empty"
    except Exception as e:  # noqa: BLE001
        status = f"failed:{type(e).__name__}"
        sections = []

    if not sections and abstract_fallback:
        sections = [{"section": "abstract", "heading": "Abstract", "text": abstract_fallback}]
        status = status if status != "not_attempted" else "abstract_only"

    references_text = ""
    refs = [s for s in sections if s["section"] == "references" or "reference" in (s.get("heading", "").lower())]
    if refs:
        references_text = "\n".join(s["text"] for s in refs)

    result = {
        "record_id": record_id,
        "title": title,
        "sections": sections,
        "references_text": references_text,
        "raw_text_path": raw_path,
        "text_extraction_status": status,
    }
    out_path.write_text(json.dumps(result, ensure_ascii=False))
    return result


def load_parsed(record_id: str) -> Optional[dict]:
    p = PARSED_CACHE / f"{record_id}.json"
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            return None
    return None
