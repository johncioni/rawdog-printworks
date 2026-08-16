# Final fix wave — pipeline JSON interface

Three findings from the final whole-branch review, applied in the
`json-interface` worktree. Nothing else was touched.

Baseline before the wave: **287 passed**. After: **290 passed** (three new
tests, no existing test modified).

---

## Finding 1 (Important) — no golden fixture for the approve SUCCESS envelope

`tests/test_json_contract.py` pinned only `approve_stale_review.json`, so the
success body defined in spec §4.2 — `{"stem", "state": "approved",
"fingerprint"}` — was uncontracted. The SwiftUI app decodes that body on every
successful approval.

**Change** — new `test_approve_ok` scenario in `tests/test_json_contract.py`,
driven through the existing `run_scenario`/`REGEN` machinery, plus the new
committed fixture `tests/fixtures/json_contract/approve_ok.json`:

```json
{"ok":true,"result":{"fingerprint":"<SHA256>","state":"approved","stem":"P1"}}
```

Design notes:

- The scenario runs on the existing `ingested_repo` fixture, whose
  `_fake_preview_photo` helper records provenance for every style — so
  `stale_previews` is empty and the previews read as fresh.
- The review file submits the **current** `expected_review_revision`, computed
  in-test with `provenance.review_revision("P1", rec)`. This pins the happy
  path of the revision + staleness check that `test_approve_stale_review` only
  exercises on its failure side. All inputs are deterministic (fixed preview
  bytes, monkeypatched toolchain), which the double run confirms.
- Crop windows are **derived** via `geometry.centered_crop_norm` from the
  recipe's recorded `render_width`/`render_height`, not hard-coded. This was a
  real trap: the windows in `test_approve_stale_review` have never passed
  `geometry.validate_crop` (that test raises `STALE_REVIEW` at driver.py:511-520,
  before the validation loop at :528), and the proven-valid windows in
  `tests/test_driver.py::_seed_approvable` are sized for a 5784x4344 render,
  whereas the contract fixture seeds 5776x4336. Deriving the windows removes the
  dependency on either.
- Beyond the fixture, the test asserts the persisted manifest fingerprint equals
  the recipe's `approval.fingerprint` — normalization to `<SHA256>` would
  otherwise hide a mismatch between the emitted and the stored value.

Fixture generated with `REGEN_CONTRACT_FIXTURES=1 ... -k test_approve_ok`,
scoped to the single test so no other fixture's bytes could be rewritten.

## Finding 2 (Important) — legacy `run --stem TYPO` exited 0 in silence

In `pipeline/driver.py`'s `_selected_stems`, unknown requested stems were
recorded only into `collect`, which is `None` on the legacy path — so the
command did nothing, said nothing, and exited 0.

**Change** — an `else` branch on the existing `collect is not None` test
(`pipeline/driver.py:670-674`):

```python
    else:
        # Legacy `run` has no failure contract for an unknown stem, so a typo
        # must still be visible rather than exiting 0 having done nothing.
        for stem in sorted(requested - known):
            print(f"WARNING: unknown stem {stem} — skipped")
```

Per the brief, the exit code is unchanged and the `collect` path is untouched.
Iteration is over `sorted(requested - known)` so multi-stem output is
deterministic.

**Confirmation the `--json` path is unaffected**: `_run_cmd` in
`pipeline/__main__.py:158-160` always constructs `result` and passes
`collect=result` on the json path, so the new `else` branch is unreachable
there. Those are the only two `process_all` call sites in the codebase. The
existing `test_process_all_unknown_requested_stem_is_not_found` (pinning the
`NOT_FOUND` collect entry) still passes unmodified.

Also note the branch is guarded by the earlier `if stems is None: return` — a
bare legacy `run` never reaches it, so that output stays byte-for-byte as it was.

**Test** — `test_process_all_unknown_requested_stem_warns_on_legacy_path` in
`tests/test_driver.py`, asserting the warning on stdout and a clean stderr.

## Finding 3 (hardening) — `int()` cast on Temperature could fail the whole snapshot

`pipeline/status.py`'s `_photo` passed a bare `int` as the cast for
`Temperature`. A hand-edited sidecar containing `Temperature=5650.0` would raise
`ValueError` and fail the entire `status --json` as `INTERNAL` — and status is
the app's refresh loop, so one malformed sidecar would take down the whole UI.

**Change** — the cast at the call site (`pipeline/status.py:62-66`) is now
`lambda value: int(float(value))`. `_control` itself is generic and was not
touched; the exposure `float` cast is unchanged.

**Test** — `test_float_valued_temperature_sidecar_still_snapshots` in
`tests/test_status.py`: a `P1_bw.pp3` sidecar with `Temperature=5650.0`, asserting
the snapshot still succeeds and reports `{"value": 5650, "source": "sidecar"}`.

No fixture churn: `int(float("5650")) == 5650`, so `status_ingested.json` stays
byte-identical (verified by the contract suite passing in compare mode).

---

## Test evidence

```
baseline (before any change)      287 passed in 19.25s
tests/test_status.py + test_driver.py after findings 2+3    63 passed in 2.19s
REGEN -k test_approve_ok           1 passed, 10 deselected in 0.76s
tests/test_json_contract.py (compare mode)                  11 passed in 1.83s
full gate RUN 1                   290 passed in 19.98s
full gate RUN 2                   290 passed in 20.22s
```

Both full runs are in plain compare mode (no `REGEN`), so the second run is the
fixture-determinism check: `approve_ok.json` reproduces byte-for-byte, and every
pre-existing fixture still matches.

## Self-review

Files touched — 5 modified, 1 new fixture, exactly as scoped:

- `pipeline/driver.py` — `_selected_stems`, one `else` branch (finding 2)
- `pipeline/status.py` — one cast at the `_photo` call site (finding 3)
- `tests/test_json_contract.py` — `geometry` added to the module import;
  one new `test_approve_ok` (finding 1)
- `tests/test_driver.py` — one new test (finding 2)
- `tests/test_status.py` — one new test (finding 3)
- `tests/fixtures/json_contract/approve_ok.json` — **new**, 1 line

Checks performed:

- No existing test was edited or deleted; the +3 count matches 287 → 290 exactly.
- No existing fixture was regenerated — the REGEN run was `-k`-scoped to the new
  test, and the full contract suite passes in compare mode afterwards.
- Both source edits are additive branches/casts; neither changes an exit code,
  an envelope shape, or any legacy output path.
- Both `process_all` call sites reviewed; the json path cannot reach the new
  warning branch.
- New tests follow the surrounding conventions (module-level `driver` import in
  `test_driver.py`, the `repo` fixture and `capsys`/`snapshot` shapes already in
  use in `test_status.py`).

No git commands were run.
