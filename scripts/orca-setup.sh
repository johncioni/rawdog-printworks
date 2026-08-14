#!/bin/bash
# Orca worktree setup for RAWdog Printworks.
#
# Run by Orca's repo setup hook on every new worktree (configured in Orca:
# repo settings -> hooks -> setup: "bash scripts/orca-setup.sh"). Idempotent
# and safe to re-run in any checkout, including the main one.
#
# What it does:
#   1. Creates .venv (gitignored, per-checkout) and installs requirements-dev.txt.
#      A venv whose interpreter path no longer resolves (checkout moved or
#      copied) is detected and rebuilt.
#   2. Smoke-checks that the test suite imports and collects.
#   3. Warns (never fails) about missing system render tools -- code and test
#      work doesn't need them; real renders do.
#
# Live photo data (Input/, Output/, archive/, .manifest, ...) is gitignored
# and exists only in the main checkout. Worktrees are for code + tests;
# pipeline runs against real photos happen in the main checkout.
set -euo pipefail
cd "$(dirname "$0")/.."

PYTHON=${PYTHON:-python3}

# Rebuild the venv if its interpreter is gone (e.g. the checkout was moved:
# venv scripts embed absolute paths).
if [ -d .venv ] && ! .venv/bin/python -c 'import sys' >/dev/null 2>&1; then
    echo "orca-setup: .venv interpreter broken; rebuilding"
    rm -rf .venv
fi
# Same if the entry-point shebangs point at a stale absolute path.
if [ -f .venv/bin/pytest ] && ! head -1 .venv/bin/pytest | grep -q "^#!$PWD/"; then
    echo "orca-setup: .venv built for a different path; rebuilding"
    rm -rf .venv
fi

if [ ! -d .venv ]; then
    echo "orca-setup: creating .venv with $($PYTHON --version)"
    "$PYTHON" -m venv .venv
fi

echo "orca-setup: installing dev requirements"
.venv/bin/python -m pip install --quiet --upgrade pip
.venv/bin/python -m pip install --quiet -r requirements-dev.txt

echo "orca-setup: collecting test suite (import smoke check)"
.venv/bin/python -m pytest tests/ -q --collect-only >/dev/null
echo "orca-setup: test suite collects OK ($(.venv/bin/python -m pytest tests/ -q --collect-only 2>/dev/null | tail -1))"

# Render toolchain (warn-only; see config/toolchain.lock for pinned versions).
RT_CLI="/Applications/RawTherapee.app/Contents/MacOS/rawtherapee-cli"
[ -x "$RT_CLI" ] || echo "orca-setup: WARNING: rawtherapee-cli not found at $RT_CLI"
for tool in exiftool magick img2pdf qpdf pdfimages; do
    command -v "$tool" >/dev/null || echo "orca-setup: WARNING: $tool not on PATH (brew install)"
done

echo "orca-setup: done. Quality gate: .venv/bin/python -m pytest tests/ -q"
