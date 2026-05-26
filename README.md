# Drosophila Connectome Data-Use Audit

A reproducible pipeline that takes a spreadsheet of papers citing major
*Drosophila* connectome resources (**hemibrain, FAFB, FlyWire, MANC, FANC**)
and classifies which papers **actually use connectome data** versus those that
merely **cite the resource as background**.

The central distinction is **dependency**: if a paper's scientific or technical
claim would weaken or disappear without the connectome resource, it counts as
data use. If the citation is ornamental background, it does not.

---

## Quick start

```bash
# 1. Install (Python 3.11+). Core deps run the rules + outputs:
pip install -e .
# Full-text extraction + LLM are optional extras:
pip install -e ".[fulltext,llm]"

# 2. Configure secrets (Unpaywall email is required for OA lookups):
cp .env.example .env   # then edit

# 3. Run the first-milestone test (first 25 papers):
python -m droso_audit.run_all \
  --input data/input/droso_data_use.xlsx \
  --out outputs/test_25.xlsx \
  --use-llm \
  --max-records 25

# 4. Run the full dataset:
python -m droso_audit.run_all \
  --input data/input/droso_data_use.xlsx \
  --out outputs/droso_data_use_audit.xlsx \
  --use-llm \
  --max-records 0
```

`--max-records 0` means no limit. Drop `--use-llm` to run rules-only (no API
key needed). Add `--no-fetch` to skip the network and use only cached full text.

### Input

Provide the source spreadsheet in any of three ways:

```bash
python scripts/01_load_sheet.py --input data/input/droso_data_use.xlsx
python scripts/01_load_sheet.py --input data/input/droso_data_use.csv
python scripts/01_load_sheet.py --google-sheet-url "https://docs.google.com/spreadsheets/d/<ID>/edit"
```

For a Google Sheet the loader tries the `…/export?format=xlsx` endpoint. If the
sheet is private (401/403/HTML login page) it prints:

> Could not access Google Sheet programmatically. Please download as .xlsx and
> place at `data/input/droso_data_use.xlsx`

All original spreadsheet columns are preserved; the audit columns are appended.

---

## ⚠️ Network requirement (important)

This pipeline depends on public scholarly APIs and open-access full-text hosts:
OpenAlex, Crossref, Semantic Scholar, Unpaywall, Europe PMC / PMC, bioRxiv, and
publisher OA pages, plus `docs.google.com` for the sheet export.

**In a restricted sandbox** (e.g. Claude Code on the web with a locked-down
egress allowlist) these hosts return `403 host_not_allowed`, so metadata
enrichment and full-text fetch cannot run. The code handles this gracefully —
blocked hosts are caught, rows are marked `not_attempted` /
`G_unclassifiable_no_full_text`, and nothing crashes — but **to actually fetch
data you must run it in an environment with outbound access to those hosts**
(e.g. locally, or with a network policy that allows them).

The LLM classifier reaches `api.anthropic.com` (or OpenAI). It auto-detects the
provider from `ANTHROPIC_API_KEY` / `OPENAI_API_KEY`; with neither set the
pipeline runs rules-only.

---

## Pipeline stages

| Stage | Module | What it does |
|------:|--------|--------------|
| 1 | `io`, `normalize` | Load sheet; normalize DOIs/titles/IDs; dedupe |
| 2 | `metadata` | Enrich via OpenAlex → Crossref → Semantic Scholar → Europe PMC → Unpaywall |
| 2b | `citation_expansion` | Optional: expand citing papers from seed resource DOIs via OpenAlex |
| 3 | `fulltext` | Fetch PMC XML → publisher OA HTML → OA PDF → preprint PDF; record *why* |
| 4 | `extract_text` | Parse XML/HTML/PDF into sectioned text (PyMuPDF→pypdf, trafilatura→bs4) |
| 5 | `detect_resources` | Find resource/tool mentions with sentence-window evidence |
| 6 | `classify` | Deterministic rules + optional LLM, merged per decision table |
| 7 | `write_outputs` | Audited xlsx/csv, manual-review queue, inventories, evidence |
| 8 | `summarize` | `summary_counts.json` + human-readable `summary_counts.md` |

The integrated runner `python -m droso_audit.run_all` executes all stages in one
**resumable** pass — every API response, full-text artifact, and parsed-text
JSON is cached under `data/cache/`, so re-running skips completed work.

`scripts/01_load_sheet.py` and `scripts/02_enrich_metadata.py` are standalone
(02 supports `--expand-citations-from-seeds`). Because stages 3–7 share
per-record caches, `scripts/03..07` delegate to the integrated runner.

---

## Outputs (`outputs/`)

- `droso_data_use_audit.xlsx` / `.csv` — original columns + audit columns
- `summary_counts.json` / `summary_counts.md` — counts and strict/broad estimates
- `needs_manual_review.csv` — prioritized review queue
- `full_text_inventory.csv` — per-paper full-text status and source
- `evidence_snippets.csv` — every resource mention with its sentence window

### Classification scheme

`actually_uses_connectome_data`: `yes | probably_yes | unclear | probably_no | no`

`use_category`:

- `A` direct connectome data analysis
- `B` connectome-derived biological result
- `C` tool/method using a connectome dataset
- `D` reuses published stats/figures only
- `E` background citation only
- `F` review / perspective / commentary
- `G` unclassifiable (no full text)

**Estimates** (in the summary):

```
strict_data_use = A + C
broad_data_use  = A + B + C
weak/contextual = D
not_data_use    = E + F
unknown         = G + unclear
```

### Quality guarantees (enforced in code + tests)

1. No row is `yes` without an `evidence_quote` (auto-downgraded to `probably_yes`).
2. No `yes` when full text is unavailable unless the abstract explicitly states data use.
3. Low-confidence rows are flagged `manual_review_needed=yes`.
4. DOI URLs and bare DOIs dedupe to the same record.
5. Full-text artifacts are cached and reused.
6. API calls retry with exponential backoff (tenacity).
7. The pipeline resumes after interruption (per-record caches).

---

## Development

```bash
pip install -e ".[dev]"
pytest          # offline unit tests (normalize, detect, classify rules)
```

The seed resource papers used for mention detection and citation expansion are
defined in `src/droso_audit/config.py` (`SEED_PAPERS`).
