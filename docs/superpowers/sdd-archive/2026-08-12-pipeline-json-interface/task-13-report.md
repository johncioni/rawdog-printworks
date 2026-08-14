# Task 13 report — golden contract fixtures + no-flag regression sweep

## What was built

- `tests/test_json_contract.py` — 10 tests: the 8 scenarios from the brief's
  Interfaces table plus the 2 legacy-output regression guards. Every scenario
  drives `pipeline.__main__.main([...])` in-process with `jsonio._real_stdout`
  monkeypatched to a `StringIO`, normalizes the capture, and compares against a
  committed fixture (or rewrites it when `REGEN_CONTRACT_FIXTURES=1`, then
  still asserts).
- `tests/fixtures/json_contract/` — 10 committed fixture files (8 envelopes +
  2 NDJSON streams). These are the schemas Plan 2's XCTest decodes.

Harness pieces are exactly as prescribed: the autouse `_json_mode_hygiene`
fixture (saves/restores `sys.stdout`, resets `jsonio._out = None` around every
scenario), the `normalize()` function verbatim (repo path → `<REPO>`,
`sha256:hex64` → `<REVISION>` **before** bare `hex64` → `<SHA256>`, RFC 3339 →
`<TIMESTAMP>`), and `REGEN_CONTRACT_FIXTURES=1` regen mode.

Seeding follows the brief: the styles/lock/lab-profile pattern copied from
`tests/test_status.py` (real `config/lab-profiles/generic-v1.yaml` copied in —
hand-written YAML fails `labprofile.load`'s schema check), monkeypatched
`toolchain.verify → []` and `toolchain.entries_for → {}`, and a fake
`driver.preview_photo` writing deterministic bytes.

## Fixture files

| File | Contents |
| --- | --- |
| `status_empty.json` | `status --json` on a seeded but photo-less repo — `ok:true`, empty `photos`, free lock, style list, clean toolchain. |
| `status_ingested.json` | `status --json` with two `ingested` photos: `P0` (no `--delivery-id` → `delivery_id`/`ingested_at` **null**) and `P1` (delivery fields set), each with fresh previews, per-style `adjustments` covering all three sources, empty `crops`, unpublished `published` block. |
| `adjust_ok.json` | `adjust --stem P1 --style natural --temperature 5600 --json` envelope — `temperature` from `sidecar`, `exposure` from `camera`, the `review_revision_before`/`after` pair. |
| `adjust_stream.ndjson` | The same run's **full** NDJSON line list. One line: adjust emits no progress events (see deviations). |
| `crops_suggested.json` | `crops --stem P1 --json` with `subject.group_bbox_detail` pinned to a fixed bbox — `basis: "faces"`, both `8x10`/`5x7` windows tagged `source: "suggested"`. |
| `approve_stale_review.json` | `approve --review-file` carrying `expected_review_revision: "sha256:wrong"` — `ok:false`, `STALE_REVIEW`, **no** `result` key. |
| `ingest_result.json` | `ingest --from <placeable> <conflicting> --delivery-id fixture-uuid --json` — one `ingested` stem plus one `conflicts` entry; `ok:true` (conflicts alone are not a failure). |
| `run_partial_failure.json` | `run --json` over three photos — `advanced` (P0 → `preview_ready`), `published` (P1 → `v001`, 2 artifacts), `failed` (P2 → `VERIFY_FAILED`), wrapped in `ok:false` + `PARTIAL_FAILURE` with the full `result` attached. |
| `run_stream.ndjson` | The same run's full NDJSON: 1 `stage` + 4 `progress` events for P0, 3 `stage` events for P1, 2 for P2, then the envelope. The streaming-parser fixture with real events. |
| `envelope_lock_held.json` | `ingest --json` against a lock file holding a **live** pid (`os.getpid()`) — `ok:false`, `LOCK_HELD`, message path normalized to `<REPO>/run/driver.lock`. |

## Deviations from the brief (and why)

1. **`run_scenario` writes the envelope alone to each `.json`, not
   `buf.getvalue()`.** The brief's skeleton writes the whole buffer, which
   contradicts its own Interfaces contract ("each file is the normalized final
   envelope only — one JSON object") for the one scenario that emits events.
   `run_scenario` now splits lines, writes `lines[-1] + "\n"` to the `.json`
   fixture, and writes the whole line list to the optional `.ndjson` fixture.
   It returns `(exit_code, envelope, lines, raw)` instead of
   `(exit_code, output)` so tests can assert on both the parsed envelope and
   the pre-normalization text.

2. **Fixtures hold the wire bytes** (compact, `sort_keys=True`, as
   `jsonio._write` emits) rather than being re-serialized pretty-printed.
   Re-serializing is a transform the brief doesn't authorize and would make
   `adjust_ok.json` disagree byte-for-byte with the last line of
   `adjust_stream.ndjson`. Inspect them with `jq .`.

3. **Added `run_stream.ndjson`** (additive; not in the brief's file list).
   `adjust_stream.ndjson`'s stated purpose is "events + envelope … for Plan 2's
   streaming-parser tests", but `adjust` emits **no** events — `jsonio.emit` is
   called only from `driver._stage_event`, `driver._RenderProgress.landed`, and
   the preview loop inside `process_all`. `adjust_stream.ndjson` is shipped
   honestly as a one-line stream (Plan 2's parser must handle envelope-only
   streams anyway), and `run_stream.ndjson` supplies the multi-event stream the
   brief actually asked for. Drop it if unwanted — nothing else depends on it.

4. **`run_partial_failure` seeds three stems, not two.** With only the two
   approved stems the brief names, `advanced` is always `[]` and no `progress`
   event is ever emitted, so neither shape is pinned by any fixture — a
   regression in either would pass this suite silently. Adding `P0` in
   `ingested` state fills all three `result` buckets and exercises both event
   types in one run. Side benefit: the message is now `"1 of 3 photos failed"`,
   matching spec §4.3's own example verbatim.

5. **`status_ingested` seeds two photos, not one.** Same reasoning: spec §4.3
   explicitly documents `delivery_id`/`ingested_at` as null "for recipes
   ingested without `--delivery-id`". With a single delivery-bearing photo, a
   Swift decoder typing those as non-optional `String` would pass every fixture
   and crash on real data. The second photo also pins the sorted ordering of
   the `photos` array, which one element cannot.

6. **No git commands run** (per the lead's instruction, overriding the brief's
   Step 4). The two paths below are ready to `git add` and commit.

## Deliberate fidelity choices

- **The fake `driver.preview_photo` also records provenance** (computes
  `provenance.style_input_hash`, calls `provenance.record_preview`, sets
  `render_width`/`render_height`, saves the recipe) — i.e. real
  `preview_photo` minus the RawTherapee call. A bytes-only fake would leave
  `stale_previews` permanently equal to all four styles and `render_width`
  unset, which would pin a degenerate contract and make the `crops` scenario
  impossible (`crop_windows` needs recorded dims).
- **`ingest.exif_summary` is monkeypatched** in the ingest scenario. exiftool
  reading fabricated `.RW2` bytes is an environment-dependent failure; the
  shape under test is the ingest result body, not metadata extraction. The
  stub returns metadata that trips none of `_preflight`'s warning branches, so
  no `WARNING:` lines enter the capture.
- **`run` monkeypatches `render_photo`, `verify_photo`, `_publish_photo`.**
  The fake publish creates a real `Output/photos/<stem>/v001` + `current`
  symlink so `_published_version` yields `"v001"` — a `"version": null` inside
  a `published` entry would pin a lying contract.
- **The manifest fingerprints for the approved stems are computed via
  `driver._current_fingerprint` after all seeding writes.** Previews and
  sidecars feed the fingerprint; a stale one downgrades both stems to
  `review_required` and the run silently produces an `ok:true` envelope.

## Test evidence

Regen, then compare:

```
REGEN_CONTRACT_FIXTURES=1 .venv/bin/python -m pytest tests/test_json_contract.py -q
  → 10 passed in 1.55s
.venv/bin/python -m pytest tests/test_json_contract.py -q
  → 10 passed in 1.44s
```

Full gate, run twice back-to-back (compare mode both times — any
run-to-run nondeterminism in a fixture would fail the second run):

```
.venv/bin/python -m pytest tests/ -q   → 287 passed in 19.04s
.venv/bin/python -m pytest tests/ -q   → 287 passed in 18.32s
```

287 = the pre-existing 277 + 10 new. No existing test was modified.

Per-test isolation — every scenario re-run alone (`-k`) against fixtures
generated by a whole-suite regen, proving no cross-test state leaks into a
fixture:

```
test_status_empty                  1 passed, 9 deselected
test_status_ingested               1 passed, 9 deselected
test_adjust_ok                     1 passed, 9 deselected
test_crops_suggested               1 passed, 9 deselected
test_approve_stale_review          1 passed, 9 deselected
test_ingest_result                 1 passed, 9 deselected
test_run_partial_failure           1 passed, 9 deselected
test_envelope_lock_held            1 passed, 9 deselected
test_legacy_status_output…         1 passed, 9 deselected
test_legacy_ingest_on_empty_input… 1 passed, 9 deselected
```

Negative control — the guard actually catches drift. Mutating
`"value":5600` → `"value":5601` in `adjust_ok.json` and re-running gave
`1 failed`; restoring the file returned the module to `10 passed`.

Legacy output captured empirically before writing the guards, by running the
real CLI in a subprocess against a fresh empty repo:

```
['ingest'] rc=0 stdout='' stderr=''
['status'] rc=0 stdout='photos: none ingested\n' stderr=''
```

Both guards assert stdout **and** stderr, in-process via `capsys`.

## Self-review

- **Envelope shapes checked against spec §4.3** (`docs/superpowers/specs/
  2026-08-12-macos-app-design.md`, lines 78–157 — the brief's own §4.3
  reference; it is not in the sdd directory). Every documented `result` sketch
  is now pinned by a fixture: `ingest`, `preview`/`adjust`, `crops`, `run`,
  `status`. `approve`'s success body is **not** pinned — the brief's approve
  scenario is the STALE_REVIEW error path; the success shape is covered by
  Task 10's own tests but has no golden fixture. Noted as a residual.
- **Ledger item confirmed and now pinned:** unpinned exposure resolves as
  `{"value": null, "source": "camera"}` in both `status_ingested.json` (all
  four styles) and `adjust_ok.json`. That is now contract.
- **Normalizer ordering verified:** `<REVISION>` substitution runs before the
  bare-hex rule, so `sha256:…` revisions never degrade into `sha256:<SHA256>`.
  Confirmed by eye in `status_ingested.json` (`review_revision` is
  `"<REVISION>"`, `preview_hashes` values are `"<SHA256>"`).
- **State hygiene:** the autouse fixture lives in `test_json_contract.py` only
  and does not leak into the other 277 tests. Confirmed by the unchanged
  existing-suite result.
- **No repo pollution:** the worktree root is byte-identical after the runs
  (`.manifest` still 346 B, no stray files). Both legacy guards use `tmp_repo`,
  so legacy `ingest`'s unconditional `manifest.save()` writes into the temp
  repo rather than the checkout.
- **No unused imports or dead parameters** in the new module; longest line is
  84 chars, within the existing `tests/` range (74–102).
- **Consciously not covered:** `INTERNAL`, `RENDER_FAILED`, `TOOLCHAIN_FAILED`,
  `NOT_FOUND`, `BAD_INPUT`, and `INVALID_STATE` envelopes have no golden
  fixture — the brief's scenario table names only `STALE_REVIEW`,
  `PARTIAL_FAILURE`, and `LOCK_HELD`. All are exercised by `tests/test_cli.py`
  and the per-command test modules; they just aren't schema-pinned for Plan 2.

## Ready to commit

```
tests/test_json_contract.py
tests/fixtures/json_contract/          (10 files)
```
