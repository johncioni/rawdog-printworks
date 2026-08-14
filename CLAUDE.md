# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

RAWdog Printworks: a resumable RAW → print-ready photo pipeline (Python) that turns Panasonic GH7 `.rw2` files into TIF/JPG/PDF output sets (22 files per photo, 3 styles × 3 crops). There is no README — the canonical reference is the design spec at `docs/superpowers/specs/2026-08-11-raw-print-pipeline-design.md`.

## Commands

All commands run through the repo `.venv` (pyobjc Vision/Quartz deps, macOS-only) — never system python.

```bash
scripts/process.sh <cmd>              # wraps .venv/bin/python -m pipeline
# subcommands: status | ingest [--from <paths> --delivery-id <id>] |
#   preview <stem> <style> | croppreview <stem> <style> <crop> |
#   crops --stem <stem> | approve <stem> [--review-file <path>] |
#   adjust --stem <stem> --style <style> [--temperature|--exposure|--reset] |
#   render <stem> | verify <stem> | run [--stem <stem>] [--force]
# most commands also take --json (NDJSON on stdout, envelope last) —
#   see docs/superpowers/specs/2026-08-12-macos-app-design.md §4.2-4.3

.venv/bin/python -m pytest tests/ -q                    # full quality gate (290 tests)
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

Plan 1 (`docs/superpowers/plans/2026-08-12-pipeline-json-interface.md`) is **implemented**: the pipeline exposes the additive `--json` NDJSON interface, and the golden contract fixtures in `tests/fixtures/json_contract/` are the authority for it — Plan 2 must match those bytes, not this prose.

Next up is Plan 2 (`docs/superpowers/plans/2026-08-12-printworks-app.md`), the macOS SwiftUI app driving that interface. Its binding constraints live in the plan's "Global Constraints" section: no pipeline logic in Swift, no repo writes from Swift, argv-only subprocess invocation.

Two contract details that have bitten before: the approval fingerprint is bare hex while `review_revision` carries a `sha256:` prefix, and `approve` without `--review-file` returns an empty result.
