# RAW-10 report — pin a non-VERIFY_FAILED `failed[]` code in the contract fixtures

## Status: DONE

## What changed and why

`tests/test_json_contract.py`'s `test_run_partial_failure` scenario is the
only place in the golden-fixture suite that exercises `failed[]`, and it
only ever produced `VERIFY_FAILED`. A Swift decoder for Plan 2, built
faithfully from the committed fixtures (the stated authority per CLAUDE.md),
would therefore model `failed[].code` as a single-value field and break at
runtime the first time the pipeline legitimately emits `RENDER_FAILED` (or
any other member of `jsonio.ERROR_CODES`).

Extended the existing scenario (no new scenario, no new fixture file) by
adding a third approved stem, `P3`, seeded identically to `P1`/`P2`
(`bind_crops=True, audit=True`, `approved` state, fingerprint computed via
`driver._current_fingerprint` after all seeding writes completed — same
ordering the existing comment already explains). `driver.render_photo` is
now a small fake that raises `render.RenderError("simulated render
failure")` specifically for `P3` and returns `None` (success) otherwise,
replacing the old always-succeeds lambda. `render` was added to the test
module's `pipeline` import to reach `render.RenderError`.

Because `RenderError` carries no `.code` attribute, `driver.process_all`'s
exception handler (`pipeline/driver.py` ~line 824-827) falls through to its
clamp default and records `code="RENDER_FAILED"` — exactly the mechanism the
brief specified, and no production code was touched to get there.

Updated the three things the brief flagged as needing to move in lockstep
with the new failure:

- `envelope["error"]["message"]`: `"1 of 3 photos failed"` → `"2 of 4 photos
  failed"` (2 failed of published+advanced+failed = 1+1+2 = 4 total).
- `envelope["result"]["failed"]`: now asserts both entries in stem order —
  `P2`/`VERIFY_FAILED`/`"dpi 240 != 300"` (unchanged) followed by
  `P3`/`RENDER_FAILED`/`"simulated render failure"`.
- The event-sequence assertion: appended `("P3", "stage", "render")` at the
  end — `P3` fails inside `render_photo` before `_finish_verified` ever
  emits a `verify` or `publish` stage event for it, so that's its only
  event.
- Both fixture files regenerated: `tests/fixtures/json_contract/run_partial_failure.json`
  and `tests/fixtures/json_contract/run_stream.ndjson`.

No other assertions were touched or weakened — the `P2`/`VERIFY_FAILED`
entry, the `advanced`/`published` buckets, the events-precede-envelope
ordering, and the "events are not envelopes" check all still hold as
written before this change.

## Files touched

- `/Users/john/orca/workspaces/rawdog-printworks/plan2-printworks-app/tests/test_json_contract.py`
- `/Users/john/orca/workspaces/rawdog-printworks/plan2-printworks-app/tests/fixtures/json_contract/run_partial_failure.json`
- `/Users/john/orca/workspaces/rawdog-printworks/plan2-printworks-app/tests/fixtures/json_contract/run_stream.ndjson`

No production code changed. `pipeline/driver.py`'s clamp of `failed[].code`
to `jsonio.ERROR_CODES` (the mechanism this task documents) was read but not
modified.

## Verification (all three from the brief)

### 1. Regenerate, then confirm fixtures are stable without the env var

```
$ REGEN_CONTRACT_FIXTURES=1 .venv/bin/python -m pytest tests/test_json_contract.py -q
...........                                                              [100%]
11 passed in 2.40s

$ .venv/bin/python -m pytest tests/test_json_contract.py -q
...........                                                              [100%]
11 passed in 2.03s
```

Regenerating and then re-running without `REGEN_CONTRACT_FIXTURES=1` both
pass, confirming the committed fixture bytes match what the test produces.

Resulting fixture content (both files), for reference:

`run_partial_failure.json`:
```
{"error":{"code":"PARTIAL_FAILURE","message":"2 of 4 photos failed"},"ok":false,"result":{"advanced":[{"state":"preview_ready","stem":"P0"}],"failed":[{"code":"VERIFY_FAILED","message":"dpi 240 != 300","stem":"P2"},{"code":"RENDER_FAILED","message":"simulated render failure","stem":"P3"}],"published":[{"artifact_count":2,"stem":"P1","version":"v001"}]}}
```

`run_stream.ndjson` (new final lines vs. before):
```
{"event":"stage","stage":"render","stem":"P2"}
{"event":"stage","stage":"verify","stem":"P2"}
{"event":"stage","stage":"render","stem":"P3"}
{"error":{"code":"PARTIAL_FAILURE","message":"2 of 4 photos failed"},"ok":false,"result":{...two failed entries...}}
```

### 2. Full gate

```
$ .venv/bin/python -m pytest tests/ -q
........................................................................ [ 24%]
........................................................................ [ 48%]
........................................................................ [ 72%]
............................................s........................... [ 97%]
........                                                                 [100%]
295 passed, 1 skipped in 20.31s
```

295 passed + 1 skipped = 296 collected, matching the brief's "296 tests
before your change" baseline (CLAUDE.md's "295 tests" figure counts only
passing tests, same collection). Green after the change, as required.

### 3. Diff scope check

```
$ git diff --stat
 .../json_contract/run_partial_failure.json         |  2 +-
 tests/fixtures/json_contract/run_stream.ndjson     |  3 ++-
 tests/test_json_contract.py                        | 27 ++++++++++++++--------
 3 files changed, 21 insertions(+), 11 deletions(-)
```

Exactly the three intended files — no production code, no stray files.

## Commit

`a3e8363c6546464f9a3ccf9385d500c0dc47e518` — "test: pin RENDER_FAILED
alongside VERIFY_FAILED in run_partial_failure fixtures" (branch
`johncioni/plan2-printworks-app`). Not pushed, per instructions.

## Concerns

None. The task was mechanical and matched the brief's pre-resolved
ambiguity exactly:

- Confirmed `render.RenderError` has no `.code` attribute, so it reliably
  clamps to `RENDER_FAILED` via `driver.process_all`'s existing handler
  rather than needing any production change.
- Confirmed stem-sort ordering (`P0` < `P1` < `P2` < `P3`) puts the new
  stem's events after `P2`'s, matching the brief's "the new stem adds its
  own events in stem order."
- The chosen failure message (`"simulated render failure"`) is arbitrary
  test fixture text, not load-bearing production behavior — happy to change
  it if a reviewer wants fixture prose to read differently, but it doesn't
  affect the contract shape being pinned.
