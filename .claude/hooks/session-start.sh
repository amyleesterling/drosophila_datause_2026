#!/bin/bash
# Installs the droso_audit package + dev/fulltext deps so tests and the
# pipeline work in Claude Code on the web sessions. Idempotent.
set -euo pipefail

# Web/remote sessions only; locals manage their own env.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-.}"

# Editable install with dev (pytest) + fulltext (PyMuPDF/pypdf/trafilatura)
# extras. Editable + 'install' (not 'ci') so the cached container reuses wheels.
python -m pip install --quiet -e ".[dev,fulltext]"

# cffi is required by pypdf's crypto fallback; the base image ships a broken
# system cryptography without it. Installing cffi makes the PDF fallback work.
python -m pip install --quiet cffi

# Make src/ importable for ad-hoc scripts that don't use the installed package.
echo 'export PYTHONPATH="${CLAUDE_PROJECT_DIR:-.}/src${PYTHONPATH:+:$PYTHONPATH}"' >> "$CLAUDE_ENV_FILE"
