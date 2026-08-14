# Task 11 report — `ingest --from` / `--delivery-id`

## What was built

**`pipeline/recipe.py`** — `new()` gains keyword-only `delivery_id=None, ingested_at=None`
(explicit `*` separator). The dict is built exactly as before and each key is added only
when its argument `is not None`, so a flag-less ingest writes byte-identical legacy recipes.

**`pipeline/ingest.py`**
- New imports: `datetime`, `os`, `uuid`.
- `_raw_files(directory)` — the `.rw2` (case-insensitive), files-only, name-sorted filter,
  extracted because `stage_sources` needs it three times and `run()` already had a
  hand-rolled copy of it. `run()`'s old `sorted({...}, key=name)` set-comprehension was
  replaced by `list(_raw_files(...))`; identical results (same-directory `Path` ordering is
  name ordering, and `iterdir()` cannot yield duplicates for the set to collapse).
- `_iter_sources(sources)` — one level of recursion into a dropped directory, `.rw2` filter.
- `stage_sources(sources)` — implemented verbatim from the brief (only the two inline
  `paths.input_dir().iterdir()` comprehensions became `_raw_files` calls). Staging dir is
  `Input/.staging-<uuid4hex>`, hashing is of the **staged temp**, decision order is
  content-duplicate → stem-conflict → place via `os.replace`, and the staging dir is removed
  in a `finally`.
- `_now_utc()` — `datetime.datetime.now(datetime.timezone.utc)` formatted with
  `isoformat(timespec="microseconds")` and `+00:00` replaced by `Z`.
- `run(delivery_id=None)` — threads `delivery_id` and `ingested_at=_now_utc() if
  delivery_id is not None else None` into `recipe.new`. Nothing else in `run` changed.

**`pipeline/__main__.py`**
- `ingest` parser gains `--from` (`nargs="+"`, `dest="sources"` — `from` is a keyword and
  would be unreachable as an attribute), `--delivery-id`, alongside the existing `--json`.
- `_ingest_result(ns)` composes the contract body `{ingested, skipped, conflicts, failed}`
  from `stage_sources` (when `--from` is given) plus `ingest.run(ns.delivery_id)`.
- `_ingest_cmd(ns)` — the flag-less non-JSON path is still literally `return _ingest()`.
  With `--json`, a non-empty `failed` raises
  `CommandError("PARTIAL_FAILURE", f"{len(failed)} file(s) failed", result=result)`;
  otherwise the result body is returned. With flags but no `--json`, the same body is
  pretty-printed and a non-empty `failed` raises `SystemExit(1)`, matching `_crops_cmd` /
  `_approve_cmd`'s existing "no legacy output to preserve" idiom.

## Interpretations and deviations

1. **`is not None` rather than the brief's truthy `if delivery_id`** in `run()`. The brief's
   Interfaces section says "when `delivery_id` is not None"; its Step 3 sketch says
   `if delivery_id`. They disagree only for `--delivery-id ""`, where the truthy form would
   write `delivery_id: ""` with no `ingested_at`. `is not None` keeps the two keys paired.
   Flag-less behavior is identical either way.
2. **`run()`'s `"skipped (already ingested)"` entries are mapped into `skipped`** as
   `{"file": stem, "reason": "already ingested"}`. The brief spells out only the two
   non-obvious renames (`ok`→`ingested`, `"failed: …"`→structured entry); dropping the
   skipped ones would make `ingest --json` return an all-empty result for a run that
   actually skipped photos. The mapping unwraps the `skipped (…)` text rather than matching
   it literally, so a future outcome string cannot vanish silently.
3. **`failed` entries from `run()`** use the stem as `"file"`, `code: "BAD_INPUT"`, and the
   message with the `"failed: "` prefix stripped. Iteration is over `sorted(results.items())`.
4. **`--from` / `--delivery-id` without `--json` are honoured**, not ignored — silently
   discarding staged-copy results would be data loss. The brief only specified the JSON
   handler.
5. **Per-photo `ingested_at`** (the brief's inline expression), so photos in one delivery can
   differ by microseconds. Grouping in the app is by `delivery_id`, so this is harmless.
6. **No git commands run** — the brief's Step 5 `git add`/`git commit` were skipped per the
   dispatch instruction.

## Test evidence

Step 2 (tests appended verbatim, before implementation):

```
5 failed, 20 passed in 0.49s
FAILED tests/test_ingest.py::test_recipe_new_without_flags_is_legacy_bytes
FAILED tests/test_ingest.py::test_stage_sources_hashes_temp_and_places
FAILED tests/test_ingest.py::test_stage_sources_conflict_and_duplicate
FAILED tests/test_ingest.py::test_stage_sources_hashes_the_staged_temp_not_the_live_source
FAILED tests/test_ingest.py::test_run_records_delivery_metadata_only_when_given
```

Step 4/5, full gate (`/Users/john/photo-edits/.venv/bin/python -m pytest tests/ -q`):

```
254 passed in 15.13s
```

249 pre-existing tests, unmodified, plus the 5 new ones.

**CLI smoke test** (scratchpad, not committed) — no unit test drives `--from` through
argparse, so the wiring was exercised end to end: a dropped directory containing `A1.RW2`,
`A2.rw2` and a `notes.txt`, with `Input/A2.RW2` already holding different bytes, plus a
nonexistent `A9.RW2` source, run as
`ingest --from <dir> <missing> --delivery-id uuid-smoke --json`:

- exit `1`, envelope `{"ok": false, "error": {"code": "PARTIAL_FAILURE", "message": "1 file(s) failed"}, "result": {…}}`
- `conflicts: [{"file": "A2.rw2", "reason": "stem exists with different content"}]`,
  `failed: [{"file": "A9.RW2", "code": "BAD_INPUT", "message": "[Errno 2] …"}]`,
  `ingested: ["A1", "A2"]`
- `notes.txt` ignored; `Input/` ends as `['A1.RW2', 'A2.RW2']` with the pre-existing A2 bytes
  intact; no `.staging-*` residue
- both recipes carry `delivery_id: uuid-smoke` and an `ingested_at` ending in `Z`; a
  subsequent flag-less `ingest.run()` produced a recipe with neither key

Note on that result: `ingested` contains `A2` while `conflicts` also names `A2.rw2`. That is
correct — the conflicting *source* was rejected and never placed, and the `A2` that got
ingested is the pre-existing `Input/A2.RW2` that `run()` picks up as it always has.

## Self-review

- Decision order in `stage_sources` is content-duplicate before stem-conflict, which is what
  `test_stage_sources_conflict_and_duplicate` gates (same content under a new stem is a
  skip, not a placement).
- The staging directory lives inside `Input/` so `os.replace` is a same-filesystem atomic
  rename; it is dot-prefixed and is a directory, so the `is_file()` filter in `_raw_files`
  excludes it from both the hash set and the stem set.
- Same-name sources in one batch: after a placement the digest is added to `known_hashes`
  and the stem to `input_stems`, so a second copy with identical bytes skips and one with
  different bytes conflicts. Neither can clobber a placed file.
- `known_hashes` is seeded from `_archived_hashes()` **and** current `Input/`, so a file
  already staged but not yet ingested still dedups.
- No test gated the old `PARTIAL_FAILURE` message (`grep` over `tests/`: only
  `test_jsonio.py`'s own synthetic error and the held-lock CLI test), so changing it to the
  count form breaks nothing.
- Known edge cases, left as the brief has them: (a) an unreadable pre-existing file in
  `Input/` makes the `known_hashes` seed raise `OSError` before the per-source `try`,
  surfacing as an `INTERNAL` envelope rather than a per-file `failed` entry; (b) a
  nonexistent *directory* passed to `--from` is silently ignored (it fails `is_dir()` and has
  no `.rw2` suffix), whereas a nonexistent `.rw2` *file* does produce a `failed` entry.
- Quality gate: this repo configures no linter or type checker (no `pyproject.toml` or
  `setup.cfg`; `requirements-dev.txt` is pytest + pyyaml + pyobjc), so the pytest run above
  is the full gate.
