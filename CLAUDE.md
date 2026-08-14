# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

RAWdog Printworks: a resumable RAW → print-ready photo pipeline (Python) that turns Panasonic GH7 `.rw2` files into TIF/JPG/PDF output sets (22 files per photo, 3 styles × 3 crops). There is no README — the canonical reference is the design spec at `docs/superpowers/specs/2026-08-11-raw-print-pipeline-design.md`.

## Commands

All commands run through the repo `.venv` (pyobjc Vision/Quartz deps, macOS-only) — never system python.

```bash
scripts/process.sh <cmd>              # wraps .venv/bin/python -m pipeline
# subcommands: status | ingest | preview <stem> <style> |
#   croppreview <stem> <style> <crop> | approve <stem> |
#   render <stem> | verify <stem> | run

.venv/bin/python -m pytest tests/ -q                    # full quality gate (171 tests)
.venv/bin/python -m pytest tests/test_render.py -q      # one module
.venv/bin/python -m pytest tests/ -q -k <pattern>       # one test
```

Run the full pytest gate before reporting any task complete.

`scripts/orca-setup.sh` bootstraps a checkout for the Orca ADE (per-worktree `.venv` + dev deps, self-heals a venv broken by a moved checkout, warns on missing render tools). Orca runs it as the repo setup hook on new worktrees; it is also safe to run manually in any checkout.

## Architecture

**Per-photo state machine** (driver.py / manifest.py):

```
ingested → preview_ready → review_required → approved → rendered → verified
```

Approval is recorded as an **approval fingerprint** — a hash over every input that can change rendered pixels (RAW SHA-256, style sidecars, crop geometry, sharpening recipe, RawTherapee seed, rendering entries of `config/toolchain.lock`, lab-profile review fields). If any fingerprinted input changes later, the photo transitions **backward** to `review_required`; nothing is published that wasn't visually approved in its exact current form. The driver is resume-safe: re-running advances each photo from its current state, including backward transitions.

**Atomic publication** (publish.py): renders go to `staging/<stem>.tmp/`, then rename into immutable `Output/photos/<stem>/vNNN/`, then the `current` symlink is swapped atomically. `Output/TIF|JPG|PDF/` are derived symlink views — regenerated idempotently, outside the atomicity guarantee. Startup recovery resolves orphaned staging dirs and unpruned versions from manifest/provenance state.

**Rendering engine**: RawTherapee CLI is primary — chosen because its `.pp3` profiles are plain text, enabling precise per-image tuning. Base style profiles live in `config/styles/` (`natural`, `filmic`, `bw`, plus `vibrant`); per-image overrides in `sidecars/`. Tool versions are pinned in `config/toolchain.lock`.

**Mutating commands take the driver lock** (non-reentrant O_EXCL); `status` is read-only.

**Committed durable state vs gitignored working state:**

- Committed: `recipes/` (per-photo recipes incl. approval fingerprints and crop geometry), `sidecars/`, `config/` (lab profiles, styles, RawTherapee seed, toolchain.lock), `docs/`.
- Gitignored but **live photo data, not scratch**: `Input/`, `Output/`, `archive/` (verbatim RAWs + SHA-256 manifest), `staging/`, `run/`, `previews/`, `.manifest`. Never delete or "clean up" these casually.

## Active work

Two approved implementation plans in `docs/superpowers/plans/`: `2026-08-12-pipeline-json-interface.md` (Plan 1, adds a `--json` NDJSON command interface to the pipeline) and `2026-08-12-printworks-app.md` (Plan 2, macOS SwiftUI app driving that interface). Plan 1's Task 13 fixtures gate Plan 2. When executing Plan 1, its "Global Constraints" section is binding (additive-only CLI changes, lock discipline at dispatch, JSON stdout rules).
