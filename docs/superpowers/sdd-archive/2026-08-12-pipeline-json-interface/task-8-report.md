# Task 8 report: dispatch-level locking + `--json` plumbing + `group_bbox_detail`

**Status: DONE_WITH_CONCERNS** (two deviations that need controller acknowledgement, both listed below; nothing is failing).

## Files modified

- `pipeline/__main__.py` — generalized dispatch, lock model, `--json` flags, JSON bodies
- `pipeline/subject.py` — `group_bbox_detail`, `group_bbox` reduced to a thin wrapper
- `pipeline/adjust.py` — result dict factored out of `apply` into `preview_result`
- `tests/test_cli.py` — 8 additions
- `tests/test_subject.py` — 1 addition, 1 named refactor

No files created. No git commands run (per instruction); nothing is committed.

## What was built

### Dispatch and lock model (`pipeline/__main__.py`)

Three helpers replace the per-subcommand `_wrap(...)` wiring:

- `_locked(fn, mutating)` — body-builder that takes `publish.acquire_lock()` exactly once when
  `mutating`. Shared by `_dispatch` and `_locked_json`, so there is exactly one place in the CLI
  that acquires the lock.
- `_dispatch(ns, fn, mutating, precheck=None)` — the single dispatch point. In JSON mode it calls
  `jsonio.run_json(lambda: run() or {}, adapters=...)`; otherwise `_wrap`.
- `_locked_json(ns, fn)` — kept for `adjust`, now delegating to `_locked`. Its behaviour is byte-for-byte
  what Task 7 shipped: `run_json(body)` with **no adapters** in JSON mode, `print(json.dumps(..., indent=2,
  sort_keys=True))` + `return 0` in legacy mode, and no `_wrap` around the legacy path.

Lock assignment as decided by the controller:

| command | locked at dispatch | `--json` |
|---|---|---|
| `ingest`, `preview`, `croppreview`, `approve`, `render`, `verify`, `adjust` | yes | all but `croppreview`, `render` |
| `run` | **no** — `process_all` locks internally | yes |
| `status` | no | yes (pre-existing) |

`run` unwrapped was verified empirically, not just by reading: a manual smoke run of `pipeline run --json`
against a scratch repo reaches `process_all` and fails on toolchain drift rather than on `LockError`,
which is what wrapping it would have produced (the `O_EXCL` lock is not reentrant). Confirmed by grep that
`process_all` is the **only** self-locking callee in `pipeline/` — `ingest.run` and the render path take no
lock, so wrapping them is safe.

Adapters passed in JSON mode are exactly the three canonical codes specified:
`{render.RenderError: "RENDER_FAILED", ingest.IngestError: "BAD_INPUT", FileNotFoundError: "NOT_FOUND"}`.
No non-canonical code was introduced (the Task-1 finding that adapters bypass `CommandError`'s validation
still stands as a latent gap in `jsonio`, untouched here).

### JSON bodies

- **`verify --json`** gets its own body, never the legacy `_verify`: `driver.verify_photo(stem)`;
  problems → `jsonio.CommandError("VERIFY_FAILED", "; ".join(problems))`; clean →
  `{"stem": stem, "verify": "clean"}`.
- **`preview --json`** returns `adjust.preview_result(stem, style, revision_before)`. `revision_before` is
  sampled **before** `driver.preview_photo` runs, because the render is what moves the revision;
  `test_preview_json_returns_adjust_shaped_result` asserts `before != after` specifically so that sampling
  too late is caught.
- **`ingest --json`** — see Deviation 1.
- `approve --json` / `run --json` return `{}` for now; their results belong to Tasks 10 and 12.

### `subject.group_bbox_detail`

Body of `group_bbox` moved to `group_bbox_detail`, returning `(bbox, "faces")` on detection,
`(None, "no_faces")` on zero results, and `(None, "detector_error")` on **both** existing failure paths —
the `if not succeeded:` branch is a detector failure, not a no-faces result. `group_bbox` is now
`return group_bbox_detail(image_path)[0]`, so its one production caller (`driver.approve`) is unaffected.

### `adjust.preview_result`

The result dict was lifted verbatim out of `adjust.apply` into `preview_result(stem, style,
revision_before)`, which reloads the recipe from disk. That reload is equivalent to what `apply` did before
in every branch: when the sidecar was dirty `apply` already re-read the recipe after the render, and when it
was not, the in-memory recipe and disk were identical (`recipe.save` had run for any reconcile drop).
`apply` now ends with `return preview_result(...)`; the redundant `rec = recipe.load(stem)` it used to do is
gone.

## Deviations from the brief (and why)

**1. `ingest --json` does not route through the legacy `_ingest`, and raises `PARTIAL_FAILURE`.**
The brief only called out this hazard for `verify`, but `_ingest` has the identical defect: it signals
failure with `raise SystemExit(1)`, a `BaseException` that `run_json` deliberately does not catch, so
`ingest --json` over a delivery with one bad file would have exited 1 with **no envelope at all** — the exact
contract violation the controller killed for `verify`. The JSON body therefore calls `ingest.run()` directly
and raises `jsonio.CommandError("PARTIAL_FAILURE", "; ".join(failed))` when any result contains `failed`,
returning `{}` otherwise. `PARTIAL_FAILURE` is canonical. The `{}` deliberately does not invent Task 11's
result shape — **Task 11 should replace that `{}` and may want to attach the per-stem results as
`CommandError(result=...)`**, which the envelope already supports.

**2. `status --json` now goes through `_dispatch` and therefore gains the three adapters.**
Task 6 wired it as `run_json(lambda: status.snapshot())` with none. The only observable change is that a
`FileNotFoundError` escaping `snapshot()` now reports `NOT_FOUND` instead of `INTERNAL`. Nothing pins the
old mapping (no test, no golden fixture yet), and a single dispatch path is what the brief asked for. Flagged
because Task 13's golden fixtures may want to pin this.

**3. `_dispatch` grew a `precheck` parameter that the brief's sketch did not have.**
`preview` passes `precheck=_preview_target`, so a malformed invocation (`preview P1` with no style, or a
doubled `--stem`) raises `BAD_INPUT` *before* the driver mutex is taken. Without it, reporting a typo would
contend for the global lock, and the pre-existing
`test_cli_preview_rejects_missing_or_doubled_values` tests — which run with no `PIPELINE_ROOT` — would
acquire the **real repository's** lock just to reject bad arguments. `_preview_cmd` re-resolves the target
inside the body; the resolution is pure and cheap, so the duplication is intentional.

**4. The brief's zero-face Vision test does not exist in this worktree, so it could not be refactored.**
`tests/test_subject.py` contains exactly one Vision test. It was refactored as specified (basis asserted
alongside bbox); no zero-face image fixture was fabricated. The `no_faces` branch is therefore covered only
by inspection, not by a test. The sentinel-based thin-wrapper test covers the `group_bbox` plumbing.

## Named test refactors

- `tests/test_subject.py::test_group_bbox_detects_real_group` → renamed
  `test_group_bbox_detail_detects_real_group`; now calls `subject.group_bbox_detail`, asserts
  `basis == "faces"`, and keeps every original bbox assertion. **`@requires_vision` skipif marker kept.**

No other existing test was modified.

## Tests added

`tests/test_cli.py` (8):
- `test_mutating_command_reports_lock_held` — subprocess `ingest --json` with a live-PID lock → exit 1,
  last stdout line is a `LOCK_HELD` envelope
- `test_status_never_locks` — `status` exits 0 while the lock is held
- `test_legacy_status_output_unchanged` — stdout is exactly `"photos: none ingested\n"`
- `test_verify_json_reports_problems_as_verify_failed` — the CLI test the brief required: exit 1,
  `{"code": "VERIFY_FAILED", "message": "tif missing; dpi 240 != 300"}` as the last stdout line
- `test_verify_json_reports_clean` — exit 0, `{"stem": "P1", "verify": "clean"}`
- `test_legacy_verify_systemexit_releases_lock` — legacy `verify` raises `SystemExit` from *inside* the
  dispatch lock; asserts the lock file is gone afterwards and legacy stdout is unchanged. Added because a
  leaked lock would wedge every subsequent command.
- `test_preview_json_returns_adjust_shaped_result` — full result body, and `before != after`
- `test_preview_json_unknown_stem_is_not_found` — `NOT_FOUND` via the `FileNotFoundError` adapter

`tests/test_subject.py` (1): `test_group_bbox_is_thin_wrapper_over_detail`.

The brief's Step-1 snippets were adapted rather than pasted verbatim: the lock setup was factored into a
`_held_lock_env` helper, unused `monkeypatch`/`cwd` parameters were dropped, and assertions were
strengthened (e.g. `ok is False` added alongside the error code). Every assertion the brief specified is
still present — the adapted tests are a strict superset.

A `json_stream` fixture was added for the in-process `--json` tests. The `verify --json` case cannot be a
subprocess test (no fixture can produce a photo that reaches `verify_photo` and fails it — staging raises
first), so it monkeypatches `driver.verify_photo` and runs `cli.main` in-process. That collides with
`jsonio`'s process-global state, so the fixture resets `jsonio._out`, redirects `jsonio._real_stdout` to a
`StringIO` (the indirection point Task 1 added for exactly this), and restores `sys.stdout`, which
`activate()` reassigns for the life of the process.

## Test evidence

```
$ /Users/john/photo-edits/.venv/bin/python -m pytest tests/ -q
227 passed in 16.19s
```

218 pre-existing + 9 added. Zero pre-existing tests modified apart from the single named refactor above.

Manual smoke run against a scratch repo (`ingest`, `ingest --json`, `run`, `run --json`, `status`,
`status --json`, `preview --json`, `verify --json`, `approve --json`):
- legacy stdout for `status` is byte-identical (`photos: none ingested\n`); legacy `ingest` on an empty
  Input prints nothing, as before
- every `--json` stdout is a single clean NDJSON envelope, legacy chatter on stderr
- `run --json` does not deadlock
- `run/driver.lock` is absent after every command, including the `SystemExit` paths

## Self-review notes

- `verify --json` on a photo that was never published reports `INTERNAL` (`RuntimeError: published
  artifacts unavailable for ...` from `_stage_published`), not `NOT_FOUND`. `VERIFY_FAILED` is reserved for
  actual verification problems as specified, and mapping that `RuntimeError` is out of scope here — worth a
  look in Task 13.
- `croppreview` and `render` are locked but flagless, per the brief; `_dispatch`'s
  `getattr(ns, "json", False)` handles the missing attribute.
- Unused imports (`manifest`, `ingest`, `render`) were dropped from `build_parser`; `driver` and
  `adjust_mod` are still needed by the inline lambdas.
- Inner lambdas take `n` rather than `ns` to avoid shadowing the enclosing namespace.
- `adjust --json` has no end-to-end CLI test in either direction (Task 7 shipped it that way; its coverage
  is at the `adjust.apply` module level). The `_locked_json` refactor is behaviour-preserving by
  construction, but it is the one refactored path with no direct CLI coverage. Adding that test was out of
  scope here; Task 13's contract fixtures are the natural home for it.
