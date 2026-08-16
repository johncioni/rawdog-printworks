# Task 5 report — `driver.preview_photo` (atomic targeted preview with dims + provenance)

## What was built

**`pipeline/driver.py`**
- Imports: added `os`; added `provenance` to the package import list (both alphabetically placed in the existing lists).
- New `preview_photo(stem, style)` inserted directly after `_record_render_dims` (before `_crop_for`), implemented verbatim from the brief's Step 3 block. Order of operations: unknown-style `ValueError` → load recipe → resolve RAW and verify `_sha256(raw) == rec["raw_sha256"]` (same message pattern as `render_photo`) → pre-render `material = provenance.gather_material(stem)` / `inputs_hash = provenance.style_input_hash(stem, style, rec, material)` → render to `run_dir()/preview-{stem}-{style}.tmp.jpg` with the same denoise-profile handling as `render_photo` → post-render re-hash of the inputs and `RuntimeError("render inputs changed during preview render …")` on mismatch (temp discarded) → always `_dims(tmp)` with the ±16 guard, recording render dims into `rec` only when not already recorded → `provenance.record_preview(rec, stem, style, tmp, inputs_hash)` → `recipe.save(stem, rec)` → `final.parent.mkdir` → `os.replace(tmp, final)` → return `final`.
- `process_all` ingested branch: `render.preview(stem, style)` → `preview_photo(stem, style)` (declared additive exception (b)). This is the only line changed in `process_all`.

**`pipeline/__main__.py`**
- `preview` subparser: positionals became `nargs="?"`, and `--stem`/`--style` flag aliases were added (`dest="stem_flag"` / `dest="style_flag"`), per the brief's contract note. The handler now calls `driver.preview_photo(*_preview_target(ns))` and still `print`s the returned path.
- New module-level helpers `_resolve(name, flag_value, positional)` and `_preview_target(ns)`. `_resolve` raises `jsonio.CommandError("BAD_INPUT", …)` when a value is missing (`missing stem`) or supplied both ways (`stem given both positionally and as --stem`). `jsonio` is imported lazily inside `_resolve`, matching the file's existing lazy-import style, so module import behavior is unchanged.

**`tests/test_driver.py`** — appended `_seed_preview_repo` plus the four verbatim tests from the brief, and the two additional scenarios named in the brief's Step 3 parenthetical: `test_preview_photo_passes_denoise_profile_when_overridden` (fake `rt_render` receives exactly `(render.denoise_profile(),)`) and `test_preview_photo_dims_failure_leaves_preview_and_recipe` (a `_dims` failure on the temp leaves both the previous preview file and the recipe bytes unchanged).

**`tests/test_cli.py`** — added coverage for the new argument contract: three parametrized argv forms (legacy positional, fully flagged, mixed `P1 --style natural`) all reach `driver.preview_photo("P1", "natural")` and print the returned path; four rejection forms (missing style, missing style with `--stem`, stem given both ways, style given both ways) return exit 1, never call `preview_photo`, and write `error: …` to stderr.

## Deviations from the brief

- **No git commands run** (brief Step 5 lists `git add`/`git commit`). The task instruction "Do NOT run any git commands" overrides the brief; nothing is staged or committed.
- **CLI tests added beyond the brief's list.** The brief only specifies `tests/test_driver.py` additions, but the flag/positional resolution is new user-visible behavior with an error contract, so it is covered directly.
- **Helper naming/placement.** The brief sketches the resolution inline (`stem = ns.stem_flag or ns.stem`); the `or` idiom cannot distinguish "given both ways", so the check is factored into `_resolve`, applied independently per value. Independence is deliberate: `preview P1 --style natural` is accepted, since the brief's "both ways" condition is per value, not per command.

## Behavior-change note (not a deviation, worth flagging)

`pipeline preview` with missing arguments now exits **1** with `error: missing stem` on stderr, where argparse previously exited **2** with a usage message. This follows inherently from the brief's mandated `nargs="?"` positionals — argparse can no longer enforce arity — and routes the failure through the `BAD_INPUT` contract instead. Verified in a real process: `python -m pipeline preview` → `error: missing stem`, exit 1.

## Existing-test updates

**None were required.** Grep confirmed no existing test asserts `render.preview` is called from `process_all`, and no existing test exercises the `ingested` branch at all (the `process_all` tests all seed explicit `preview_ready`/`approved`/`verified`/`rendered` states). `render.preview` itself is untouched and its `tests/test_render.py` coverage still passes unchanged. Declared exception (b) therefore cost zero test edits.

## Test evidence

```
baseline (before any change):  194 passed in 15.17s

after tests appended, before implementation:
  pytest tests/test_driver.py -q -k preview_photo
  → 6 failed, 21 deselected
    AttributeError: module 'pipeline.driver' has no attribute 'preview_photo'
    (all six failed on the missing function, not on a fixture error)

after implementation:
  pytest tests/test_driver.py -q  → 27 passed in 0.89s
  pytest tests/test_cli.py -q     → 8 passed in 0.71s
  pytest tests/ -q                → 207 passed in 12.64s   (final rerun: 207 passed in 12.81s)
```

207 = 194 baseline + 6 new driver tests + 7 new CLI cases (3 accept + 4 reject). No pre-existing test changed, was skipped, or was deleted.

## Self-review of the diff

- **`provenance` shadowing looks alarming but is inert.** `_publish_photo` has a local `provenance = {...}` dict. Because it is assigned there, `provenance` is local to that function for its whole body, and the function never references the module — so the new module-level `from . import provenance` cannot affect it. No behavior change; left as-is to keep unrelated code byte-for-byte identical.
- **No import cycle.** `pipeline.provenance` imports `labprofile, paths, recipe, render, toolchain` and never `driver`, so `driver → provenance` is acyclic. Full suite import passes confirm this.
- **Failure atomicity re-checked against each exit path.** RAW mismatch, `rt_render` raising, post-render input mismatch, `_dims` raising, and the ±16 guard all return before `recipe.save`, so both the previous JPG and the recipe bytes are untouched — the last three are asserted by tests. The only surviving window is between `recipe.save` and `os.replace`; there the recorded content hash is the temp's, which does not match `final`, so `provenance.stale_styles` reports the style stale rather than fresh, as the brief requires.
- **Recorded content hash is the temp's bytes**, which `os.replace` makes byte-identical to `final`; the atomic test asserts `rec["previews"]["natural"]["content"] == provenance.content_hash(out)` reading the *final* path, which passes.
- **`tmp.unlink(missing_ok=True)` before rendering** prevents a leftover temp from a previously crashed run being mistaken for this run's output if `rt_render` fails to write.
- **Real material dicts everywhere.** Both `style_input_hash` calls receive a gathered `material`, never `{}` — the `material or gather_material(stem)` idiom would silently re-gather on a falsy value, defeating the point of the pre/post snapshot comparison.
- **`preview_photo` does not check `rec["manual_assets"]`** (unlike `render_photo`). The brief's contract does not include it and previews precede approval/manual-asset territory; flagging in case a later task wants that guard.
- **`render.preview` left in place**, still exercised by `tests/test_render.py`. Only its two former callers (`process_all`, the CLI handler) now route through `preview_photo`; the `render` import in `build_parser` was kept even though it is now unused there, consistent with the already-unused `manifest`/`ingest` imports on that line and to avoid touching unrelated bytes.
- **No typecheck/lint gate exists in this repo** (`requirements-dev.txt` is pytest + pyyaml + pyobjc; no flake8/mypy/ruff config, no Makefile), so the full pytest run is the complete gate.

## Files modified

- `/Users/john/photo-edits/.claude/worktrees/json-interface/pipeline/driver.py`
- `/Users/john/photo-edits/.claude/worktrees/json-interface/pipeline/__main__.py`
- `/Users/john/photo-edits/.claude/worktrees/json-interface/tests/test_driver.py`
- `/Users/john/photo-edits/.claude/worktrees/json-interface/tests/test_cli.py`
