# CLAUDE.md — Project memory / handoff

## What this project is
A reproducible Python pipeline that takes a spreadsheet of papers citing major
*Drosophila* connectome resources (**hemibrain, FAFB, FlyWire, MANC, FANC**) and
classifies which papers **materially use connectome data** vs. those that
**merely cite the resource as background**. Core test: if the paper's claim would
weaken/disappear without the connectome resource → data use; if the citation is
ornamental background → not data use.

Owner's goal (from README): "figure out how many papers have actually used
drosophila connectomics data vs just citations."

## Current status (as of 2026-05-26)
- Full pipeline is **built, committed, and pushed** to branch
  `claude/droso-connectome-audit-bpH12`.
- **Draft PR #1** open against `main`:
  https://github.com/amyleesterling/drosophila_datause_2026/pull/1
- 23 offline unit tests pass (`pytest`).
- A SessionStart hook installs deps automatically in web sessions
  (`.claude/hooks/session-start.sh`, registered in `.claude/settings.json`).

## ⚠️ The main blocker: network
This sandbox's egress allowlist **blocks every scholarly API + Google Sheets**
(`403 host_not_allowed`): OpenAlex, Crossref, Semantic Scholar, Unpaywall,
Europe PMC, publisher OA hosts, and `docs.google.com`. Only GitHub, PyPI, and
`api.anthropic.com` are reachable.

Consequence: **live metadata enrichment and full-text fetch cannot run inside
this web container.** The code degrades gracefully (blocked rows →
`G_unclassifiable_no_full_text` / manual review; no crashes), but to actually
fetch data you must either:
1. **Run locally** (your machine can reach the APIs), or
2. **Recreate the web environment with a network policy that allows those hosts.**

The Google Sheet (`https://docs.google.com/spreadsheets/d/1-vlym4VTBgIgNRmTumiftprQ3jNp-z_Ow5pwxS2y3IQ/edit`)
must be downloaded as `.xlsx` to `data/input/droso_data_use.xlsx`, OR fetched via
`--google-sheet-url` once `docs.google.com` is reachable.

## How to run
```bash
pip install -e ".[fulltext,llm]"   # or ".[dev]" for tests only
cp .env.example .env               # set UNPAYWALL_EMAIL (required) + optional keys

# First-milestone test (25 papers):
python -m droso_audit.run_all --input data/input/droso_data_use.xlsx \
  --out outputs/test_25.xlsx --use-llm --max-records 25

# Full run:
python -m droso_audit.run_all --input data/input/droso_data_use.xlsx \
  --out outputs/droso_data_use_audit.xlsx --use-llm --max-records 0
```
- `--use-llm` is optional; without an API key it runs rules-only.
- `--no-fetch` uses only cached full text (skips network).
- The run is **resumable** — everything caches under `data/cache/`.

## Architecture (`src/droso_audit/`)
- `config.py` — paths, env settings, seed papers, column schema.
- `io.py` — load local xlsx/csv or Google Sheet export.
- `normalize.py` — DOI/title/PMID/PMCID/OpenAlex normalization + dedupe. (tested)
- `metadata.py` — OpenAlex→Crossref→Semantic Scholar→Europe PMC→Unpaywall, merged.
- `citation_expansion.py` — optional OpenAlex `cites:` expansion from seed DOIs.
- `fulltext.py` — fetch PMC XML→OA HTML→OA PDF→preprint PDF; records why.
- `extract_text.py` — JATS XML / HTML (trafilatura→bs4) / PDF (pymupdf→pypdf) → sections.
- `detect_resources.py` — resource/tool mention detection + sentence windows. (tested)
- `classify.py` — deterministic rules + optional LLM (Anthropic or OpenAI,
  auto-detected) + merge logic. (tested)
- `evidence.py` — build evidence-snippet rows + LLM evidence windows.
- `summarize.py` — summary_counts.json/.md with strict/broad estimates.
- `write_outputs.py` — audited xlsx/csv, manual-review queue, inventories.
- `run_all.py` — integrated resumable runner (CLI entry: `python -m droso_audit.run_all`).
- `httpc.py` — shared HTTP session: retry/backoff (tenacity) + disk cache;
  raises `HostNotAllowed` when the egress proxy blocks a host.

`scripts/01..08` mirror the stages; 01 (load) and 02 (enrich, supports
`--expand-citations-from-seeds`) are standalone, 03–07 delegate to `run_all`
because they share per-record caches, 08 rebuilds the summary.

## Outputs (`outputs/`)
`droso_data_use_audit.xlsx`/`.csv`, `summary_counts.json`/`.md`,
`needs_manual_review.csv`, `full_text_inventory.csv`, `evidence_snippets.csv`.
All original spreadsheet columns are preserved; audit columns appended (see
`ADDED_COLUMNS` in `config.py`).

## Classification scheme
`actually_uses_connectome_data`: yes | probably_yes | unclear | probably_no | no
`use_category`: A direct analysis · B connectome-derived biological result ·
C tool/method using dataset · D reuses published stats/figures · E background
citation only · F review/perspective · G unclassifiable (no full text).
Estimates: strict = A+C, broad = A+B+C, weak = D, not-use = E+F, unknown = G+unclear.

### Hard quality rules (coded + tested)
1. No `yes` without an `evidence_quote` (auto-downgraded to `probably_yes`).
2. No `yes` without full text unless the abstract explicitly states data use.
3. Low confidence → `manual_review_needed=yes`.
4. DOI URL and bare DOI dedupe to the same record.
5. Full-text artifacts cached + reused; API calls retried with backoff; resumable.

## Next steps / TODO
- [ ] Get the input data in: download the Google Sheet to
      `data/input/droso_data_use.xlsx` (sheet is private to the sandbox).
- [ ] Run the 25-paper milestone in a network-enabled environment.
- [ ] Inspect `needs_manual_review.csv`; tune `STRONG_YES_PATTERNS` /
      `BACKGROUND_PATTERNS` in `classify.py` against real false pos/neg.
- [ ] Scale to the full ~2,000 papers; consider citation expansion from seeds.
- [ ] Optionally add publisher-specific OA HTML handling for big sources (eLife,
      Nature, Cell) in `fulltext.py`.

## Env / keys (.env)
`UNPAYWALL_EMAIL` (required for OA lookups), `OPENALEX_MAILTO`/`CROSSREF_MAILTO`
(polite pool), `SEMANTIC_SCHOLAR_API_KEY`, `NCBI_EMAIL`/`NCBI_API_KEY`, and one of
`ANTHROPIC_API_KEY` (preferred) or `OPENAI_API_KEY` for LLM classification.
