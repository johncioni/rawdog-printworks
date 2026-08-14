# Task 9 report — `crops` command

## What was built

**`pipeline/driver.py`**
- Added `jsonio` to the package import tuple (alphabetical position; `jsonio`
  imports only `publish`, which `driver` already imports, so no cycle).
- New `crop_windows(stem)` placed immediately above `approve` (driver.py:400).
  Implemented verbatim from the brief, plus a two-line docstring stating the
  `basis`/`source` split (the one contract point a reader cannot see from the
  code: why a fully persisted recipe reports `basis: None` rather than
  inventing a `"persisted"` basis value).

  Behaviour:
  - All windows persisted → `{"stem", "basis": None, "windows": {crop:
    {...window, "source": "persisted"}}}`; the detector is never called and
    `_render_dims` is never consulted.
  - Otherwise `_render_dims(rec)` is required; its `ValueError` is re-raised as
    `jsonio.CommandError("BAD_INPUT", "render dims not recorded; generate
    previews first")`.
  - Natural preview present → `subject.group_bbox_detail`: `"faces"` →
    subject-centered windows, basis `"faces"`; `"no_faces"` → centered windows,
    basis `"center"`; `"detector_error"` → centered windows, basis
    `"detector_error"`. Preview missing → centered windows, basis `"center"`.
  - Persisted windows are carried through untouched with `source: "persisted"`
    even when other windows are suggested.
  - Nothing is written: no `recipe.save`, no manifest write, no lock.

**`pipeline/__main__.py`**
- New `crops` subcommand: `--stem` required, `--json` optional, dispatched via
  the generalized `_dispatch(ns, _crops_cmd, mutating=False)` with no precheck.
  A comment records why it is non-mutating.
- New `_crops_cmd(ns)` following the `_status_cmd`/`_preview_cmd` shape: it
  imports `driver` at call time (so `monkeypatch.setattr(driver,
  "crop_windows", ...)` is observed), returns the result dict under `--json`,
  and otherwise pretty-prints `json.dumps(result, indent=2, sort_keys=True)`
  and returns `None` → exit 0 through `_wrap`.
- `FileNotFoundError` from `recipe.load` on an unknown stem already maps to
  `NOT_FOUND` through `_dispatch`'s adapters, and to `error: …` + exit 1 in the
  legacy path; no extra handling was added.

**`tests/test_driver.py`** — the brief's three tests verbatim, plus four:
`test_crop_windows_all_persisted_reports_no_basis`,
`test_crop_windows_mixes_persisted_and_suggested`,
`test_crop_windows_requires_dims_when_one_window_persisted`,
`test_crop_windows_without_preview_is_centered`.

**`tests/test_cli.py`** — three wiring tests: `test_crops_json_returns_windows`,
`test_crops_legacy_pretty_prints_result`, `test_crops_never_locks`.

## Deviations and reasons

1. **No git commit** (brief Step 5 says `git add` + `git commit`). The
   dispatching instruction said explicitly "Do NOT run any git commands", so no
   git command was run at all. The three source files are left modified in the
   worktree for the lead to commit.
2. **Seven extra tests beyond the brief's three.** The lead's contract calls out
   the all-persisted (`basis` null) and mixed persisted+suggested paths, which
   the brief's three tests do not exercise, and the CLI wiring (non-mutating,
   `--stem` required, legacy pretty-print) was untested. Additive only.
3. **Docstring on `crop_windows` and a comment on the subcommand.** Two
   non-obvious contract points (`basis` is about suggestion only; `crops` must
   never take the driver lock) that the code alone does not state.

## Test evidence

New tests fail before the implementation:

```
$ /Users/john/photo-edits/.venv/bin/python -m pytest tests/test_driver.py \
    tests/test_cli.py -q -k "crop_windows or crops_"
10 failed, 2 passed, 41 deselected in 1.69s
```

After the implementation:

```
$ ... -k "crop_windows or crops_"
12 passed, 41 deselected in 1.80s
```

Full gate:

```
$ /Users/john/photo-edits/.venv/bin/python -m pytest tests/ -q
237 passed in 15.23s
```

227 pre-existing tests unmodified + 10 new. No existing test was edited.

Out-of-process smoke test against a scratch `PIPELINE_ROOT` (recipe with
`render_width/height` 5784x4344, no preview, no persisted crops):

- `pipeline crops --stem P1` → pretty-printed body, exit 0, basis `"center"`,
  both windows `source: "suggested"` (8x10 `w` 0.93879…, matching
  `centered_crop_norm` for a 1.331 aspect source at 1.25 target).
- `pipeline crops --stem P1 --json` → single NDJSON line
  `{"ok":true,"result":{...}}`, exit 0.
- `pipeline crops --stem NOPE --json` → `{"ok":false,"error":{"code":
  "NOT_FOUND",…}}`, exit 1.
- `pipeline crops --json` → argparse usage error (`--stem` required).
- The recipe on disk still had `crops: {5x7: null, 8x10: null}` after all of
  the above — nothing persisted.

## Self-review

- Read the final text of both changed source regions after editing. No leftover
  scaffolding, no duplicated blocks, import ordering preserved.
- `crop_windows`'s loop variable `crop` does not shadow the module-level `crops`
  import in `driver.py`; the `crops` subcommand name does not collide with the
  existing `croppreview` subcommand (argparse does not abbreviate subcommand
  names).
- Confirmed rather than assumed: `_render_dims` is required as soon as **one**
  window is missing, even though another is persisted — the fall-through order
  in the brief's code makes this so, and
  `test_crop_windows_requires_dims_when_one_window_persisted` asserts it as
  intended behaviour rather than "fixing" it.
- `test_crop_windows_all_persisted_reports_no_basis` monkeypatches
  `group_bbox_detail` to raise, so the "no suggestion runs at all" claim is
  enforced, not merely implied by the returned basis.
- `test_crops_never_locks` runs the real CLI with a live-PID lock file held and
  asserts the failure is `NOT_FOUND` (missing recipe), not `LOCK_HELD` — proof
  the command bypasses the driver mutex.
- No linter is configured in this repo (`requirements-dev.txt` is pytest, pyyaml,
  pyobjc); pytest is the whole gate and it is green.

---

# Fix round 1 — recipe byte-identical assertion

## Finding addressed

Plan-mandated: no test asserted the recipe file is byte-identical after
`crop_windows`. Only `recipe.load(...)["crops"]` equality was checked.

## What changed (`tests/test_driver.py` only — no source change)

The mandated pattern was added to the two paths the review named plus the third
write path, capturing `(tmp_repo / "recipes/P1.yaml").read_bytes()` before the
call and asserting equality after:

- `test_crop_windows_suggests_with_basis` (suggestion path)
- `test_crop_windows_all_persisted_reports_no_basis` (all-persisted path)
- `test_crop_windows_mixes_persisted_and_suggested` (added as well: it is the
  third path `approve` would write on, filling the missing `5x7` window)

## Empirical finding: bytes alone do not catch a no-op re-save

The review's stated rationale — that a bytes assertion "would catch a future
regression that re-saves the file with unchanged content" — does not hold, and
this was verified rather than assumed. With `recipe.save(stem, rec)` temporarily
inserted at the top of `crop_windows`, all seven tests still passed:

```
$ /Users/john/photo-edits/.venv/bin/python -m pytest tests/test_driver.py -q -k crop_windows
7 passed, 27 deselected in 1.17s      # with the TEMP re-save in place
```

`recipe.save` emits `yaml.safe_dump(data, sort_keys=True)` — deterministic — so
a content-identical round-trip produces a byte-identical file. `read_bytes()`
compares content, not whether a write happened.

The bytes assertion is still correct and is kept exactly as mandated (it catches
any re-save that *changes* content, e.g. persisting a suggested window). It is
now paired with an identity check via a new `_recipe_state(tmp_repo)` helper
returning `(bytes, st_ino)`: `recipe.save`'s temp-file + `os.replace` always
lands a new inode, so a no-op re-save is detectable. With the same TEMP re-save
inserted, the strengthened tests fail as they should:

```
FAILED tests/test_driver.py::test_crop_windows_suggests_with_basis
FAILED tests/test_driver.py::test_crop_windows_all_persisted_reports_no_basis
FAILED tests/test_driver.py::test_crop_windows_mixes_persisted_and_suggested
3 failed, 4 passed, 27 deselected in 1.15s
```

The TEMP line was then removed (`grep -n TEMP pipeline/driver.py` → no matches);
`pipeline/driver.py` and `pipeline/__main__.py` are unchanged from the reviewed
version.

## Test evidence after the fix

Covering tests:

```
$ /Users/john/photo-edits/.venv/bin/python -m pytest tests/test_driver.py -q -k crop_windows
.......                                                                  [100%]
7 passed, 27 deselected in 0.69s
```

Full gate:

```
$ /Users/john/photo-edits/.venv/bin/python -m pytest tests/ -q
........................................................................ [ 30%]
........................................................................ [ 60%]
........................................................................ [ 91%]
.....................                                                    [100%]
237 passed in 17.06s
```

No git commands were run.
