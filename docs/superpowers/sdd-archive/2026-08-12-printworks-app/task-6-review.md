# Task 6 review — `RepoWatcher` (commit b3fcf2a)

Reviewer: independent (did not write this code). Everything below was reproduced;
nothing is asserted from reading alone.

- **SPEC VERDICT: ❌** — the watched set, event mask, coalescing mechanism,
  poll fallback and fd hygiene all match the brief, and I verified each one
  works. But the `changes` stream is **single-shot**: any cancellation of a
  consumer permanently finishes it, and `stop()` cannot terminate a consumer, so
  the only way to end the consuming loop is the one action that destroys the
  watcher. Spec §6 item 5 makes this stream the app's *only* refresh path ("No
  refresh button exists"). Separately, the 500 ms coalesce is a pure trailing
  debounce with no max-wait, so **sustained** external activity produces zero
  emissions (measured: 0 in 6 s).
- **QUALITY VERDICT: changes required.**

Scratch harnesses live in
`/private/tmp/claude-501/-Users-john-Projects-rawdog-printworks/e7e004ec-ea32-40c7-ad29-efa604d73354/scratchpad/sandbox/`
(`base`, `nocoalesce`, `probe`, `mut`, `deadlock`, `hook`, `verbatim`, `prevfull`).

---

## Findings

### C1 (Critical) — one cancelled consumer kills the watcher permanently, and `stop()` cannot end a consumer loop

**What is wrong.** `RepoWatcher` builds exactly one `AsyncStream` in `init` and
publishes it as `public let changes`. `AsyncStream.Iterator.next()` installs a
cancellation handler that calls the stream storage's `cancel()`, which **finishes
the stream** — not just that read. So the first time any task suspended in
`next()` is cancelled, the stream is terminated for the whole life of the object.
There is no way to obtain a new one. Compounding it, `stop()` never calls
`continuation.finish()` (only `deinit` does), so a `for await` consumer cannot
exit by stopping the watcher — cancellation is the *only* way to end it, and
cancellation is what destroys it.

**Evidence.**

```
$ cd .../scratchpad/sandbox/probe && swift test --filter ReviewerProbeTests
ReviewerProbeTests.swift:107: error: -[...testStreamSurvivesATimedOutRead] :
  XCTAssertNotNil failed - iterator is dead after a timed-out read
ReviewerProbeTests.swift:129: error: -[...testFreshIteratorAfterATimedOutRead] :
  XCTAssertNotNil failed - stream is permanently finished after one cancelled read
PROBE-D  read-after-timeout-got-value  = false
PROBE-D2 fresh-iterator-got-value      = false
```

Then the Task 7 shape — a SwiftUI `.task {}` consumer cancelled on disappear and
re-established on reappear, against the same live, started watcher:

```
$ swift test --filter ReviewerLifecycleTests
ReviewerLifecycleTests.swift:48: error: XCTAssertGreaterThan failed: ("0") is not
  greater than ("0") - watcher is permanently dead after the first consumer was cancelled
PROBE-LIFECYCLE consumerA=1 consumerB-after-recycle=0
PROBE-RESTART   emission-after-stop-then-start = true      <- the kqueue side is fine
```

And `stop()` does not terminate consumers:

```
$ swift test --filter ReviewerPublishTests
PROBE-STOPFINISH consumer-loop-exited-after-stop = false
```

So: `stop()`/`start()` genuinely restart the filesystem sources (PROBE-RESTART
true) — the class advertises a restartable lifecycle — but the stream that
carries the events cannot be restarted at all.

**Impact.** Spec §6 item 5 and §6's busy-pill paragraph make this stream the sole
mechanism by which the UI learns about anything: there is no refresh button. A
single cancelled consumer silently freezes the entire app's view of the repo,
with no error, no banner, and no recovery short of relaunching.

**Concrete fix.** Make `changes` a computed property that vends a fresh stream
per call, multiplexed over a registry:

```swift
private var continuations: [UInt64: AsyncStream<Void>.Continuation] = [:]
private var nextConsumerID: UInt64 = 0

public var changes: AsyncStream<Void> {
    AsyncStream(bufferingPolicy: .bufferingNewest(1)) { c in
        let id = lock.withLock { nextConsumerID += 1; continuations[nextConsumerID] = c; return nextConsumerID }
        c.onTermination = { [weak self] _ in
            guard let self else { return }
            self.lock.withLock { _ = self.continuations.removeValue(forKey: id) }
        }
    }
}
```

…and emit to `continuations.values` in `emitCoalesced`/`emitPoll`. Caution while
doing it: today `yield` is called while holding `lock`; with an `onTermination`
that also takes `lock` you must not create a lock inversion — deregister off the
lock (or snapshot the continuations under the lock and yield outside it, which is
the cleaner shape anyway). Add a test that cancels a consumer and proves a new
consumer still receives events, and one that proves `stop()` leaves the watcher
resumable.

**Origin: implementation.** The brief only says `var changes: AsyncStream<Void>`;
the single-instance-created-in-`init` design, and the decision to finish the
continuation only in `deinit`, are the implementer's.

---

### I1 (Important) — coalescing, the headline behaviour of this task, is not tested at all

**What is wrong.** `testCoalescedChangeEmission`'s comment says "Burst of writes →
exactly one coalesced emission" but every assertion is `XCTAssertNotNil`. Nothing
in the suite counts emissions, so the suite cannot see coalescing disappear.

**Evidence.** I built a watcher with **no coalescing whatsoever** —
`directoryChanged` yields once per raw kqueue event — and ran the shipped suite
unmodified against it:

```
$ cd .../sandbox/nocoalesce && swift test
Test Case '-[...testCoalescedChangeEmission]'                     passed (0.953 seconds)
Test Case '-[...testMissingDirectoryIsRetriedOnLaterStart]'       passed (0.008 seconds)
Test Case '-[...testPollingEmitsRepeatedlyAndStops]'              passed (0.340 seconds)
Test Case '-[...testStopIsIdempotentClosesDescriptorsAndStopsEmissions]' passed (0.268 seconds)
	 Executed 4 tests, with 0 failures (0 unexpected)
```

An inflated coalesce window survives too (`coalesce-10x`: 500 ms default becomes
5 s, violating spec §6's stated 500 ms) — see the mutation matrix under I2.

The implementation itself **is** correct; it is only untested. A reviewer-written
counting test discriminates cleanly (30 writes at 10 ms spacing, 200 ms coalesce,
actively-draining consumer):

```
=== BASE (shipped impl) ===   REVIEWER-PROBE emissions-for-30-file-burst = 1   PASS
=== NOCOALESCE (mutant) ===   REVIEWER-PROBE emissions-for-30-file-burst = 30  FAIL
```

**Concrete fix.** Add that counting test (it is
`sandbox/base/Tests/PrintworksCoreTests/ReviewerCoalesceTests.swift`; ~35 lines,
uses an `actor Counter` and a `for await` consumer, no new API), plus a second
assertion that the emission does not arrive before `coalesce` has elapsed so a
zero-delay implementation is also caught.

**Origin: the brief, then the implementation.** The brief's mandated Step 1 code
carries the misleading comment and the weak assertion, so the implementer
inherited it — but the implementer added three tests *beyond* the brief
(polling, missing-directory, fd closure) and did not add the one for the
behaviour the task is named after.

---

### I2 (Important) — 6 of the 11 watched directories can be deleted with the suite still green, including `Input/` and `run/`

**Evidence.** Full mutation matrix, each mutant applied to a fresh copy of
`RepoWatcher.swift` and run against the *unmodified* shipped tests
(`sandbox/mut`, driver output in `tasks/bgx280lc7.output`):

| mutation | result |
|---|---|
| `no-coalesce` (yield per raw event) | **SURVIVED** (4/4 green) |
| `coalesce-10x` (500 ms → 5 s) | **SURVIVED** (4/4 green) |
| `no-fd-close` (drop `Darwin.close`) | killed — `testStopIsIdempotent…` |
| `no-sem-wait` (drop `closed.wait()` loop) | killed — `testStopIsIdempotent…` |
| `no-source-cancel` (drop `source.cancel()`) | killed — `testStopIsIdempotent…` |
| `stoppolling-noop` | killed — `testPollingEmitsRepeatedlyAndStops` |
| `no-discard-missing` (never discard a vanished dir) | **SURVIVED** |
| `start-once-only` (2nd `start()` no-ops when any watch exists) | **SURVIVED** |
| drop `Input` | **SURVIVED** |
| drop `previews` | killed — `testMissingDirectoryIsRetriedOnLaterStart` |
| drop `sidecars` | killed — `testCoalescedChangeEmission` |
| drop `recipes` | killed — `testCoalescedChangeEmission`, `testStopIsIdempotent…` |
| drop `config` | **SURVIVED** |
| drop `config/styles` | killed — `testCoalescedChangeEmission` |
| drop `config/lab-profiles` | **SURVIVED** |
| drop `config/rawtherapee-seed` | **SURVIVED** |
| drop `Output` | **SURVIVED** |
| drop `Output/photos` | killed — `testCoalescedChangeEmission` |
| drop `run` | **SURVIVED** |

`Input/` is spec §6 item 5's own worked example ("file dropped in `Input/`") and
`run/` is what clears the busy pill on lock release (spec §6, §7) — both are
unprotected. `config` (bare) is where `toolchain.lock` lives, a fingerprint input
per CLAUDE.md.

I separately confirmed **all 11 directories do work** — a new file in each of the
eleven produces an emission (`PROBE-F new-file-no-emission: []`), and the list in
`RepoWatcher.swift:5-17` matches the brief's enumeration exactly, in order.

**Concrete fix.** Replace the ad-hoc four writes in `testCoalescedChangeEmission`
with a loop over the 11-element list (my `testEveryWatchedDirectoryEmits` in
`sandbox/probe/.../ReviewerProbeTests.swift` does exactly this and runs in 1.6 s).
**Origin: the brief** (its mandated test only exercises 4 of the 11), compounded
by the implementer not extending it while it was adding other tests.

---

### I3 (Important) — `stop()` deadlocks permanently if it is ever reached on the watcher's own queue; `deinit` is that path

**What is wrong.** `stop()` blocks on `DispatchSemaphore.wait()` (no timeout) for
each source's cancel handler, and those handlers run on the private `queue`. If
`stop()` is itself executing on `queue`, the handlers can never be dequeued.
`deinit` calls `stop()`, and the queue *does* transiently hold a strong `self`:
`source.setEventHandler { [weak self] in self?.directoryChanged(...) }` upgrades
the weak reference to a strong one for the duration of the call. If the last
external reference is released during that window, the handler's own release is
the final one and `deinit` runs **on `queue`**.

**Evidence — the deadlock is real.** I added one hook to a scratch copy
(`_reviewerRunOnPrivateQueue`, which only does `queue.async(execute:)`) and called
`stop()` through it, with a 6 s watchdog:

```
$ .../sandbox/hook/.build/release/HK
calling stop() from the watcher's own private queue…
RESULT: DEADLOCK — stop() never returned when called on the watcher's queue
(exit 3)
```

**Evidence — I could not reach it from unmodified code.** A randomised release
sweep (11 sources, continuous storm thread, release offset swept 0–3 ms in 37 µs
steps, plus a plain burst variant) ran **4500 iterations with no deadlock**
(`sandbox/deadlock`, `COMPLETED 1500 iterations with no deadlock` +
`COMPLETED 3000 iterations with no deadlock`). Every closure in the shipped class
uses `[weak self]`, so the window is only the few microseconds a handler holds
its temporary strong reference. So: structurally reachable, catastrophic when
hit, not reproduced in practice.

**Concrete fix (cheap, belt-and-braces).** Tag the queue and skip the blocking
wait when already on it:

```swift
private static let queueKey = DispatchSpecificKey<Void>()
// in init: queue.setSpecific(key: Self.queueKey, value: ())
// in stop(): let onOwnQueue = DispatchQueue.getSpecific(key: Self.queueKey) != nil
//            for watch in stopped.2 where !onOwnQueue { watch.closed.wait() }
```

Optionally bound the wait (`.wait(timeout: .now() + 2)`) so a future regression
degrades instead of hanging. **Origin: implementation** — the brief says only
"`stop()` cancels sources and closes fds"; blocking `deinit` on an unbounded
semaphore is the implementer's mechanism.

---

### I4 (Important) — the coalesce has no max-wait: sustained external activity emits nothing at all

**What is wrong.** Every event bumps `coalesceGeneration` and reschedules, so
`emitCoalesced` only ever fires after a full quiet window. There is no cap.

**Evidence.** Default 500 ms coalesce, one write to `run/` every 200 ms for 6 s,
active `for await` consumer:

```
$ swift test --filter ReviewerStarvationTests
PROBE-STARVE 6s of activity @200ms gaps (29 writes): emissions during=0, after quiet=1
```

**Impact.** Spec §6 wants the busy pill up *while* an external CLI run holds the
lock, and the 5 s fallback poll is started by `AppModel` only once `busyExternally`
is true — which requires a `status` refresh, which requires an emission. If an
external command keeps touching watched directories at sub-500 ms intervals, the
app never learns the lock is held, never raises the pill, and never starts the
fallback poll. (In the current pipeline the gaps are render-length so this does
not bite today — see "verified fine" — but the property is unbounded and the
guard rail costs three lines.)

**Concrete fix.** Record `firstPendingAt` when `pendingChange` goes false→true and
schedule at `min(now + coalesceDelay, firstPendingAt + maxWait)` with
`maxWait` = 2 s, or simply have `AppModel` start the fallback poll unconditionally
rather than only when `busyExternally`. **Origin: the brief** — its Step 3 text
mandates "every event sets a pending flag and (re)schedules a coalesce timer",
which is exactly an uncapped trailing debounce.

---

### I5 (Important) — the suite is flaky at HEAD, and the recorded "20/20 consecutive green" gate does not reproduce

**What is wrong.** I measured `swift test` at b3fcf2a across **50 runs: 48 green,
2 red**, both `AppModelTests.testDebouncersAreKeyedPerStemAndStyle` — the exact
test the ledger records as the historical ~14 % flake that Task 5's fix round was
supposed to close.

```
=== RUN 10 RED ===
AppModelTests.swift:312: XCTAssertEqual failed:
  ("["P1|filmic", "P2|bw"]") is not equal to ("["P1|natural", "P1|filmic", "P2|bw"]")
=== RUN 12 RED ===
AppModelTests.swift:312: XCTAssertEqual failed:
  ("["P2|bw", "P1|filmic"]") is not equal to ("["P2|bw", "P1|filmic", "P1|natural"]")
FINAL: 18 green / 2 red of 20 runs; per-run Executed 50 tests
```
(a second, later set was `HEAD FULL SUITE: 30 green / 0 red of 30`; the red set
ran while the machine was under elevated load.)

**Root cause, confirmed with a sanitiser, not by reasoning.** `FakeClient` in
`AppModelTests.swift:6-33` is `@unchecked Sendable` with a bare
`var mutateLog: [[String]]` appended from `nonisolated func mutate`, which runs
off the MainActor — concurrent adjusts append concurrently and lose an entry
(note both failures show a log order different from the scheduling order). TSan
on the whole 50-test suite reports **exactly one** race, and it is that one:

```
$ swift test --sanitize=thread
WARNING: ThreadSanitizer: Swift access race (pid=94957)
    #0 FakeClient.mutate<A>(_:args:onEvent:) AppModelTests.swift
SUMMARY: ThreadSanitizer: Swift access race AppModelTests.swift in FakeClient.mutate<A>(...)
	 Executed 50 tests, with 0 failures
```

**This is not Task 6's fault** and I checked rather than assumed:
`AppModelTests` runs *before* `RepoWatcherTests` in every run (suite start order
captured from a real run), the pre-Task-6 tree at 3212f6c contains the same racy
fixture, and `--filter AppModelTests` is 30/30 green at both revisions. It is the
ledger's own deferred "M4 … unsynchronized mutateLog", now demonstrably capable
of turning the suite red under load. But the Task 6 gate line "swift test 20/20
consecutive green at 50 tests" is not reproducible, and it is worth noting that
my own first attempt at that gate reported a false 20/20 because a naive
`grep -m1 "Executed N tests, with 0 failures"` matches the *first suite's* line,
not the run's — an easy way to record a green that never happened.

**Concrete fix.** Put `mutateLog` behind the lock `FakeClient` already could have
(`private let lock = NSLock()`, append and read under it) — three lines in
`AppModelTests.swift`. Re-run TSan to confirm the suite goes race-free.
**Origin: pre-existing (Task 5 / the Task 5 brief's fixture).** Fix it now,
before Task 7 adds a watcher-driven refresh loop on top of it.

---

### M1 (Minor) — in-place edits of existing files are invisible (the real cost of kqueue-vs-FSEvents)

kqueue on a directory reports entry changes, not content changes. A non-atomic
rewrite of an existing file inside a watched directory produces nothing; the
atomic control case works:

```
PROBE-INPLACE emission-for-in-place-edit  = false
PROBE-ATOMIC  emission-for-atomic-replace = true
```

I checked what this actually costs: every pipeline writer that touches a watched
directory uses temp+`os.replace` (`recipe.py:50-52`, `pp3.py:118-120`,
`driver.py:138`, `manifest.py:48-50`, `ingest.py:205`, `publish.py:114/139/143`),
and `render.py`'s two `write_text` calls only run when the file does not exist
(a create, which does fire). The one non-atomic writer of a watched file is
`toolchain.write_lock()` (`toolchain.py:153`, `Path.write_text`) — and `grep`
shows it is called only from `tests/test_toolchain.py`, never from a CLI path.
So the exposure is hand-edits to `config/styles/*.pp3`,
`config/lab-profiles/*`, `config/rawtherapee-seed/*` and `config/toolchain.lock`
with an editor that truncates in place. This is the concrete, measured content of
the ledger's already-flagged "spec says FSEvents, plan mandates kqueue" note.
**Origin: the plan/brief.** Cheapest mitigation: a comment in
`RepoWatcher.swift` stating the limitation, so nobody later assumes content
changes are covered.

### M2 (Minor) — a *re*-publish is caught only by accident

`Output/photos/<stem>/` is not watched, so `publish.py`'s new `vNNN` directory and
`current` symlink swap (both inside it) emit nothing:

```
PROBE-REPUBLISH emission-for-new-version+symlink-swap = false
PROBE-REBUILDVIEWS emission                            = true
```

It is caught only because `driver.py:625` calls `publish.rebuild_views()` right
after every publish, and that rmtree+mkdir's `Output/TIF|JPG|PDF`, which *are*
direct children of the watched `Output/`. If `rebuild_views` is ever made
incremental, the app goes blind to republishes. **Origin: the brief's watch list.**
Fix (if wanted): watch `Output/photos/<stem>` per published stem, or leave it and
record the dependency in a comment.

### M3 (Minor) — the "discard a vanished directory" behaviour is untested, and a recreated directory is not re-attached

The `no-discard-missing` mutant survives the suite. And the behaviour itself
strands the directory:

```
PROBE-RECREATE emission-after-recreate-without-restart = false
PROBE-RECREATE openFds-after                           = 0
```

Re-attachment happens only on the next `start()` or poll tick, and polling is only
active while `busyExternally` — so a watched directory deleted and recreated while
the app is idle stays unwatched indefinitely. Per the brief's own wording
("retried on the next `start()`/poll") this is by design, but nothing tests it and
nothing re-arms it in the idle case.

### M4 (Minor) — `testMissingDirectoryIsRetriedOnLaterStart` does not test what it is named

The `start-once-only` mutant (make `start()` a no-op whenever any watch already
exists) **survives**, because that test's repo has *zero* watched subdirectories
at the first `start()`. The test therefore never demonstrates the documented
contract "existing sources are retained while paths that were absent during an
earlier call are retried" (RepoWatcher.swift:61-63). Fix: create `recipes/` before
the first `start()`, then create `previews/` and re-`start()`.

### M5 (Minor) — housekeeping

`testCoalescedChangeEmission` is the only test that never removes its temp repo
(the other three have `defer { try? FileManager.default.removeItem(...) }`), so
each run leaks a directory tree under `TMPDIR`. The report also acknowledges
leaving the brief's `Void?` inference warnings in place.

### M6 (Minor) — `start()` racing `stop()` off the MainActor can leave live sources

`stop()` snapshots and clears `watches` under the lock, then cancels outside it; a
concurrent `start()` re-populates the dictionary and can leave sources and fds
alive after `stop()` has returned. The *poll* retry path is guarded
(`startWatching` bails when `pollingTask == nil` or the generation moved) — the
plain `start()` path is not. Not reachable from a MainActor-only Task 7 wiring;
worth a `// call start()/stop() from one actor` note or an `isStopping` flag.

---

## What I verified that turned out to be FINE

- **(b) The `stopPolling()` race is not real.** The poll loop sleeps *after*
  emitting, so the next tick is always a full interval after `second` is
  delivered. I measured the actual exposure — from `second` being delivered to
  `stopPolling()` returning — at **mean 5 µs, max 65 µs against a ~37 ms budget,
  with 0 violations in 80 runs, taken while the machine was at load average
  ~280**. I also swept the interval down (40/8/2/1 ms, 40 runs each: 0/160
  violations) and separately ran the shipped test 40× under 16 spinning cores
  (0 failures). The assertion is *not* vacuous either: injecting a 60 ms stall
  before `stopPolling()` breaks it 10/10, so it does detect a watcher that keeps
  emitting.
- **(c) fd recycling cannot make the assertion lie.** 200 repetitions of the
  shipped `fcntl(F_GETFD)/EBADF` check in a quiet process: 0 spurious. 200 more
  with a background thread continuously `open()`/`close()`ing a file to churn the
  descriptor table: 0 spurious. And the assertion genuinely discriminates —
  dropping `Darwin.close(descriptor)`, dropping `source.cancel()`, *or* dropping
  the `closed.wait()` loop each turns it red, so the semaphore handshake is
  load-bearing rather than decorative.
- **(d) The `nonisolated(unsafe) var iterator` opt-out is safe here, and the
  toolchain claim is true.** Reverting all 8 declarations to the brief's verbatim
  `var iterator` reproduces exactly the two errors the report cites
  (`capture of 'iterator' with non-Sendable type 'AsyncStream<Void>.Iterator' in a
  '@Sendable' closure`, `mutation of captured var 'iterator' in
  concurrently-executing code`) on Swift 6.2.4. Accesses never overlap because
  `withTaskGroup` joins the cancelled child before returning, and no shipped test
  reads an iterator after a timed-out read — so the tests are not corrupted by
  the cancellation semantics (the *production* consequence is C1). TSan on an
  isolated RepoWatcher package: 4 tests, 0 failures, **zero** warnings.
- **(e) No reachable deadlock in the shipped code.** Every closure the private
  queue can run captures `[weak self]`; 4500 randomised
  release-during-storm iterations produced no hang; `stop()` blocks its caller for
  **0.48 ms worst case** even while a 4000-file storm is in flight across all 11
  directories, so calling it from the MainActor is not a priority-inversion
  problem in practice. The structural hazard is I3.
- **(f) All 11 directories work.** The list in `RepoWatcher.swift:5-17` matches
  the brief's enumeration exactly, and a new file in each of the eleven —
  including the seven the shipped tests skip — produces an emission
  (`PROBE-F new-file-no-emission: []`). `run/driver.lock`
  (`publish.py:48-53`) is a direct child of `run/`, so lock acquire/release both
  fire; `Input/` is flat (`ingest.py` uses `iterdir()` and
  `input_dir() / source.name`), so non-recursive watching is correct there.
- **`@unchecked Sendable` is honest.** Every mutable field (`watches`,
  `pendingChange`, `coalesceGeneration`, `pendingCoalesce`, `pollingGeneration`,
  `pollingTask`, and `DirectoryWatch.isCancelling`) is read and written only under
  `lock`; the rest are `let`. `RepoWatcher` never installs an
  `onTermination` handler, so there is no lock inversion against `AsyncStream`'s
  internal lock today (this is the thing to be careful about when fixing C1).
- **Scope claim holds.** `git diff --name-status 3212f6c b3fcf2a` shows exactly
  the two intended added files; `git status --porcelain` is empty at b3fcf2a; no
  AppModel/Contract/PipelineClient/Debouncer/CropMath/`Package.swift`/project
  file/Python/fixture was touched; `withTimeout` collides with no other symbol in
  the test target.
- **The refresh gate was verified, not rebuilt, and it is correct.**
  `AppModel.refresh()` (AppModel.swift:222-233) is unchanged since Task 5:
  `isRefreshing` blocks re-entry, `pendingRefresh` records one trailing request,
  and the `repeat … while pendingRefresh` loop runs exactly one follow-up per
  arriving change. That is spec §7's watcher-storm rule verbatim ("a `status` call
  already in flight suppresses re-entry; at most one trailing refresh queues").
  Its test (`testConcurrentRefreshesCollapseToOneActiveAndOneTrailing`, 5 rapid
  refreshes → `callCount == 2`, `maxConcurrent == 1`) is present and unmodified;
  no second gate and no duplicate test were added.
- **Gates, re-run by me.** `xcodebuild -project RAWdogPrintworks.xcodeproj
  -scheme RAWdogPrintworks -destination 'platform=macOS,arch=arm64' build`
  → `** BUILD SUCCEEDED **`. `.venv/bin/python -m pytest tests/ -q` →
  `295 passed, 1 skipped in 28.55s`. `swift test` → 48/50 runs green (see I5).

---

## What I could not determine

- Whether the controller's original "20/20 consecutive green" measurement used a
  reliable oracle. I can only say the claim does not reproduce at 50 runs, and
  that the obvious grep for it (`Executed N tests, with 0 failures`, first match)
  silently reports a false green because it matches the first *suite*, not the
  run — I hit that exact trap myself on my first attempt.
- The real-world probability of the I3 `deinit`-on-queue deadlock. It is
  structurally reachable and I proved the hang, but 4500 randomised attempts did
  not hit the microsecond-wide reference-release window, so I cannot put a number
  on it. Fix it because it is three lines, not because I measured it.
- Whether Task 7 will consume `changes` in a cancellable `.task {}` (which
  triggers C1) or a lifetime-scoped `Task` (which does not). C1 is a defect either
  way — `stop()` cannot end a consumer, so cancellation is the only shutdown —
  but the blast radius depends on wiring that does not exist yet.
