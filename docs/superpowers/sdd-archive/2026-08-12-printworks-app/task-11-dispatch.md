# Task 11 dispatch — e2e smoke test + release build script

You are the implementer. This is the last task. A separate Opus reviewer reviews
it afterwards, and the **visual QA gate belongs to the controller, not you**.

## Read first

- `.superpowers/sdd/2026-08-12-printworks-app/task-11-brief.md` — **authoritative**;
  it contains the `SmokeTests` skeleton and the exact `scripts/build-app.sh`.
- `docs/superpowers/specs/2026-08-12-macos-app-design.md` §8 (testing/done-criteria).
- Task 3's stub-script pattern; `PipelineClient`, `AppModel`, `Contract`.

## Scope — Steps 1 and 2 only

**Step 1 — `Tests/PrintworksCoreTests/SmokeTests.swift`.** Build a temp fixture
repo (dir list from `tests/conftest.py`, two fake photos: recipes + tiny preview
JPG bytes) and a stub `python` shell script dispatching on `$1`, logging argv to
`<repo>/stub-calls.log`. Drive the REAL `PipelineClient` + `AppModel` end-to-end
through spec §8's flow: refresh → startDraft → setSlider → flushPendingAdjustments
(the debounced adjust fires and the draft **rebases** on the revision pair rather
than going stale) → check all three → approve. Assert the argv sequence
(adjust → approve → `run --stem P1` → final status), the review-file contents the
stub received (its `expected_review_revision` must match), and that the final
refresh landed.

Two traps the brief calls out — heed them:
- `executableOverride` is **required**; without it the client runs
  `stub -m pipeline <args>` and the stub sees `-m` as its command.
- The canned adjust/preview envelopes must carry `review_revision_before/after`
  matching the canned status revisions, or the draft stales instead of rebasing
  and the test asserts the wrong thing.

This is the app-side twin of Plan 1's golden fixtures: it exists to catch wiring
drift the unit fakes cannot. If it passes on the first run without you having
seen it fail, make it fail deliberately once (break the argv or the revision
pair) and record that — a smoke test that cannot fail is worse than none.

**Step 2 — `scripts/build-app.sh`** exactly as the brief specifies (zsh,
`set -euo pipefail`, xcodegen, Release build to `app/build`, ad-hoc `codesign`).
Run it and confirm it exits 0 and produces the `.app`.

## NOT yours — Step 3, the visual QA gate

The controller captures and eye-reviews the §8 screenshot set (grid, review in
each style, compare, crop overlay, slider shimmer, render progress, busy pill,
stale-draft banner, error banner). **Do not open the app, do not run the pipeline,
and do not report Task 11 complete** — green tests explicitly do not close it.

The app currently points at a scratch repo. Never point anything at
`~/Projects/rawdog-printworks`; it holds irreplaceable photo data.

## Gates

```
swift test --disable-sandbox --package-path app/PrintworksCore
xcodebuild -project app/RAWdogPrintworks/RAWdogPrintworks.xcodeproj \
  -scheme RAWdogPrintworks -destination 'platform=macOS' \
  OTHER_SWIFT_FLAGS='$(inherited) -disable-sandbox' build
zsh scripts/build-app.sh
```

Exit code is the oracle, never a grep (zsh: `$PIPESTATUS[0]` expands to nothing).

## Report + stop

Write `task-11-report.md` **in this ledger directory**, including the deliberate
failure you induced in the smoke test and what it caught. You cannot commit —
leave the work uncommitted with the intended commit message. Do NOT rewrite
`HANDOFF.md`.
