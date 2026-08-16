# Task 4 Report: CropMath + Debouncer

## Status: DONE

## What was built

Per the task-4 brief (`.superpowers/sdd/2026-08-12-printworks-app/task-4-brief.md`), all paths
interpreted per the standing PATH CONVENTION ruling (bare paths in the brief are relative to
`app/PrintworksCore/`):

- `app/PrintworksCore/Sources/PrintworksCore/CropMath.swift` — new file:
  - `CropMath.nudged(_:dx:dy:)` — translates a `CropWindow` by (dx, dy) in normalized units,
    clamping x to `[0, 1-w]` and y to `[0, 1-h]`; w/h/source pass through unchanged.
  - `CropMath.aspectFitRect(image:container:)` — the letterboxed/pillarboxed `CGRect` an image
    occupies when aspect-fit centered inside a container.
  - `RepoPaths.resolve(_:repo:)` — resolves a repo-relative contract path to an absolute `URL`,
    passing already-absolute paths through unchanged.
- `app/PrintworksCore/Sources/PrintworksCore/Debouncer.swift` — new file:
  - `final class Debouncer: @unchecked Sendable` with `init(delay: Duration)`,
    `schedule(_:)` (cancels any pending action and replaces it), `flush()` (runs a pending
    action immediately, synchronously from the caller's perspective — the approve-path escape
    hatch), and `var hasPending: Bool`.
- `app/PrintworksCore/Tests/PrintworksCoreTests/CropMathTests.swift` — `CropMathTests` +
  `RepoPathsTests` (the brief's Step-1 code block defines three test classes across two listed
  test files; `RepoPathsTests` was placed alongside `CropMathTests` since the brief's Files
  section lists only `CropMathTests.swift` and `DebouncerTests.swift`).
- `app/PrintworksCore/Tests/PrintworksCoreTests/DebouncerTests.swift` — `DebouncerTests`.
- `app/PrintworksCore/Sources/PrintworksCore/Contract.swift` — added the explicit
  `public init(x:y:w:h:source:)` to `CropWindow` that the brief calls for, since Swift only
  auto-synthesizes an *internal* memberwise initializer for a public struct. No other change to
  this file; `CropWindow` itself was reused as-is per the standing instruction not to declare a
  second crop-window type.

All test code and public signatures were taken verbatim from the brief, as instructed. Two
implementation-body deviations from the brief's literal code were required to make it compile
under this repo's toolchain (Swift 6.2.4 / Xcode 26.3, `swift-tools-version:6.0`, strict
concurrency) — both are internals only; every signature, test, and observable behavior is
unchanged from the brief:

1. **`CropMath.swift` needed an explicit `import CoreGraphics`.** With only `import Foundation`
   (as the brief's snippet has it), `CGRect(x:y:width:height:)` failed to resolve on this SDK
   — the compiler could only see `CGRect`'s zero-argument initializer ("argument passed to call
   that takes no arguments"), reproduced in isolation with a two-line `swift` script. `CGSize`
   was unaffected. Adding `import CoreGraphics` alongside `import Foundation` fixed it with no
   other change.

2. **`Debouncer.fire()` needed `NSLock.withLock` instead of manual `lock()`/`unlock()`.** The
   brief's `fire()` is `async` and called `lock.lock()` / `lock.unlock()` directly around the
   state read; under this toolchain `NSLock.lock()`/`unlock()` are unavailable from asynchronous
   contexts at all (diagnostic: "instance method 'lock' is unavailable from asynchronous
   contexts; Use async-safe scoped locking instead"), regardless of whether an `await` actually
   spans the critical section. I replaced the lock/unlock pair with a single
   `lock.withLock { ... }` closure that reads and clears `pendingAction`/`pendingTask` and
   returns the captured action, then `await`s it outside the closure — same critical-section
   shape, same behavior, no API change. `schedule()` and `hasPending` are synchronous and their
   `lock.lock()`/`unlock()` calls were left untouched (they compiled without complaint).

## Debouncer determinism concern (flagged per instructions)

`DebouncerTests.testOnlyLastScheduledActionRuns` (verbatim from the brief) is not a pure logical
test — it schedules two actions on a 50ms-delay debouncer, sleeps 150ms of real wall-clock time,
then asserts only the second action fired. This is inherently a sleep-and-hope pattern: it
relies on the OS scheduler firing the debounced `Task.sleep(for: .milliseconds(50))` and
completing the resulting `fire()` well within the 150ms window the test then waits.

I did not rewrite this test to remove the wall-clock dependency, because doing so would require
either (a) injecting a fake/virtual clock abstraction into `Debouncer`, which changes its public
`init(delay: Duration)` shape that the brief specifies verbatim and that Task 9 will depend on,
or (b) using Swift Testing's clock-mocking facilities, which aren't available to XCTest-based
async sleep code without a bigger restructure — both out of scope for "implement this brief's
exact signatures." Per your instruction to flag this rather than paper over it, here is what I
did instead to establish confidence in lieu of true determinism:

- Ran the full suite (including `DebouncerTests`) **5 times** standalone (`swift test`), all
  green.
- Ran `DebouncerTests` alone **10 times** in a sequential loop, all green, with
  `testOnlyLastScheduledActionRuns` consistently completing in 0.151–0.161s (i.e., the 50ms
  debounce fired essentially immediately after its delay, leaving ~100ms+ of margin before the
  150ms assertion point every time).
- Ran `DebouncerTests` **4 more times concurrently** (4 parallel `swift test` invocations
  competing for CPU) to add scheduler contention; all 4 still passed with the same ~150–168ms
  timing.
- Total: 19 runs of the debounce timing test across sequential and concurrent conditions, 0
  failures observed. The 3x margin (100ms delay-to-fire budget within a 150ms wait, for a 50ms
  debounce) held steady across all of them, which is what makes it reliable in practice even
  though it is not a formal guarantee — under sufficiently extreme scheduler starvation it could
  in principle flake. I did not add any additional sleeps or retries to mask this; it's the same
  timing shape the brief specified.

## Verification

All four required checks below were run from a clean worktree after the implementation, in this
order.

### 1. `swift test --package-path app/PrintworksCore`

Run count: **1 full run with full output captured** + **5 additional full-suite runs** (only the
`Test Suite 'All tests'` start/pass lines captured on the repeats) + **10 filtered
`--filter DebouncerTests` runs** + **4 concurrent filtered runs** = **20 total invocations**,
zero failures across all of them.

First full run (all 25 tests — the 20 pre-existing plus 5 new):

```
Test Suite 'ContractTests' passed ... Executed 10 tests, with 0 failures (0 unexpected)
Test Suite 'CropMathTests' passed ... Executed 2 tests, with 0 failures (0 unexpected)
Test Suite 'DebouncerTests' passed ... Executed 2 tests, with 0 failures (0 unexpected) in 0.152s
Test Suite 'LineCollectorTests' passed ... Executed 2 tests, with 0 failures (0 unexpected)
Test Suite 'PipelineClientTests' passed ... Executed 8 tests, with 0 failures (0 unexpected)
Test Suite 'RepoPathsTests' passed ... Executed 1 test, with 0 failures (0 unexpected)
Test Suite 'PrintworksCorePackageTests.xctest' passed ... Executed 25 tests, with 0 failures (0 unexpected) in 2.549 (2.554) seconds
Test Suite 'All tests' passed at 2026-08-14 01:52:06.683.
	 Executed 25 tests, with 0 failures (0 unexpected) in 2.549 (2.557) seconds
```

5 repeat full-suite runs (start/pass lines only, confirming stability):

```
=== full run 1 === Test Suite 'All tests' started at 01:52:38.049 / passed at 01:52:40.634
=== full run 2 === Test Suite 'All tests' started at 01:52:41.523 / passed at 01:52:43.956
=== full run 3 === Test Suite 'All tests' started at 01:52:44.850 / passed at 01:52:47.258
=== full run 4 === Test Suite 'All tests' started at 01:52:48.218 / passed at 01:52:50.743
=== full run 5 === Test Suite 'All tests' started at 01:52:51.740 / passed at 01:52:54.185
```

10 sequential `--filter DebouncerTests` runs — every one reported
`Executed 2 tests, with 0 failures (0 unexpected)`, timing for
`testOnlyLastScheduledActionRuns` ranging 0.151s–0.161s across the 10 runs.

4 concurrent `--filter DebouncerTests` runs (launched together to add scheduler contention) —
all 4 exited 0 with `Executed 2 tests, with 0 failures (0 unexpected)`, timing 0.151s–0.168s.

### 2. xcodebuild app target build

```
cd app/RAWdogPrintworks
xcodebuild -project RAWdogPrintworks.xcodeproj -scheme RAWdogPrintworks -configuration Debug build
...
** BUILD SUCCEEDED **
```

The `RAWdogPrintworks` target links `PrintworksCore` as a local Swift package dependency and
built clean with no warnings introduced by the new files.

### 3. `.venv/bin/python -m pytest tests/ -q` (from worktree root)

```
........................................................................ [ 24%]
........................................................................ [ 48%]
........................................................................ [ 72%]
............................................s........................... [ 97%]
........                                                                 [100%]
295 passed, 1 skipped in 22.51s
```

Matches the required unchanged baseline exactly. No Python file or fixture was touched.

### 4. `git status --porcelain`

Before commit (only the intended files, no build products):

```
 M app/PrintworksCore/Sources/PrintworksCore/Contract.swift
?? app/PrintworksCore/Sources/PrintworksCore/CropMath.swift
?? app/PrintworksCore/Sources/PrintworksCore/Debouncer.swift
?? app/PrintworksCore/Tests/PrintworksCoreTests/CropMathTests.swift
?? app/PrintworksCore/Tests/PrintworksCoreTests/DebouncerTests.swift
```

After `git add app/PrintworksCore && git commit`, `git status --porcelain` is clean (empty
output, not shown here since there is nothing to show).

## Commit

```
3dc79044b1a57125defac785b2662dd3d2c7877a  feat(app): crop nudge math + cancellable debouncer
```

Branch: `johncioni/plan2-printworks-app` (not pushed, per instructions). 5 files changed, 143
insertions.

## Concerns for reviewer

1. **Two internal-only deviations from the brief's literal code**, both required to compile on
   this toolchain and both fully explained above: `import CoreGraphics` added to `CropMath.swift`,
   and `Debouncer.fire()`'s manual lock/unlock replaced with `NSLock.withLock`. No public
   signature, test, or behavior changed — verified by the fact that the brief's tests, taken
   verbatim, pass unmodified against this implementation.
2. **`RepoPathsTests` placement**: the brief's Step-1 code block defines three test classes
   (`CropMathTests`, `RepoPathsTests`, `DebouncerTests`) but its Files section names only two
   test files. I put `RepoPathsTests` in `CropMathTests.swift` since `RepoPaths` is one of the
   interfaces documented under the same "Produces" bullet list as `CropMath`. Flagging in case
   the plan intended a third file.
3. **`DebouncerTests.testOnlyLastScheduledActionRuns` is wall-clock-dependent**, as detailed
   above — this is inherent to the brief's verbatim test and public API; I did not alter it, but
   ran it 19 times total (sequential + concurrent) with 0 failures and a consistent ~100ms
   margin, which is the empirical case for why it's reliable in practice rather than a proof it
   can never flake.
