# Task 8 report — ReviewView + CompareView

## What changed

- Added `ReviewView.swift`, replacing `MainWindow`'s `ReviewScreen` stub with
  the black review canvas, fixed 260 pt inspector, segmented style picker,
  `⌘1`–`⌘4` style shortcuts, space-triggered compare mode, previous/next photo
  arrow shortcuts, stale-preview rerender chip, and preview-rendering shimmer.
- Added `CompareView.swift`: a labeled 2×2 view of the four pipeline styles;
  selecting a panel sets `selectedStyle` and returns to the single canvas.
- Reused `PreviewImage` and its one shared hash/size-keyed cache. Added only a
  fit/fill presentation option so review images letterbox while Task 7 grid and
  sidebar callers retain fill behavior. Review/compare calls use
  `RepoPaths.resolve` through that loader and `.id(previewHash)`.
- Added the two required `rerenderPreview` model tests. The production method
  and its call to the same `rebase(stem:before:after:)` used by `applyAdjust`
  were already present in the clean Task 7 baseline; no parallel logic was
  added.
- Regenerated the checked-in Xcode project so both new source files are in the
  Sources build phase (`xcodegen generate`, exit 0).
- `HANDOFF.md` was read and left untouched. No commit was attempted.

## Focused RED → GREEN evidence

1. `testRerenderPreviewSendsExactArgsAndRefreshes`
   - Mutation: removed the terminal `--json` from `rerenderPreview`'s argv.
   - RED command: `swift test --disable-sandbox --package-path app/PrintworksCore --filter AppModelTests.testRerenderPreviewSendsExactArgsAndRefreshes`
   - RED result: exit 1; exact-argv `XCTAssertEqual` failed, showing the emitted
     five-element argv instead of the required six-element argv.
   - Restored `--json`.
   - GREEN: the same focused command exited 0; 1 test, 0 failures. The test also
     asserts exactly one terminal status refresh.

2. `testRerenderPreviewUsesSharedRebaseForBothPairBranches`
   - The matching case refreshes to `after`; the nonmatching case deliberately
     refreshes to the draft's old revision, preventing terminal reconciliation
     from masking a missing shared-rebase call.
   - Mutation: removed `rerenderPreview`'s call to the shared
     `rebase(stem:before:after:)` method (no replacement or copied logic).
   - RED command: `swift test --disable-sandbox --package-path app/PrintworksCore --filter AppModelTests.testRerenderPreviewUsesSharedRebaseForBothPairBranches`
   - RED result: exit 1 with 3 failures: the matching draft became stale and
     stayed at `r1`; the nonmatching draft failed to become stale.
   - Restored the one shared `rebase(...)` call.
   - GREEN: the same focused command exited 0; 1 test, 0 failures. Matching
     `r1→r2` rebases; nonmatching `rX→r2` preserves `r1` and marks stale.

## Gates

- `swift test --disable-sandbox --package-path app/PrintworksCore`
  - Exit 0; 66 tests, 0 failures.
- `xcodebuild -project app/RAWdogPrintworks/RAWdogPrintworks.xcodeproj -scheme RAWdogPrintworks -destination 'platform=macOS' OTHER_SWIFT_FLAGS='$(inherited) -disable-sandbox' build`
  - Exit 0; `** BUILD SUCCEEDED **`.
  - `CoreSimulatorService` and `DVTFilePathFSEvents` diagnostics appeared before
    the successful macOS build, as the dispatch warned they may.

## Shared preview-cache cost

The loader quantizes the maximum pixel dimension to 256 px rungs. For the
repo's 4:3 previews at 4 bytes/pixel, representative canvas entries cost:
1280 px ≈ 4.9 MB, 1536 px ≈ 7.1 MB, 2048 px ≈ 12.6 MB, and
2560 px ≈ 19.7 MB (`bytesPerRow × height`; actual row alignment may vary).
A 2560 px canvas entry therefore costs about eleven 768 px grid entries and can
evict a small grid working set when the shared 256 MiB pool is already full.
I kept the one bounded LRU pool for this scoped task: quantization and the hard
cost/count limits prevent unbounded retention, while splitting it now would be
an unrequested cache refactor. If the controller smoke shows grid re-decode
churn after leaving review, separate canvas/grid pools or a canvas cost ceiling
would be the targeted follow-up.

## Not verified

- I did not launch or operate the app, inspect real photos, take screenshots,
  or perform the controller-owned smoke (style switching updates the canvas;
  space opens the 4-up compare). The build proves compilation only, so Task 8
  is not being reported complete.
- Cache costs above are calculated from the loader's rungs and 4:3 pixel cost;
  runtime cache pressure was not instrumented.
- Crop overlay and its `C` interaction remain Task 9 scope.

Intended commit message (controller-owned):
`feat(app): review screen — canvas, style switching, compare mode, stale-preview chip`
