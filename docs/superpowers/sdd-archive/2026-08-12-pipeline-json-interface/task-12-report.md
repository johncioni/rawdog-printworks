# Task 12 report — `run --stem` / `--force` + progress events

## What was built

### `pipeline/driver.py`

- **`process_all(stems=None, force=False, collect=None)`** — all three defaults
  reproduce today's behavior exactly. New helpers:
  - `_selected_stems(data, stems, collect)` — `stems=None` → `sorted(data["photos"])`;
    otherwise `sorted(requested & known)`, and (collect mode only) every
    requested-but-unknown stem appends a `NOT_FOUND` entry to `collect["failed"]`.
  - `_force_downgrade` / `_restore_forced` — force remembers `(state, artifacts)`
    for a selected `rendered`/`verified` stem, blanks `artifacts` and sets
    `approved` **in the in-memory `data` only** (no `manifest.save`), so the
    downgrade first reaches disk inside that stem's successful `_finish_verified`.
    A per-stem `finally` restores the remembered pair whenever `_finish_verified`
    did not persist — including the exception path — so a later stem's
    `manifest.save(data)` cannot carry a failed stem's downgrade to disk.
    `_UNSET` sentinel: a photo entry that had no `artifacts` key gets the key
    removed again on restore, not left as `{}`, so the manifest is byte-identical.
  - `collect` is initialized with all three keys (`setdefault`), so callers can
    pass a bare `{}`.
- **Per-stem failure isolation** — the loop's `except` is now
  `(RuntimeError, render.RenderError)`. Manual-assets keeps its legacy skip-print
  in both modes; when `collect is None` everything else is re-raised bare
  (byte-for-byte legacy, pinned by two regression tests); when `collect` is given
  it appends `{"stem", "code": "RENDER_FAILED", "message"}` and continues.
- **`_finish_verified(data, stem, collect=None)`** — appends
  `{"stem", "code": "VERIFY_FAILED", "message"}` on verify failure and
  `{"stem", "version", "artifact_count"}` on success. `_published_version(stem)`
  reads the `current` symlink with `os.readlink` (guarded by `is_symlink()`,
  returning `None` when nothing is published).
- **Events** (all `jsonio.emit`, no-ops outside JSON mode): `_stage_event` emits
  `stage` for `preview` (top of the ingested branch), `render` (immediately before
  each of the four `render_photo` call sites), `verify` and `publish` (inside
  `_finish_verified`). The ingested branch emits per-style `progress`
  (1-based, `total=len(paths.STYLES)`, `detail=style`).
- **`render_photo`** — `_RenderProgress` emits one 1-based `progress` event per
  **requested** artifact as it lands in staging (TIF, native JPG, crop JPGs, PDFs,
  comparison sheet), `total=len(requested)`, `detail=<artifact filename>`. A style
  TIF rendered only as a dependency of a requested JPG is deliberately not counted,
  so `len(events) == total` holds for every `only=` subset.

### `pipeline/__main__.py`

- `run` gains `--stem` and `--force`; dispatch stays `mutating=False`
  (`process_all` still takes the lock itself).
- `_run_cmd`: JSON path seeds `result = {"published": [], "advanced": [], "failed": []}`,
  calls `process_all(stems={ns.stem} if ns.stem else None, force=ns.force, collect=result)`,
  maps an escaping `RuntimeError` to `CommandError("TOOLCHAIN_FAILED", str(e))`, and
  raises `CommandError("PARTIAL_FAILURE", f"{len(failed)} of {total} photos failed",
  result=result)` when anything failed.

## Deviations from the brief (and why)

1. **Legacy path forwards `--stem`/`--force`** instead of calling `process_all()`
   bare. Taking the brief literally would make `run --stem P1` (without `--json`)
   silently process *every* photo — a harmful surprise. With no flags the call is
   `process_all(stems=None, force=False)`, i.e. the signature defaults, which the
   Step-4 regression test pins as identical to legacy.
   `test_run_legacy_passes_no_scoping_and_no_collect` asserts the no-flag argv
   forwards `stems=None, force=False, collect=None`.
2. **`n` in the PARTIAL_FAILURE message** = `len(published) + len(advanced) + len(failed)`
   ("photos that produced an outcome"). It is the only value computable in
   `__main__` and matches the spec's `"1 of 3 photos failed"` example. Photos that
   stop at "awaiting visual review" produce no entry and so are not counted.
3. **`detail` on render progress is the artifact filename** (`"P1_natural_8x10.jpg"`),
   per the brief. `docs/superpowers/specs/2026-08-12-macos-app-design.md:98` shows
   an illustrative `"filmic 8x10 tif"` instead — flagged here so Task 13's golden
   fixtures pin the filename form deliberately rather than by accident.
4. **`TOOLCHAIN_FAILED` maps any `RuntimeError` escaping `process_all`** (brief's
   letter, no message matching). Verified safe: `publish.LockError` subclasses
   `Exception`, not `RuntimeError`, so `run_json`'s `LOCK_HELD` handling is
   untouched — pinned by `test_run_json_reports_held_lock`, a subprocess test
   against a held lock.
5. **Extra tests beyond the brief's list** (see below) — the brief's force-failure
   shape ("manifest unchanged") passes even without the restore, because nothing
   saves after the failure. The added two-stem version is what actually
   discriminates.

## Test evidence

Full gate: `/Users/john/photo-edits/.venv/bin/python -m pytest tests/ -q`
→ **277 passed** (254 pre-existing, unmodified, + 23 new).

New in `tests/test_driver.py` (17): the brief's four verbatim tests
(`stem_scoping`, `force_rerenders_verified`, `collect_shapes`,
`render_photo_emits_progress_in_json_mode`), the Step-4 legacy regression guard
(`no_args_matches_legacy_flow`), plus
`without_collect_still_reraises`, `collect_isolates_failures_and_continues`
(3 stems: RenderError → VERIFY_FAILED → published, loop reaches all three),
`collect_keeps_legacy_manual_assets_skip`, `unknown_requested_stem_is_not_found`,
`force_failure_keeps_published_version` (P1 forced+fails, P2 succeeds and saves →
P1 still `verified` with its original artifacts on disk),
`force_verify_failure_keeps_published_version` (same guarantee via the
`_finish_verified`-returns-False path rather than a raising render),
`force_leaves_pre_approval_states_alone`, `emits_render_verify_publish_stages`,
`emits_preview_stage_and_per_style_progress`,
`finish_verified_reports_published_version_from_symlink` (real `current` → `v004`),
`render_photo_progress_names_every_requested_artifact` (29 events, indexes 1..29,
names == `manifest.artifact_names`), `render_photo_progress_counts_only_requested_artifacts`
(`only={P1_natural.jpg}` → exactly one event, `total=1`).

New in `tests/test_cli.py` (6): result-is-collect, `--stem`/`--force` forwarding,
legacy forwarding, PARTIAL_FAILURE carrying successes, TOOLCHAIN_FAILED,
LOCK_HELD survival (subprocess).

Verified failing first (Step 2): the new tests failed with
`TypeError: process_all() got an unexpected keyword argument` and
`SystemExit: 2` (unrecognized `--stem`) before implementation.

End-to-end smoke on a scratch repo (real subprocess, `PIPELINE_ROOT` set):
- `run --json` on an empty repo → `{"ok":true,"result":{"advanced":[],"failed":[],"published":[]}}`, exit 0
- `run --json --stem NOPE --force` → `PARTIAL_FAILURE`, `"1 of 1 photos failed"`, NOT_FOUND entry in `result`, exit 1
- `run` (legacy, no flags) → no stdout, exit 0

## Self-review

- Legacy call shapes preserved: `render_photo(stem)` for full renders and
  `render_photo(stem, only=stale)` for partial — existing tests monkeypatch it as
  a single-argument lambda, which any `only=None`-normalizing helper would break.
- `manifest.save` is never called for a forced downgrade before the stem succeeds;
  the `finally` restore covers both the continue and the re-raise paths.
- The verification-tool-drift branch (verified → rendered for all photos) is
  untouched by `stems` scoping, as today.
- `collect` mutation is append-only into pre-seeded lists; `_finish_verified`
  uses `setdefault` so it is safe when called directly with a bare dict.
- No git commands were run (per instruction); Step 5's commit is left to the lead.

## Files

- `/Users/john/photo-edits/.claude/worktrees/json-interface/pipeline/driver.py` (modified)
- `/Users/john/photo-edits/.claude/worktrees/json-interface/pipeline/__main__.py` (modified)
- `/Users/john/photo-edits/.claude/worktrees/json-interface/tests/test_driver.py` (modified)
- `/Users/john/photo-edits/.claude/worktrees/json-interface/tests/test_cli.py` (modified)
