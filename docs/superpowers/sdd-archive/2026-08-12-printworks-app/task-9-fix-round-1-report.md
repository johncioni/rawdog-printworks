# Task 9 fix round 1 report

## What changed

- **M1:** Moved `.contentShape(Rectangle())` immediately after the crop
  outline's `.frame`, before `.position`. The 5×7 outline no longer installs a
  full-canvas hit region over 8×10, and neither outline includes the black
  letterbox in its hit region.
- **M2:** Split inspector control setup from crop loading. Crop loading is now
  keyed only by stem, review revision, and overlay visibility—not style—and is
  skipped when the overlay is hidden and status already supplies persisted
  crops. A cancelled stale-revision caller no longer recursively starts another
  crop query.
- **M3:** Revision-cache the specific `BAD_INPUT` / `render dims not recorded`
  response as “no suggestion yet” without a banner. Inspector crop rows now
  fall back to `photo.crops` when no queried result is present.
- **M4:** Added argv coverage for exposure-only formatting (`0.35`) and for
  composing temperature plus exposure in one adjust command.
- **M5:** Added an Approve-adjacent line naming every stale preview style that
  must be re-rendered.
- **N6:** The live outline now derives its displayed origin through
  `CropMath.nudged`, the same clamp used on drag completion.
- **N11:** Added a 40-entry LRU crop-result cache and an eight-query bound on
  concurrent tracked crop requests.
- **N12:** Restored the shortcut legend and added the Task 9 `C` crop-overlay
  shortcut.
- N7, N8, N9, N10 and all previously deferred findings were left alone.

## M1 verification

- Final modifier order is `frame → contentShape → position → gesture`.
- Because each content shape is fixed while the view still has the crop
  window's dimensions, 5×7 no longer covers the whole canvas; the distinct
  8×10 perimeter is reachable by hit testing.
- The same window-local shapes exclude every point in the black letterbox, so
  a letterbox press cannot start either crop gesture.
- `CropOverlayView.swift` compiled in the required Xcode build. Per dispatch, I
  did not open the app; the controller still owns the live drag smoke.

## RED → GREEN evidence

All Swift test commands included `--disable-sandbox`; exit code was the oracle.

1. M2/M3/N11 regression set
   - RED: `swift test --disable-sandbox --package-path app/PrintworksCore
     --filter AppModelTests` exited 1. The cancelled request retried (`[P1,
     P1]`), missing render dimensions produced a banner and refired, the
     41-entry cache retained P0, and nine crop queries ran concurrently.
   - GREEN after implementation: the same command exited 0; 36 tests passed.
2. M4 exposure formatting
   - RED mutation: changed exposure formatting from two decimals to one.
     `testSetSliderSendsExposureWithTwoDecimalPlaces` exited 1 with actual
     `--exposure 0.3` versus expected `--exposure 0.35`.
   - GREEN after restoring two decimals: focused test exited 0; 1/1 passed.
3. M4 both-touched composition
   - RED mutation: temporarily cleared pending temperature when exposure was
     touched. `testSetSliderComposesBothTouchedControlsInOneCommand` exited 1;
     actual argv omitted `--temperature 5650`.
   - GREEN after reverting the mutation: focused test exited 0; 1/1 passed.

## Required gates

- `swift test --disable-sandbox --package-path app/PrintworksCore`
  - Exit 0; 75 tests, 0 failures.
- `xcodebuild -project app/RAWdogPrintworks/RAWdogPrintworks.xcodeproj -scheme
  RAWdogPrintworks -destination 'platform=macOS'
  OTHER_SWIFT_FLAGS='$(inherited) -disable-sandbox' build`
  - Exit 0; `BUILD SUCCEEDED`.
  - Managed-environment CoreSimulator/FSEvents diagnostics were non-fatal.

## Not verified here

- I did not open the app or run live crop, letterbox, slider, or approval smoke.
- I did not invoke any pipeline mutation against the real repo.
- `HANDOFF.md` was not rewritten.

## Handoff

The work is intentionally uncommitted because this worktree's git metadata is
outside the writable roots. Intended commit message:

`fix(app): close Task 9 crop overlay review findings`
