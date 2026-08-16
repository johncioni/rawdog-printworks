# RAW-10 brief — pin a non-VERIFY_FAILED `failed[]` code in the contract fixtures

## Why this exists

`CLAUDE.md` names the golden fixtures in `tests/fixtures/json_contract/` — not
prose — as the authority the macOS app (Plan 2) decodes against. The pipeline can
emit any member of `jsonio.ERROR_CODES` in a per-stem `failed[].code`, but every
fixture that shows that field today contains exactly one value, `VERIFY_FAILED`.
A Swift decoder written faithfully from the fixtures would therefore model the
field too narrowly and break at runtime on a perfectly legal `RENDER_FAILED`.

This is documentation-of-domain work. The runtime domain is already correct and
already clamped (`pipeline/driver.py`, the `collect["failed"]` append clamps to
`jsonio.ERROR_CODES`). Do not change that clamp.

## Requirement

Make the committed contract fixtures show that `failed[].code` varies.

Extend the EXISTING scenario `test_run_partial_failure` in
`tests/test_json_contract.py` (do not add a separate scenario) so the single run
produces two failed stems with two DIFFERENT codes:

- the current verification failure, which must keep producing
  `{"stem": ..., "code": "VERIFY_FAILED", "message": "dpi 240 != 300"}`
- one additional stem whose render raises `render.RenderError`, producing
  `code: "RENDER_FAILED"`

Seed the new stem exactly like the existing approved stems (`bind_crops=True,
audit=True`, `approved` state with a fingerprint taken AFTER all seeding writes —
the existing comment in that test explains why the ordering matters).

## What you must update, all of it

Regenerating the fixture is not the whole job. The test asserts the envelope and
the event stream explicitly, and those assertions must be updated to match:

- `envelope["error"]["message"]` — currently `"1 of 3 photos failed"`; the count
  and total both change.
- `envelope["result"]["failed"]` — now two entries. Assert BOTH codes.
- the event-sequence assertion (`stage`/`progress` tuples) — the new stem adds
  its own events in stem order.
- both fixture files: `tests/fixtures/json_contract/run_partial_failure.json` and
  `tests/fixtures/json_contract/run_stream.ndjson`.

Regenerate with, from the repo root:

    REGEN_CONTRACT_FIXTURES=1 .venv/bin/python -m pytest tests/test_json_contract.py

then run WITHOUT the env var to confirm the committed fixtures match, and finally
run the full gate.

## Constraints

- Additive only. No production code changes at all — this task touches
  `tests/test_json_contract.py` and the two fixture files, nothing else. If you
  believe production code must change, stop and report BLOCKED with the reason.
- Do not weaken any existing assertion to make things pass. The existing
  `VERIFY_FAILED` entry, the `advanced`/`published` buckets, the
  events-precede-envelope rule and the "events are not envelopes" assertion all
  still hold.
- Fixture bytes are generated, never hand-edited.

## Verification (all three, and report the output)

1. `.venv/bin/python -m pytest tests/test_json_contract.py -q`
2. `.venv/bin/python -m pytest tests/ -q` — the full gate; it is 296 tests before
   your change and must be green after.
3. `git diff --stat` — confirm only the three intended files changed.

## Commit

One commit. Message body should say what the fixtures now document and why it
matters for the Plan 2 decoder.
