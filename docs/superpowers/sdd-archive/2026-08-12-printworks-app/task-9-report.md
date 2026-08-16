# Task 9 report — CropOverlayView + InspectorView

## What changed

- Added `CropOverlayView.swift`: 8×10 solid amber and 5×7 dashed crop
  windows, placed in the actual aspect-fit image rectangle. Drag deltas are
  normalized against that rectangle, passed through `CropMath.nudged`, and
  stored in the review draft only.
- Added `InspectorView.swift`: per-style Warmth and Exposure controls, Reset,
  crop statuses/nudged tags, the three expression-audit checks, note field,
  stale-draft/Re-review surface, and Approve gating/action.
- `PreviewImage` now reports the dimensions of its already-decoded `CGImage` to
  the crop overlay (no second image loader). Missing paths and decode failures
  also have distinct placeholder glyphs/captions (Task 8 N4).
- Added `AppModel.resetAdjust`, revision-keyed/coalesced `crops(stem:)` caching,
  draft mutation helpers, and the single `photos(inDeliveryOf:)` derivation.
  Review, sidebar, toolbar, and grid now use that one delivery helper.
- Integrated the `C` crop toggle, basis chips (`centered fallback` /
  `detection failed — centered`), adjust shimmer, and crop draft nudges in
  `ReviewScreen`.
- Added explicit accessibility labels to every Task 9 control and to Task 8's
  compare toggle, stale-preview chip, and four compare panels. Escape now
  closes compare (Task 8 N5).
- Regenerated `RAWdogPrintworks.xcodeproj`; both new Swift files are in the
  Sources build phase.

## Test-first evidence

Each focused run used `swift test --disable-sandbox --package-path
app/PrintworksCore --filter <test>`; exit code, not output matching, was the
oracle.

1. `testSetSliderSendsOnlyChangedTemperatureControl`
   - RED: temporarily emitted `--temperature 5599` instead of the requested
     `5600`; exit 1 with the exact argv mismatch. The expectation contains no
     `--exposure` flag.
   - GREEN: restored `Self.number(temperature, decimals: 0)`; exit 0, 1/1.
2. `testResetAdjustSendsResetFlag`
   - RED: temporarily omitted `--reset`; exit 1, actual argv ended at
     `--style natural --json` instead of `--reset --json`.
   - GREEN: restored `--reset`; exit 0, 1/1.
3. `testCropsUsesCanonicalArgsAndCachesUntilRevisionChanges`
   - Uses a real `PipelineClient` executable stub that records actual argv and
     moves status from revision `r1` to `r2`.
   - RED: temporarily accepted the stem-only cache regardless of revision;
     exit 1 because the post-revision result stayed `faces` and only one
     `crops --stem P1 --json` invocation was recorded.
   - GREEN: required `cached.revision == revision`; exit 0, 1/1, with one call
     for `r1`, a cache hit on the second request, and one new call for `r2`.

## Gates

- `swift test --disable-sandbox --package-path app/PrintworksCore`
  - exit 0; 69 tests, 0 failures.
- `(cd app/RAWdogPrintworks && xcodegen generate)`
  - exit 0; project generated.
- `xcodebuild -project app/RAWdogPrintworks/RAWdogPrintworks.xcodeproj -scheme
  RAWdogPrintworks -destination 'platform=macOS'
  OTHER_SWIFT_FLAGS='$(inherited) -disable-sandbox' build`
  - exit 0; `BUILD SUCCEEDED`.
  - Xcode printed managed-environment CoreSimulator/FSEvents diagnostics; they
    were non-fatal, and the required exit-code oracle was 0.

## Not verified here

- Per the dispatch stop gate, I did not open the app and did not invoke
  `adjust`, `approve`, `run`, or `preview` against the repo.
- Step 4's real-photo smoke, screenshots, crop drag visual check, slider/sidecar
  writes, approval flow, and live accessibility-tree inspection remain for the
  controller. No claim of runtime/visual verification is made.
- Task 8 N3 (compare-cell aspect/layout polish) was not changed; it is not part
  of Task 9's required carry-forwards.

## Handoff

The work is intentionally uncommitted; I cannot commit in this worktree.
Intended commit message:

`feat(app): crop overlay drag-nudge + inspector (sliders, audit, approve)`

`HANDOFF.md` was not rewritten; this ledger report is the checkpoint.
