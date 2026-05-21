"""Spreadsheet loading (local xlsx/csv or Google Sheet export)."""
from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import Optional

import pandas as pd

from .config import INPUT_DIR
from .httpc import HostNotAllowed, get_bytes


GOOGLE_SHEET_ID_RE = re.compile(r"/spreadsheets/d/([a-zA-Z0-9-_]+)")

DOWNLOAD_HINT = (
    "Could not access Google Sheet programmatically. "
    "Please download as .xlsx and place at data/input/droso_data_use.xlsx"
)


def sheet_id_from_url(url: str) -> Optional[str]:
    m = GOOGLE_SHEET_ID_RE.search(url)
    return m.group(1) if m else None


def load_from_google_sheet(url: str, *, save_to: Optional[Path] = None) -> pd.DataFrame:
    """Attempt to download a Google Sheet via the xlsx export endpoint."""
    sid = sheet_id_from_url(url)
    if not sid:
        raise ValueError(f"Could not parse Google Sheet id from URL: {url}")
    export_url = f"https://docs.google.com/spreadsheets/d/{sid}/export?format=xlsx"
    try:
        content = get_bytes(export_url)
    except HostNotAllowed:
        print(DOWNLOAD_HINT, file=sys.stderr)
        raise
    if not content or content[:4] not in (b"PK\x03\x04",):  # xlsx is a zip
        # Likely an HTML login/permission page.
        print(DOWNLOAD_HINT, file=sys.stderr)
        raise PermissionError(DOWNLOAD_HINT)
    save_to = save_to or (INPUT_DIR / "droso_data_use.xlsx")
    save_to.parent.mkdir(parents=True, exist_ok=True)
    save_to.write_bytes(content)
    return pd.read_excel(save_to)


def load_input(input_path: Optional[str] = None, google_sheet_url: Optional[str] = None) -> pd.DataFrame:
    """Load the input sheet from a local file or a Google Sheet URL."""
    if input_path:
        p = Path(input_path)
        if not p.exists():
            raise FileNotFoundError(f"Input file not found: {p}")
        if p.suffix.lower() in (".xlsx", ".xls"):
            df = pd.read_excel(p)
        elif p.suffix.lower() == ".csv":
            df = pd.read_csv(p)
        else:
            raise ValueError(f"Unsupported input extension: {p.suffix}")
        return df
    if google_sheet_url:
        return load_from_google_sheet(google_sheet_url)
    # Fall back to default local locations.
    for cand in (INPUT_DIR / "droso_data_use.xlsx", INPUT_DIR / "droso_data_use.csv"):
        if cand.exists():
            return load_input(str(cand))
    raise FileNotFoundError(
        "No input provided. Pass --input <file>, --google-sheet-url <url>, "
        f"or place droso_data_use.xlsx/csv in {INPUT_DIR}"
    )
