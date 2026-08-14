# Task 6 report — `status --json`

## What was built

**Created `pipeline/status.py`** — `snapshot()` returns the spec §4.3 `status` result:
`repo`, `toolchain`, `lock`, `styles`, `photos[]`. Per photo: `stem`, `state`,
`delivery_id`, `ingested_at`, `review_revision`, `previews`, `preview_hashes`,
`stale_previews`, `adjustments`, `crops`, `expression_audit`, `published`.
Implemented verbatim from the brief's Step 3 code. Helpers: `_rel`, `_control`,
`_photo`, `_state_stamps`, `snapshot`.

**Modified `pipeline/publish.py`** — added `lock_status()` immediately after
`_lock_is_stale` (before `acquire_lock`), verbatim from the brief. Returns
`{"held", "stale", "pid"}`; a dead-PID lock reports `held: False, stale: True`
and the file is never unlinked.

**Modified `pipeline/__main__.py`** — the `status` subparser gains
`--json` (`action="store_true"`); the handler dispatches through a new
`_status_cmd(ns)`:

```python
def _status_cmd(ns):
    if not ns.json:
        return _status()
    from . import jsonio, status
    return jsonio.run_json(lambda: status.snapshot())
```

`status` and `jsonio` are imported lazily inside the handler, matching the
file's existing import style. The legacy `_status()` body is untouched.

**Created `tests/test_status.py`** — the brief's four tests, verbatim.

## Correctness properties, and how each is satisfied

- **Read-only / lock-free / side-effect-free.** `snapshot()` calls
  `manifest.load_readonly()`, never `load()`. Nothing in the path calls `mkdir`:
  `lock_status()` only stats and reads `run/driver.lock`; it does not create
  `run/` the way `acquire_lock()` does. Verified two ways — the brief's
  `test_snapshot_photo_fields_and_no_writes` compares every file's `st_mtime_ns`
  across the whole tree before and after, and a manual check (below) covers the
  harder case where `.manifest` is absent and the recovery branch runs.
- **One recipe load + one `gather_material` per photo.** `_photo` loads `rec`
  once and gathers `material` once; the fingerprint is computed from *that* rec
  via `recipe.fingerprint(stem, rec, material["style_hashes"],
  material["seed_hash"], material["lock"], material["lab"])`, and the same
  `material` dict is passed positionally to `provenance.review_revision` and
  `provenance.stale_styles`. No `{}` placeholders are passed anywhere.
- **Preview existence derives from the material snapshot.** `previews[style]` is
  set from `material["preview_hashes"][style] is not None` — the path is built
  only to be relativized, and no fresh `exists()` call is made, so `previews`
  and `preview_hashes` can never disagree.
- **Snapshot coherence.** `_state_stamps()` stamps every `recipes/*.yaml` plus
  `.manifest` (`None` when absent). If the stamps moved during assembly, the
  whole build is retried once after `time.sleep(0.1)`; the second attempt
  returns unconditionally.
- **Dead-PID lock.** `test_snapshot_reports_stale_lock` asserts both the
  `{"held": False, "stale": True, "pid": 999999}` shape and `lock.exists()`
  afterwards.
- **Legacy output unchanged.** `_status()` is byte-identical to before; only the
  dispatch in front of it changed. Confirmed by subprocess run (below) and by
  the pre-existing `test_cli_status_runs`, which still passes.

## Deviations from the brief

1. **CLI wiring shape.** The brief specified the behavior ("`status` subparser
   gains `--json`; handler: `--json` → `run_json(lambda: status.snapshot())`;
   else legacy `_status()`") but gave no code. I introduced the `_status_cmd(ns)`
   helper above rather than inlining a conditional in the lambda, so the
   `build_parser` line stays as terse as its neighbours.
2. **No `git add` / `git commit`.** The brief's Step 5 includes them; the team
   lead's instruction was "Do NOT run any git commands", which takes precedence.
   Only the pytest half of Step 5 was run. The four files are left uncommitted
   in the worktree.

Everything else — `publish.lock_status`, all of `pipeline/status.py` (including
the function-local `import json as _json` inside `_photo`), and all four tests —
is verbatim from the brief.

## Observations for the reviewer / Task 13 (not changed here)

- **Brief vs. spec §4.3 example, exposure fallback.** The spec's illustrative
  JSON shows `filmic` exposure as `{"value": null, "source": "style"}`, but the
  brief's `_control` returns `{"value": None, "source": "camera"}` when neither
  the sidecar nor the base style pins the key. The brief's prose is explicit
  about this ("when neither file pins it, source `camera`, value `None`"), so
  the brief's behavior is what shipped. The brief's tests never assert the
  un-pinned exposure case, so this is unverified by the suite. **The Task 13
  golden fixtures need to pick one of these deliberately** — I did not reconcile
  it toward the spec example.
- **Repeated base-style reads.** `_control` reloads
  `config/styles/{style}.pp3` for each (photo, style, control), i.e. up to
  8 reads per photo of the same 4 files. Correctness is unaffected; a
  per-snapshot cache is an available optimization if photo counts grow.
- **Coherence scope excludes sidecars and base styles.** `_state_stamps()`
  covers recipes and `.manifest` only. That matches the spec's wording ("re-stats
  the recipe/manifest files it read"), so it is intended, but it does mean an
  `adjustments` value can come from a sidecar written mid-snapshot without
  triggering the retry.
- **Benign `lock_status` race (verbatim from the brief).** If the lock file
  disappears between `exists()` and the reads, `pid` is `None` and
  `_lock_is_stale` returns `False`, so the result is
  `{"held": True, "stale": False, "pid": None}` for a lock that no longer
  exists. The next snapshot corrects it.
- **`Temperature` cast.** `int(value)` would raise `ValueError` (→ `INTERNAL`
  envelope) on a pp3 holding e.g. `Temperature=5650.0`. The spec types
  Temperature as an int, and RawTherapee writes it as one.

## Test evidence

New tests, first run (before implementation) — collection error, as expected:

```
ImportError: cannot import name 'status' from 'pipeline'
```

After implementation:

```
$ /Users/john/photo-edits/.venv/bin/python -m pytest tests/test_status.py -q
....                                                                     [100%]
4 passed in 0.22s
```

Full gate:

```
$ /Users/john/photo-edits/.venv/bin/python -m pytest tests/ -q
........................................................................ [ 34%]
........................................................................ [ 68%]
...................................................................      [100%]
211 passed in 15.03s
```

211 = the 207 pre-existing tests (all unmodified, all passing) + 4 new.

### Manual end-to-end check of the CLI wiring

Against a temp `PIPELINE_ROOT` holding one recipe and a `.manifest`
(script: `scratchpad/cli_check.py`):

- `python -m pipeline status` → rc 0, stdout exactly `P1: ingested\n`, stderr
  empty — legacy output byte-identical.
- `python -m pipeline status --json` → rc 0, **exactly one** stdout line, which
  parses as `{"ok": true, "result": {...}}` with result keys
  `lock, photos, repo, styles, toolchain` and photo keys matching §4.3.
  `filmic.temperature == {"source": "style", "value": 5650}`,
  `natural.temperature == {"source": "camera", "value": null}`,
  all `previews` null, `published` all null.
- With `run/driver.lock` = `999999`: `lock` reports
  `{"held": false, "pid": 999999, "stale": true}` and the lock file still
  exists afterwards.

### Manual check of the write-free recovery branch

The brief's no-writes test has `.manifest` present, so it never exercises
`load_readonly`'s `rebuild(persist=False)` path. Checked separately
(script: `scratchpad/recovery_check.py`) with a recipe on disk and no
`.manifest`:

```
manifest-recovery branch taken: True
tree unchanged (no writes, no mkdir): True
photos: ['P1']
state: ingested
```

`.manifest` was **not** created, and every path's mtime is unchanged — the
recovery branch is write-free too.

## Self-review of the diff

- Additive only. `pipeline/status.py` and `tests/test_status.py` are new;
  `publish.py` gains one function and changes no existing line; `__main__.py`
  changes only the two `status` subparser lines and adds `_status_cmd`.
  `pipeline/subject.py` was not touched (the brief excludes it).
- No existing test file was modified.
- `status.py` imports only `manifest, paths, pp3, provenance, publish, recipe,
  toolchain` plus stdlib `time` — no import cycle (`publish` imports only
  `paths`; `jsonio` imports `publish` but not `status`).
- `_wrap` still returns the right exit code around `run_json`: `run_json`
  returns 0 or 1 and swallows every `Exception` itself, and `fn(ns) or 0` maps
  `1 → 1`, `0 → 0`.
- `--json` reaches the handler as `ns.json` (argparse's default dest); the flag
  exists only on the `status` subparser, so no other subcommand's namespace
  changed.
- `jsonio.activate()` sets `sys.stdout = sys.stderr` process-wide and never
  restores it, so no in-process `cli.main(["status", "--json"])` test was added
  — it would leak the redirect into the rest of the suite. The brief's tests
  call `snapshot()` directly for this reason; the wiring is covered by the
  subprocess check above instead.

## Files

- `/Users/john/photo-edits/.claude/worktrees/json-interface/pipeline/status.py` (new)
- `/Users/john/photo-edits/.claude/worktrees/json-interface/pipeline/publish.py` (modified — `lock_status()` added)
- `/Users/john/photo-edits/.claude/worktrees/json-interface/pipeline/__main__.py` (modified — `status --json` wiring)
- `/Users/john/photo-edits/.claude/worktrees/json-interface/tests/test_status.py` (new)
