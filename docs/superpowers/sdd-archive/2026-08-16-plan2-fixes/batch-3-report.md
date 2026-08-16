# Batch 3 report — concurrency, correctness, performance

Date: 2026-08-16. Branch: `johncioni/plan2-fixes` at base `964d708`.

## Changed

1. `PipelineClient` now starts a reporting-only watchdog for mutations. At the
   named 10-minute threshold it publishes elapsed time, then refreshes that
   state every minute. `AppModel` exposes the state and `MainWindow` shows it,
   reveals `run/` in Finder, and explains that Activity Monitor is where the
   user may end a process they judge stuck. Ten minutes is long enough for a
   legitimate multi-photo RAW render while still surfacing a silent stall in a
   useful session timeframe. The subprocess and FIFO continue waiting.
2. `RepoWatcher.stop()` gives all descriptor-close semaphores one absolute
   two-second deadline. `AppRuntime.save()` retires the old watcher in a
   detached utility task, off the MainActor.
3. ImageIO decoding moved from the cache actor into detached utility tasks.
   The actor retains coherent LRU and in-flight state; unrelated keys decode
   concurrently and same-key requests share work. `PreviewImage`'s initializer
   and view surface are unchanged.
4. `findPendingInputFiles` is nonisolated and invoked by a detached utility
   task; only its result is assigned back on the MainActor.
5. `aspectFitRect` returns `.zero` for non-positive image or container sizes.
6. Settings status validation now distinguishes invalid configuration from a
   transient read failure. Invalid paths/toolchains still disable Save; a
   transient status error is shown inline while Save remains available.
7. Each grid card is now a plain-styled, labelled `Button`, providing native
   keyboard and VoiceOver activation. The Retry control remains a separate
   sibling so controls are not nested.

## Hard prohibition and scope

No subprocess `terminate()`, `interrupt()`, kill, signal, timeout exit, or FIFO
release was added. A zero-context added-line scan for those process-control
calls returned no matches. The long-running test also arms a TERM trap and
proves it is not fired before natural release.

No README OUT-OF-SCOPE finding was fixed. The named Grid failure-badge block had
to move unchanged outside the new card button to avoid nesting its Retry button;
its deferred failure-code behavior is untouched. The deferred RepoWatcher
coalesce reset and every named Sidebar/Review/Inspector/build-script item remain
unchanged.

## Mutation RED evidence — every new test

Each production mutation below was applied with `apply_patch`, run with the
focused command shown, observed RED, and immediately restored.

1. `AppModelTests.testLongRunningMutationSurfacesWithoutStoppingSubprocess`
   - Mutation: suppressed the watchdog's `onLongRunning` callback.
   - Command: `swift test --disable-sandbox --package-path app/PrintworksCore --filter AppModelTests.testLongRunningMutationSurfacesWithoutStoppingSubprocess`
   - RED: **exit 1**; `XCTAssertNotNil`, message, and reveal-URL assertions
     failed because observable state never flipped.
2. `AppModelTests.testPendingInputScanRunsOffMainActor`
   - Mutation: called `inputScanner` directly from `performRefresh`.
   - Command: `swift test --disable-sandbox --package-path app/PrintworksCore --filter AppModelTests.testPendingInputScanRunsOffMainActor`
   - RED: **exit 1**; `XCTAssertFalse failed` because the scanner ran on the
     main thread.
3. `RepoWatcherTests.testStopCancellationWaitUsesOneTotalDeadline`
   - Mutation: recreated `.now() + totalWait` for every semaphore.
   - Command: `swift test --disable-sandbox --package-path app/PrintworksCore --filter RepoWatcherTests.testStopCancellationWaitUsesOneTotalDeadline`
   - RED: **exit 1**; elapsed `0.321...` was not less than `0.2` seconds.
4. `PreviewImageCacheTests.testUnrelatedPreviewDecodesCanOverlap`
   - Mutation: performed the synchronous decoder call directly inside the
     cache actor, reproducing the reported serialization.
   - Command: `swift test --disable-sandbox --package-path app/PrintworksCore --filter PreviewImageCacheTests.testUnrelatedPreviewDecodesCanOverlap`
   - RED: **exit 1**; second decode timed out instead of reaching the overlap
     gate. A preliminary `Task.detached` → `Task` mutation stayed green because
     that closure did not serialize here, so it was rejected as evidence.
5. `CropMathTests.testAspectFitRectReturnsZeroForDegenerateImage`
   - Mutation: removed the zero-width image guard.
   - Command: `swift test --disable-sandbox --package-path app/PrintworksCore --filter CropMathTests.testAspectFitRectReturnsZeroForDegenerateImage`
   - RED: **exit 1**; `(400, 0, 0, 600)` was not `.zero`.
6. `SettingsStatusValidationTests.testTransientStatusErrorAllowsSaveButConfigurationFailureDoesNot`
   - Mutation: classified the transient default branch as invalid.
   - Command: `swift test --disable-sandbox --package-path app/PrintworksCore --filter SettingsStatusValidationTests.testTransientStatusErrorAllowsSaveButConfigurationFailureDoesNot`
   - RED: **exit 1**; the transient `allowsSave` `XCTAssertTrue` failed.

Restored focused command: **exit 0**, 6 tests, 0 failures.

## Required gates

- `swift build --disable-sandbox --package-path app/PrintworksCore` — **exit 0**.
- `swift test --disable-sandbox --package-path app/PrintworksCore` — **exit 0**;
  99 tests, 0 failures.
- `xcodebuild -project app/RAWdogPrintworks/RAWdogPrintworks.xcodeproj -scheme RAWdogPrintworks -configuration Release OTHER_SWIFT_FLAGS='$(inherited) -disable-sandbox' build` — **exit 0**, `BUILD SUCCEEDED`. Expected CoreSimulator/FSEvents diagnostics were benign sandbox artifacts.
- `.venv/bin/python -m pytest tests/ -q` — **exit 0**; 295 passed, 1 skipped.

## Checkpoint

No git add or commit was run. No task remains in flight. Per the batch brief,
this report is the checkpoint and `HANDOFF.md` remains unchanged.
