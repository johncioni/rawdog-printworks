# Task 1 report — `pipeline/jsonio.py` (JSON mode core)

## What I built

Two new files, both taken verbatim from the brief:

- `/Users/john/photo-edits/.claude/worktrees/json-interface/pipeline/jsonio.py`
- `/Users/john/photo-edits/.claude/worktrees/json-interface/tests/test_jsonio.py`

`jsonio.py` provides the surface every later task consumes:

- `ERROR_CODES` — the closed set of 10 codes; `CommandError.__init__` raises `ValueError` on
  anything outside it, so an unknown code fails loudly at construction rather than leaking into
  an envelope.
- `CommandError(code, message, result=None)` with `.code`, `.message`, `.result`.
- `activate()` — idempotent; saves the real stdout via the `_real_stdout()` indirection point into
  module-level `_out`, then points `sys.stdout` at `sys.stderr` so legacy `print()` calls in
  `driver`/`ingest` cannot corrupt the NDJSON stream.
- `active()`, `emit(event)` (no-op while inactive), `finish_ok(result) -> 0`,
  `finish_error(code, message, result=None) -> 1`.
- `run_json(fn, adapters=None)` — activates, then maps `CommandError` → its own code/message/result,
  `publish.LockError` → `LOCK_HELD`, an `adapters` isinstance match (insertion order, first match
  wins) → that code with `str(e)`, and anything else → `INTERNAL` with `f"{type(e).__name__}: {e}"`.

Envelope lines are written with `json.dumps(..., sort_keys=True, separators=(",", ":"))` and flushed
per line, so output is compact deterministic NDJSON.

## Deviations from the brief

1. **Skipped the `git add` / `git commit` in Step 5.** The controller commits; my task instructions
   explicitly forbid running git commands. Everything else in Step 5 (the full gate) was done.

No deviations in the code itself — `pipeline/jsonio.py` and `tests/test_jsonio.py` are byte-for-byte
the blocks given in the brief.

## Test evidence

Step 2 — verify failure before implementing:

```
$ /Users/john/photo-edits/.venv/bin/python -m pytest tests/test_jsonio.py -q
tests/test_jsonio.py:7: in <module>
    from pipeline import jsonio, publish
E   ImportError: cannot import name 'jsonio' from 'pipeline' (/Users/john/photo-edits/.claude/worktrees/json-interface/pipeline/__init__.py)
=========================== short test summary info ============================
ERROR tests/test_jsonio.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 0.23s
```

Step 4 — verify pass after implementing:

```
$ /Users/john/photo-edits/.venv/bin/python -m pytest tests/test_jsonio.py -q
.......                                                                  [100%]
7 passed in 0.02s
```

Step 5 — full gate (run from the worktree root):

```
$ /Users/john/photo-edits/.venv/bin/python -m pytest tests/ -q
........................................................................ [ 40%]
........................................................................ [ 80%]
..................................                                       [100%]
178 passed in 24.12s
```

The repo has no ruff/flake8/mypy configuration and `requirements-dev.txt` lists only
`pytest`, `pyyaml`, and the two pyobjc frameworks, so pytest is the entire quality gate here.

## Self-review notes

- **Additive only.** Both files are new. Nothing existing was touched, so no existing CLI path can
  change behavior; `activate()` is only reachable from code that calls it, and nothing calls it yet.
- **No import cycle.** `jsonio` imports `publish`, which imports only `json`, `os`, `re`, `shutil`,
  `contextlib`, `pathlib`, and `. paths`. `pipeline/__init__.py` is empty. Later tasks should avoid
  importing `jsonio` *from* `publish` for this reason.
- **`sys.stdout` leak across tests — checked, not a problem.** `activate()` assigns `sys.stdout`
  directly, which `monkeypatch` does not undo, so I expected possible pollution of test files that
  sort after `test_jsonio.py` (`test_labprofile` onward). The full suite passes at 178, and pytest's
  capture manager reassigns `sys.stdout`/`sys.stderr` when it resumes capturing per test item, so
  the assignment does not escape. I deliberately did not add a defensive save/restore, since fixing
  a hypothesis the gate disproves would be a silent deviation from the brief.
- **Contract detail for later tasks:** `finish_ok`/`finish_error` write through `_out` and will
  raise `AttributeError` if called without a prior `activate()`. Only `emit()` is guarded for the
  inactive case. `run_json` always activates first, so the dispatch path in Task 8 is safe; any
  direct `finish_*` caller must activate itself.
- **`import sys` in `tests/test_jsonio.py` is unused.** It came with the brief's verbatim block. I
  left it in place because there is no lint gate to trip and matching the brief exactly is more
  valuable than the cleanup; trivially removable if a reviewer prefers.
- **Exit-code invariant holds:** the only `return 0` is `finish_ok`, reached only when `fn()` returns
  normally; every error path returns 1 via `finish_error`. So exit 0 iff `ok: true`.
