# Batch 2 report — tests that cannot fail

Date: 2026-08-16. Branch: `johncioni/plan2-fixes` at base `f93ec85`.

## Changed

- Debouncer tests now use an actor-isolated recorder and await the actual timer
  tasks instead of racing an unsafe array against a fixed sleep.
- `Debouncer.schedule` returns its `Task` as an `@discardableResult`, allowing
  the cancellation test to cancel the exact in-flight timer. Cancellation also
  discards the pending action only when its generation still owns it.
- `LineCollector` buffers `Data`, splits on byte `0x0A`, and decodes only
  complete lines. The existing test now checks each returned batch, and a new
  test splits `é` between chunks.
- Removed the impossible RepoWatcher teardown assertion; the existing `defer`
  is the cleanup. That `defer` runs before XCTest's teardown block, so the old
  block always sampled an already-removed path and could never detect a leak.
- RepoWatcher early-emission coverage races a change stream against a positive
  window-elapsed result, then asserts that the main consumer remains empty.
- Removed the three stale-fd-number assertions. Tests now use
  `openFileDescriptors.isEmpty`, which proves watcher ownership without racing
  kernel fd reuse.

## Mutation evidence — every touched test

Every mutation below was made with `apply_patch`, run with the stated focused
command, observed RED, and immediately restored. The final focused GREEN after
all restores was:

```bash
swift test --disable-sandbox --package-path app/PrintworksCore \
  --filter 'DebouncerTests|LineCollectorTests|RepoWatcherTests'
```

Result: **exit 0**, 19 tests, 0 failures.

### 1. `testOnlyLastScheduledActionRuns`

Exact implementation edit in `Debouncer.schedule`:

```diff
-        pendingAction = action
+        if pendingAction == nil {
+            pendingAction = action
+        }
```

Command: `swift test --disable-sandbox --package-path app/PrintworksCore --filter DebouncerTests.testOnlyLastScheduledActionRuns`

RED: **exit 1** at `DebouncerTests.swift:22`:
`XCTAssertEqual failed: ("[1]") is not equal to ("[2]")`.

### 2. `testScheduledActionDoesNotRunInCancelledTask`

Exact implementation edit in the timer task's cancellation `catch`:

```diff
-                self?.discard(scheduledGeneration: scheduledGeneration)
+                await self?.fire(scheduledGeneration: scheduledGeneration)
```

Command: `swift test --disable-sandbox --package-path app/PrintworksCore --filter DebouncerTests.testScheduledActionDoesNotRunInCancelledTask`

RED: **exit 1** at `DebouncerTests.swift:45`:
`XCTAssertEqual failed: ("[1]") is not equal to ("[]")`.

### 3. `testReassemblesLinesAcrossChunkBoundaries`

Exact implementation edit in `LineCollector.completeLines`:

```diff
-        return completed
+        return []
```

Command: `swift test --disable-sandbox --package-path app/PrintworksCore --filter LineCollectorTests.testReassemblesLinesAcrossChunkBoundaries`

RED: **exit 1**. `LineCollectorTests.swift:13` got `[]` instead of `["abc"]`;
line 17 got `[]` instead of `["def"]`.

### 4. `testReassemblesUTF8ScalarSplitAcrossChunks`

Exact implementation edit reintroduced per-chunk UTF-8 decoding:

```diff
-        buffer.append(data)
+        buffer.append(Data(String(decoding: data, as: UTF8.self).utf8))
```

Command: `swift test --disable-sandbox --package-path app/PrintworksCore --filter LineCollectorTests.testReassemblesUTF8ScalarSplitAcrossChunks`

RED: **exit 1**. `LineCollectorTests.swift:29` and `:33` both got `["��"]`
instead of `["é"]`.

### 5. `testCoalescedChangeEmission`

Exact implementation edit removed this entry from
`RepoWatcher.watchedDirectories`:

```diff
-        "sidecars",
```

Command: `swift test --disable-sandbox --package-path app/PrintworksCore --filter RepoWatcherTests.testCoalescedChangeEmission`

RED: **exit 1**. The load-bearing sidecar assertion at
`RepoWatcherTests.swift:58` reported `XCTAssertNotNil failed` (the timed-out
iterator also caused the later `:66` and `:74` checks to fail).

### 6. `testBurstIsEmittedExactlyOnceAfterCoalesceDelay`

Exact implementation edit forced immediate emission:

```diff
-        let deadline = min(trailingDeadline, maximumDeadline)
+        let deadline = now
```

Command: `swift test --disable-sandbox --package-path app/PrintworksCore --filter RepoWatcherTests.testBurstIsEmittedExactlyOnceAfterCoalesceDelay`

RED: **exit 1**. At `RepoWatcherTests.swift:109`, `.change` was not equal to
`.windowElapsed`; at `:112`, `30` was not equal to `0`. The arrival/settling
checks at `:125` and `:131` also got `30` instead of `1`.

### 7a. `testStopIsIdempotentClosesDescriptorsAndStopsEmissions`

Exact implementation mutation made cancellation retain its owned watch:

```diff
-            watches.removeAll()
```

```diff
-            if watches[relativePath] === watch {
+            if watches[relativePath] !== watch {
```

Command: `swift test --disable-sandbox --package-path app/PrintworksCore --filter RepoWatcherTests.testStopIsIdempotentClosesDescriptorsAndStopsEmissions`

RED: **exit 1** at `RepoWatcherTests.swift:292`: `XCTAssertTrue failed` for
`watcher.openFileDescriptors.isEmpty`.

### 7b. `testStopReturnsWhenCalledFromPrivateQueue`

The same two-line retained-watch mutation above was active.

Command: `swift test --disable-sandbox --package-path app/PrintworksCore --filter RepoWatcherTests.testStopReturnsWhenCalledFromPrivateQueue`

RED: **exit 1** at `RepoWatcherTests.swift:325`: `XCTAssertTrue failed - stop
should release every watched descriptor`.

### 7c. `testVanishedDirectoryIsDiscardedAndRetriedOnlyWhenRequested`

Exact implementation edit prevented a vanished watch from being discarded:

```diff
-            if watches[relativePath] === watch {
+            if watches[relativePath] !== watch {
```

Command: `swift test --disable-sandbox --package-path app/PrintworksCore --filter RepoWatcherTests.testVanishedDirectoryIsDiscardedAndRetriedOnlyWhenRequested`

RED: **exit 1**. `RepoWatcherTests.swift:414` reported `XCTAssertTrue failed -
the vanished directory watch was retained`; `:436` also reported
`XCTAssertNotNil failed - explicit start should re-attach the recreated directory`.

## Repeated Swift stability runs

The exact full command was run in five separate processes:

```bash
swift test --disable-sandbox --package-path app/PrintworksCore
```

All five runs exited 0 with **93 tests, 0 failures**. Test-suite durations were
15.113s, 15.043s, 14.812s, 15.711s, and 14.261s.

## Required gates

- `swift build --disable-sandbox --package-path app/PrintworksCore` — **exit 0**.
- `swift test --disable-sandbox --package-path app/PrintworksCore` — **exit 0**;
  93 tests, 0 failures (and 5/5 repeated runs as above).
- `xcodebuild -project app/RAWdogPrintworks/RAWdogPrintworks.xcodeproj -scheme RAWdogPrintworks -configuration Release OTHER_SWIFT_FLAGS='$(inherited) -disable-sandbox' build` — **exit 0**, `BUILD SUCCEEDED`. CoreSimulator/FSEvents diagnostics were benign sandbox artifacts.
- `.venv/bin/python -m pytest tests/ -q` — **exit 0**; 295 passed, 1 skipped.

## Scope and checkpoint

No README OUT-OF-SCOPE item was changed, including the named adjacent tests,
the deferred RepoWatcher coalesce-reset item, and `scripts/build-app.sh`. No git
add or commit was run. No task remains in flight. Per the batch brief, this
report is the checkpoint and `HANDOFF.md` remains unchanged.
