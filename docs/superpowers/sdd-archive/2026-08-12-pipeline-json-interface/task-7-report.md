# Task 7 report — `adjust` command

## What was built

| File | Change |
| --- | --- |
| `pipeline/adjust.py` | **New.** `apply(stem, style, temperature=None, exposure=None, reset=False)` plus the ownership/reconcile helpers, implemented verbatim from the brief. |
| `pipeline/__main__.py` | **Modified, additive.** `import json` on line 1; `from . import adjust as adjust_mod` inside `build_parser`'s lazy-import block; the `adjust` subparser after `run`; module-level `_locked_json(ns, fn)`. No existing line changed. |
| `tests/test_adjust.py` | **New.** The brief's six tests verbatim, plus one added test (see Deviations). |

TDD order followed: tests written first, run to confirm failure (`ImportError: cannot import name 'adjust'`), then implementation, then green.

## Correctness properties (all gated ones verified)

- **`_reconcile` runs before every operation** and drops ownership of any bundle whose current pp3 values diverge from `last_written`. The drop is persisted through a separate `recipe_dirty` flag, so a reset that touches no sidecar still saves the recipe (`test_reset_restores_previous_and_skips_diverged` asserts `"wb" not in ...["vibrant"]` after a reset that left the hand-edited `4800` in place).
- **WB is an atomic triple.** `Setting`/`Temperature`/`Green` are captured, divergence-checked, and restored all-or-none through `_CONTROLS["wb"]`; no code path handles one of the three alone.
- **Reset restores `previous`**, removing keys whose captured value was `None`, and never touches a diverged bundle (`_reconcile` has already removed it, so `_reset_control` finds no entry and returns `False`).
- **Re-owning after divergence re-captures `previous` from the hand-edited value** — `test_adjust_after_divergence_recaptures_previous` writes 5600, hand-edits to 4800, writes 5200, and a later reset restores `4800`.
- **`remove_section_if_empty` after removals**, so no stranded `[White Balance]` header survives a reset.
- **The sidecar file is deleted only when the document is truly empty.** A comment-only file survives; verified empirically and now locked in by a test.
- **Write order is sidecar first, recipe second**, matching the spec §4.2 crash rule.
- **Render failure maps to `CommandError("RENDER_FAILED")`** with the sidecar retaining the user's values; only `render.RenderError` is adapted, so `preview_photo`'s `RuntimeError` guards still surface as `INTERNAL` per spec §7.
- **Real material to provenance.** `provenance.review_revision(stem, rec)` is called with no `material` argument, so it gathers fresh real material on each call — required, since `before` and `after` must each see their own `preview_hashes`. No `{}` is ever passed.

## Deviations from the brief

1. **No git commands** (brief Step 5 says `git add` / `git commit`). The lead's instruction to run no git commands overrides. Nothing is staged or committed.
2. **Absolute interpreter path** — `/Users/john/photo-edits/.venv/bin/python` instead of the brief's relative `.venv/bin/python`; this worktree has no local `.venv`.
3. **One test added** beyond the brief's six: `test_reset_keeps_comment_only_sidecar`. It exercises a property the review gates on that the brief's tests did not cover — a `render.ensure_sidecar` comment-only file must survive a reset (deleting it would change `style_hashes`) and must not retain a stranded `[White Balance]` header. Purely additive; the six brief tests are byte-for-byte as specified.

`pipeline/adjust.py` and the `__main__.py` snippets are otherwise verbatim from the brief.

## Test evidence

```
$ /Users/john/photo-edits/.venv/bin/python -m pytest tests/test_adjust.py -q   # before implementation
ImportError: cannot import name 'adjust' from 'pipeline'   → 1 error during collection

$ /Users/john/photo-edits/.venv/bin/python -m pytest tests/test_adjust.py -q   # after
6 passed in 2.43s

$ /Users/john/photo-edits/.venv/bin/python -m pytest tests/ -q                 # full gate
218 passed in 13.81s
```

211 pre-existing tests + 6 brief tests + 1 added test = 218. No existing test file was modified.

### CLI smoke test (out-of-tree scratch repo, fake renderer)

The unit tests call `adjust.apply` directly, so the subparser wiring was exercised separately:

- `adjust --stem P1 --style natural --temperature 5600` → exit 0, pretty-printed result.
- `--json` → single-line `{"ok":true,"result":{…}}` envelope, exit 0.
- `--temperature 12000 --json` → `{"ok":false,"error":{"code":"BAD_INPUT",…}}`, exit 1.
- `--stem NOPE --json` → `NOT_FOUND`, exit 1.
- `--reset --json` → exit 0; both controls restored, the app-created sidecar removed (it was truly empty), ownership left as `{'natural': {}}`.
- `run/driver.lock` verified absent after the success invocations; release on the `CommandError` path follows from `acquire_lock` being a contextmanager, and was not separately observed.

## Self-review notes and observations (no changes made)

These are known rough edges I deliberately left alone; all are Task 8's territory, and the brief states Task 8 must preserve `_locked_json`'s behavior.

1. **Non-JSON `adjust` errors print a traceback.** The subparser uses `_locked_json` directly rather than `_wrap`, so a `CommandError` in the plain path is uncaught. Matches the brief exactly; Task 8 generalizes dispatch.
2. **`_reconcile` raises `KeyError` on an unknown control name** in a hand-edited recipe's `app_adjustments`, surfacing as `INTERNAL` rather than a clean error. The control vocabulary is spec-fixed, so this is only reachable via hand-editing.
3. **argparse `type=int` exits 2** on `--temperature abc` before `adjust.apply`'s `BAD_INPUT` validation can run, so that one input class bypasses the JSON envelope.
4. **`_validate`'s `int()`/`float()` casts** would raise `ValueError` → `INTERNAL` on a non-numeric value reaching `apply` programmatically. Not reachable through the CLI.
5. **Whitespace residue after an adjust→reset round trip.** A comment-only sidecar comes back as `"# …\n\n"` rather than the original `"# …\n"`: `Pp3.set` inserts a blank separator line before a new section, and `remove_section_if_empty` deletes only the section span. The gated property (file survives, no stranded header) holds, but the file's bytes — and therefore `style_hashes` — do not return to their exact pre-adjust value. Fixing it means changing `pipeline/pp3.py`, which is Task 3's file and outside this task's additive-only scope. Nothing downstream breaks: the recipe's recorded `inputs` hash is recomputed at the reset's re-render, so the preview is not left falsely stale.
