"""Central configuration: paths, constants, seed papers, and column schema."""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:  # python-dotenv optional at import time
    pass


# --------------------------------------------------------------------------- #
# Paths
# --------------------------------------------------------------------------- #
PKG_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PKG_DIR.parent.parent

DATA_DIR = PROJECT_ROOT / "data"
INPUT_DIR = DATA_DIR / "input"
CACHE_DIR = DATA_DIR / "cache"
META_CACHE = CACHE_DIR / "metadata"
FULLTEXT_CACHE = CACHE_DIR / "full_text"
PDF_CACHE = CACHE_DIR / "pdfs"
PARSED_CACHE = CACHE_DIR / "parsed_text"
CLASSIFIER_CACHE = CACHE_DIR / "classifier"
OUTPUTS_DIR = PROJECT_ROOT / "outputs"

NORMALIZED_PARQUET = CACHE_DIR / "normalized_records.parquet"
ENRICHED_PARQUET = CACHE_DIR / "enriched_records.parquet"
FULLTEXT_PARQUET = CACHE_DIR / "fulltext_records.parquet"
EVIDENCE_PARQUET = CACHE_DIR / "evidence_snippets.parquet"
CLASSIFIED_PARQUET = CACHE_DIR / "classified_records.parquet"


def ensure_dirs() -> None:
    for d in (
        INPUT_DIR,
        META_CACHE,
        FULLTEXT_CACHE,
        PDF_CACHE,
        PARSED_CACHE,
        CLASSIFIER_CACHE,
        OUTPUTS_DIR,
    ):
        d.mkdir(parents=True, exist_ok=True)


# --------------------------------------------------------------------------- #
# Environment / secrets
# --------------------------------------------------------------------------- #
@dataclass
class Settings:
    unpaywall_email: str = field(default_factory=lambda: os.getenv("UNPAYWALL_EMAIL", ""))
    openalex_mailto: str = field(default_factory=lambda: os.getenv("OPENALEX_MAILTO", os.getenv("UNPAYWALL_EMAIL", "")))
    crossref_mailto: str = field(default_factory=lambda: os.getenv("CROSSREF_MAILTO", os.getenv("UNPAYWALL_EMAIL", "")))
    semantic_scholar_key: str = field(default_factory=lambda: os.getenv("SEMANTIC_SCHOLAR_API_KEY", ""))
    ncbi_email: str = field(default_factory=lambda: os.getenv("NCBI_EMAIL", ""))
    ncbi_key: str = field(default_factory=lambda: os.getenv("NCBI_API_KEY", ""))
    anthropic_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    anthropic_model: str = field(default_factory=lambda: os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"))
    openai_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))
    openai_model: str = field(default_factory=lambda: os.getenv("OPENAI_MODEL", "gpt-4o-mini"))

    @property
    def has_llm(self) -> bool:
        return bool(self.anthropic_key or self.openai_key)

    @property
    def llm_provider(self) -> str:
        if self.anthropic_key:
            return "anthropic"
        if self.openai_key:
            return "openai"
        return "none"


SETTINGS = Settings()

USER_AGENT = (
    "droso-data-use-audit/0.1 (https://github.com/amyleesterling/drosophila_datause_2026; "
    f"mailto:{SETTINGS.openalex_mailto or 'unknown@example.com'})"
)


# --------------------------------------------------------------------------- #
# Seed resource papers (for mention detection + optional citation expansion)
# --------------------------------------------------------------------------- #
SEED_PAPERS = [
    {
        "resource": "hemibrain",
        "title": "A connectome and analysis of the adult Drosophila central brain",
        "doi": "10.7554/eLife.57443",
    },
    {
        "resource": "FAFB",
        "title": "A Complete Electron Microscopy Volume of the Brain of Adult Drosophila melanogaster",
        "doi": "10.1016/j.cell.2018.06.019",
    },
    {
        "resource": "FlyWire",
        "title": "FlyWire: online community for whole-brain connectomics",
        "doi": "10.1038/s41592-021-01330-0",
    },
    {
        "resource": "FlyWire",
        "title": "Neuronal wiring diagram of an adult brain",
        "doi": "10.1038/s41586-024-07558-y",
    },
    {
        "resource": "FlyWire",
        "title": "Whole-brain annotation and multi-connectome cell typing of Drosophila",
        "doi": "10.1038/s41586-024-07686-5",
    },
    {
        "resource": "MANC",
        "title": "A Connectome of the Male Drosophila Ventral Nerve Cord",
        "doi": "10.7554/eLife.97769.1",
    },
]


# --------------------------------------------------------------------------- #
# Output column schema
# --------------------------------------------------------------------------- #
ADDED_COLUMNS = [
    "normalized_title",
    "doi_normalized",
    "pmid",
    "pmcid",
    "openalex_id",
    "semantic_scholar_id",
    "year",
    "journal_or_source",
    "resource_cited",
    "resource_detected_in_text",
    "full_text_status",
    "full_text_source",
    "full_text_url",
    "pdf_url",
    "text_extraction_status",
    "actually_uses_connectome_data",
    "use_category",
    "use_subcategory",
    "evidence_quote",
    "evidence_section",
    "evidence_location",
    "confidence",
    "manual_review_needed",
    "manual_review_reason",
    "classifier_notes",
    "last_checked_date",
]

USE_CATEGORIES = [
    "A_direct_connectome_data_analysis",
    "B_connectome_derived_biological_result",
    "C_tool_or_method_using_connectome_dataset",
    "D_reuses_published_stats_or_figures_only",
    "E_background_citation_only",
    "F_review_perspective_commentary",
    "G_unclassifiable_no_full_text",
]

USE_VALUES = ["yes", "probably_yes", "unclear", "probably_no", "no"]
CONFIDENCE_VALUES = ["high", "medium", "low"]
