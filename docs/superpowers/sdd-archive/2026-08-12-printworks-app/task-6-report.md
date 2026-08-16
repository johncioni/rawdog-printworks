# Task 6 Report — RepoWatcher

## Result

- Created `app/PrintworksCore/Sources/PrintworksCore/RepoWatcher.swift`.
- Created `app/PrintworksCore/Tests/PrintworksCoreTests/RepoWatcherTests.swift`.
- `RepoWatcher` opens one `O_EVTONLY` `DispatchSourceFileSystemObject` on a
  private queue for each of the 11 explicitly listed non-recursive directories.
- Event bursts reschedule a generation-checked `DispatchWorkItem`; the eventual
  event is yielded through `AsyncStream<Void>` with `.bufferingNewest(1)`.
- Missing directories are skipped and retried by later `start()` calls and poll
  ticks. Polling uses a sleeping `Task`, never `Timer`.
- `stop()`/`stopPolling()` invalidate generations. `stop()` cancels every source,
  waits for every cancellation handler to close its fd, and is idempotent.
- No other production/test file was changed. In particular, `AppModel.swift`,
  `AppModelTests.swift`, `Package.swift`, project files, Python, fixtures,
  `CLAUDE.md`, progress, and docs were untouched.
- The mandatory stop checkpoint later superseded the controller's initial
  no-touch ruling, so `HANDOFF.md` was refreshed after Task 6 completion.
- No git command and no `xcodebuild` command was run, per controller rulings.

## TDD RED evidence

Tests were written before `RepoWatcher.swift`. Command:

```text
swift test --package-path app/PrintworksCore --filter RepoWatcherTests
```

Actual failing output included:

```text
RepoWatcherTests.swift:16:23: error: cannot find 'RepoWatcher' in scope
RepoWatcherTests.swift:56:23: error: cannot find 'RepoWatcher' in scope
RepoWatcherTests.swift:79:23: error: cannot find 'RepoWatcher' in scope
RepoWatcherTests.swift:102:23: error: cannot find 'RepoWatcher' in scope
error: fatalError
```

Production behavior that makes each test fail:

- `testCoalescedChangeEmission`: fails if recipe/sidecar/style/publish filesystem
  changes do not reach the stream within the stated timeout.
- `testPollingEmitsRepeatedlyAndStops`: fails if polling does not yield at least
  twice while active or yields again after `stopPolling()`.
- `testMissingDirectoryIsRetriedOnLaterStart`: fails if an initially absent
  directory crashes `start()` or is not attached on the later `start()`.
- `testStopIsIdempotentClosesDescriptorsAndStopsEmissions`: fails if repeated
  `stop()` is unsafe, any opened fd is not `EBADF`, tracking is not emptied, or a
  post-stop write emits.

## Required Swift 6.2.4 adaptation

The brief's `withTimeout` helper was retained verbatim. Once `RepoWatcher`
existed, its verbatim mutable iterator captures did not compile under strict
concurrency. Actual errors were:

```text
error: capture of 'iterator' with non-Sendable type
'AsyncStream<Void>.Iterator' in a '@Sendable' closure
error: mutation of captured var 'iterator' in concurrently-executing code
```

Minimal adaptation: each local iterator declaration is
`nonisolated(unsafe) var`. Reads remain sequential: each task group cancels and
joins its losing child before the helper returns and before the next read starts.
No public signature changed. Swift also emits informational `Void?` inference
warnings for the brief's `let first = ...` form; those lines were left unchanged.

No other brief-code deviation was required. The internal
`openFileDescriptors` snapshot is the controller-authorized fd test hook; the
test still verifies closure at the OS boundary using `fcntl(F_GETFD)`/`EBADF`.

## GREEN evidence and anti-flake gates

- First focused GREEN after implementation: 4 tests, 0 failures.
- Integration GREEN before repetition: 50 tests, 0 failures.
- Final toolchain: Apple Swift 6.2.4; target `arm64-apple-macosx15.0`.

Final exact-command full gate, `swift test`: 20 GREEN / 0 RED.
Per-run executed counts (all GREEN):

```text
01=50 02=50 03=50 04=50 05=50 06=50 07=50 08=50 09=50 10=50
11=50 12=50 13=50 14=50 15=50 16=50 17=50 18=50 19=50 20=50
```

Final exact-command focused gate,
`swift test --filter RepoWatcherTests`: 20 GREEN / 0 RED.
Per-run executed counts (all GREEN):

```text
01=4 02=4 03=4 04=4 05=4 06=4 07=4 08=4 09=4 10=4
11=4 12=4 13=4 14=4 15=4 16=4 17=4 18=4 19=4 20=4
```

Final Python gate:

```text
.venv/bin/python -m pytest tests/ -q
295 passed, 1 skipped in 20.63s
```

An earlier attempt to put 20 plain Swift invocations inside one long-lived shell
produced 20 infrastructure REDs before any test executed:
`sandbox-exec: sandbox_apply: Operation not permitted`. Root cause was SwiftPM
trying to create a nested sandbox after that shell was detached by the managed
runner. I first confirmed `--disable-sandbox` made 20/20 full and 20/20 focused
runs green, then superseded that evidence with the final fresh-process runs above
using the controller's exact commands. No sleep/timeout was inflated.

## Refresh-gate ruling

Yes, the existing Task 5 gate satisfies the brief. `AppModel.refresh()` uses
`isRefreshing` to prevent a second active `status`, sets `pendingRefresh` when a
call arrives in flight, and loops only for the trailing request. Existing
`testConcurrentRefreshesCollapseToOneActiveAndOneTrailing` launches five refreshes
and asserts `callCount == 2` and `maxConcurrent == 1`. It was not changed and no
duplicate refresh-gate test was added.

## Concerns / uncertainty

No unresolved functional concern. The managed-runner nested-sandbox behavior is
fully disclosed above and did not occur in any of the 40 final exact-command runs.

DONE
