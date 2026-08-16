# Task 6 re-review — fix round 1 (`b3fcf2a..c4a10d1`)

Reviewer: independent re-review (did not write the fix, did not write the
original review). Scope: `c36db76` (Codex's fix) + `c4a10d1` (controller's test
change). Everything asserted below was re-run by me in this worktree or in a
scratch copy of the package; nothing is carried over from
`task-6-fix-round-1.md`, whose mutation and repetition evidence is tagged
`[claimed]` and which I therefore treated as unverified and re-derived from
scratch.

- **SPEC VERDICT: ✅** — C1 and I1–I5 are closed, with one partial (below).
  The watched set, event mask, coalescing, poll fallback and fd hygiene still
  match the brief; `changes` is now genuinely multi-consumer and genuinely
  restartable; `stop()` no longer self-deadlocks on its own queue; sustained
  activity now emits.
- **QUALITY VERDICT: ships.** No Critical, no Important blocker. One partial
  closure (P1) and four new minors (N1–N4, numbered `N` so they do not collide
  with the original review's M1–M6), all cheaper to fix in Task 7's window than
  to hold this task for.
- **The `c4a10d1` adjudication is correct**, and I did not have to take it on
  faith — I reproduced the original failure mode under load and watched the
  emission arrive. See "Adjudicating c4a10d1" below.

---

## Gates, re-run by me (exit code as the oracle, never a grep)

| gate | result |
|---|---|
| `swift build --disable-sandbox --package-path app/PrintworksCore` | **exit 0** |
| `swift test --disable-sandbox --package-path app/PrintworksCore` | **exit 0**, `Executed 58 tests, with 0 failures` |
| `xcodebuild -project app/RAWdogPrintworks/... -scheme RAWdogPrintworks -destination 'platform=macOS' build` | **exit 0**, `** BUILD SUCCEEDED **` |
| Swift compiler warnings across both builds | **0** (the only `warning:` line in the xcodebuild log is `appintentsmetadataprocessor` metadata noise) |
| `swift test --sanitize=thread` (full suite) | **exit 0**, `Executed 58 tests, with 0 failures`, **0** `WARNING: ThreadSanitizer` |
| under-load repetition gate, 15× full suite at load average 290–334 | **15 green / 0 red**, exit code per run |

Idle green being weak evidence for this package, the repetition gate is the one
that matters: 15 consecutive full-suite runs, each a separate process judged by
its own exit code, with 100 spinner processes pinning all 10 cores. Load average
was 192 at the start and 334 at the end — above the 158 at which the flake that
opened this round was seen. Zero red.

The exit code was captured with `cmd; echo $?`, not with `${PIPESTATUS[0]}` —
under zsh that array is `$pipestatus` and the uppercase form silently expands to
nothing, which is one more way to record a green that never happened.

## Mutation gate — re-derived, not inherited

`task-6-fix-round-1.md`'s mutation results are `[claimed]`. I rebuilt the whole
matrix myself against a scratch copy of the package
(`scratchpad/mut/pkg`, driver `scratchpad/mutate.py`), each mutant applied to
the **shipped, unmodified** tests and judged by process exit code.

**21 mutants: 20 killed, 1 survived.**

| finding | mutation | result |
|---|---|---|
| C1 | `cancel-kills-all-consumers` (one termination clears the registry) | **KILLED** — `testCancellingOneConsumerDoesNotFinishAnother` |
| C1 | `stop-does-not-finish-consumers` (drop the `finish()` loop) | **KILLED** — `testStopFinishesConsumerAndFreshStreamWorksAfterRestart` |
| I1 | `no-coalesce` (yield per raw kqueue event) | **KILLED** — `testBurstIsEmittedExactlyOnceAfterCoalesceDelay` |
| I1 | `coalesce-10x` (configured delay × 10) | **SURVIVED** — see P1 |
| I2 | `drop-Input` | **KILLED** — `testEveryWatchedDirectoryEmits` |
| I2 | `drop-config` | **KILLED** — `testEveryWatchedDirectoryEmits` |
| I2 | `drop-config/lab-profiles` | **KILLED** — `testEveryWatchedDirectoryEmits` |
| I2 | `drop-config/rawtherapee-seed` | **KILLED** — `testEveryWatchedDirectoryEmits` |
| I2 | `drop-Output` | **KILLED** — `testEveryWatchedDirectoryEmits` |
| I2 | `drop-run` | **KILLED** — `testEveryWatchedDirectoryEmits`, `testSustainedChangesEmitBeforeActivityStops` |
| I2 | `drop-previews` / `sidecars` / `recipes` / `config/styles` / `Output/photos` | **KILLED** (already were) |
| I3 | `no-own-queue-check` (force `onOwnQueue = false`) | **KILLED** — `testStopReturnsWhenCalledFromPrivateQueue` |
| I4 | `no-maxwait` (`maxCoalesceWait` → 1e6 s) | **KILLED** — `testSustainedChangesEmitBeforeActivityStops` |
| M3 | `no-discard-missing` | **KILLED** — `testVanishedDirectoryIsDiscardedAndRetriedOnlyWhenRequested` |
| M4 | `start-once-only` | **KILLED** — `testMissingDirectoryIsRetriedOnLaterStart` |
| M6 | `no-lifecycle-guards` (drop both `stopsInFlight` and the generation check) | **KILLED** — `testStartAlreadyInFlightCannotOutliveConcurrentStop` |
| I5 | `unlock-mutatelog` (remove `mutateLogLock`), under TSan | **KILLED** — reproduces the original warning verbatim |

I5 is the one finding whose closure is a *negative* claim (no race), so I checked
it in both directions rather than only running the sanitiser once. HEAD under
TSan is clean — 0 warnings across 58 tests. Removing the lock again reproduces
the original review's warning, same access, same frame:

```
WARNING: ThreadSanitizer: Swift access race (pid=94400)
    #0 FakeClient.mutate<A>(_:args:onEvent:) AppModelTests.swift
SUMMARY: ThreadSanitizer: Swift access race AppModelTests.swift in FakeClient.mutate<A>(...)
```

so the three-line fix is load-bearing rather than coincidental.

All six directories the original review measured as unprotected — `Input`,
`config`, `config/lab-profiles`, `config/rawtherapee-seed`, `Output`, `run` —
now die. I2 is closed, and I confirmed it the same way the original review
opened it rather than by reading the new test.

I also checked that nothing was *weakened* to get there: the only lines the fix
round removed from `RepoWatcherTests.swift` are the nine `let x = await
withTimeout(...)` declarations, each replaced by the identical line with an
explicit `: Void?` annotation (which also clears M5's inference warnings). No
assertion was deleted or loosened.

---

## Adjudicating `c4a10d1` (controller-authored — reviewed adversarially)

The claim to test: *in `scheduleCoalescedChange` every change sets
`pendingChange = true` and the newest work item carries the current
`coalesceGeneration`, so `emitCoalesced` cannot be starved permanently — an
emission can only be LATE, never lost.*

**The reasoning is sound.** The invariant it rests on holds, and I checked it
rather than accepting it:

- `coalesceGeneration` is mutated in exactly two places: `scheduleCoalescedChange`
  (RepoWatcher.swift:303) and `stop()` (RepoWatcher.swift:122). Nowhere else.
- `scheduleCoalescedChange` sets `pendingChange = true` (:302) and then, after
  `lock.unlock()` (:314) with **no intervening early return**, submits a work
  item carrying that generation (:316). So `pendingChange == true` always
  implies a live work item at the current generation.
- `stop()` clears `pendingChange` in the *same* critical section in which it
  bumps the generation (:122-123), so the one other generation bump cannot
  strand a pending change.
- `emitCoalesced` (:319) clears `pendingChange` only on the path where it emits.
- `directoryChanged` and every `emitCoalesced` work item both run on the same
  serial `queue`, so `pendingCoalesce?.cancel()` (:305) can never race a work
  item that has already begun executing.

**And I reproduced it, which the commit message says it did not do** — it records
that the flake "needs the full suite's contention, which is why this was settled
by reading the coalescing path rather than by repro." Reading the path is what
makes the claim *believable*; it is not what makes it *true*. So I ran the full
suite 15× at load average ~300 (higher than the 158 the original gate saw) with
an added probe (`scratchpad/probe/.../LateOrLostProbeTests.swift`)
that runs the identical 30-write burst, samples the counter at the *old* test's
350 ms budget, and then keeps watching to 8 s:

```
run 1  burstMs=375 at350=1 firstMs=376 final=1
run 2  burstMs=395 at350=1 firstMs=370 final=1
run 3  burstMs=393 at350=0 firstMs=361 final=1   <- the original failure, then delivery
run 4  burstMs=390 at350=1 firstMs=372 final=1
...
run 15 burstMs=430 at350=1 firstMs=358 final=1
```

Run 3 is the exact reported symptom: the counter is **0** when the old fixed
350 ms wait expires — and the emission then lands 11 ms later. That is LATE, not
LOST, measured rather than argued. `final` is 1 in every one of the 15 runs;
nothing was ever dropped. Across all runs the emission arrived at 350–376 ms
after `lastWrite` against a 200 ms configured coalesce — a ~170 ms scheduling
slip sitting right on top of the old test's 150 ms margin. A 1-in-25 failure
rate is exactly what that distribution predicts, and 1-in-15 is what I got.

**Two corrections to how the claim is stated**, neither of which changes the
verdict:

1. *"bounded by `maxCoalesceWait` (2 s)"* is not the real bound.
   `maxCoalesceWait` bounds the **scheduled deadline**, not delivery. The queue
   is `qos: .utility` (RepoWatcher.swift:35-36) and the consumer's actor hop is
   on the cooperative pool; both slip without bound under load. The honest
   statement is "never lost; late by an amount the class does not bound." That
   matters because the replacement test's 5 s poll ceiling is still a fixed
   bound on an unbounded quantity — just one with ~13× the headroom of the
   350 ms it replaced, which is why it holds at load 300.
2. *"never lost"* is true of the **scheduling** machinery, but there is one real
   drop path it does not cover — see N2 below. It cannot affect the failing
   test (that test registers its consumer synchronously at
   `let changes = watcher.changes`, before `start()`), so the adjudication
   stands.

**The test change itself is sound and non-vacuous.** Splitting ABSENCE (fixed
wait — the only way to assert something did *not* happen) from ARRIVAL (poll to
a ceiling) is the right call, and the added settle assert is a genuine
strengthening: my `no-coalesce` mutant is killed by this test.

I looked for the obvious way this fix could go wrong. I4's own fix means the
watcher is now *required* to emit mid-burst if the burst outlives
`maxCoalesceWait`, which would make "exactly one emission" contradict the
product contract — so the new test has a second, unstated load bound: the burst's
own wall clock must stay under 2 s, and it is 30 × `Task.sleep(10ms)`, i.e. set
by the machine and not by the test. It does not materialise: `burstMs` stayed in
370–449 ms across all 15 runs at load 300, ~4.5× of headroom, because
`Task.sleep` on the cooperative pool is far less starved than the `.utility`
dispatch queue that carries the emission. Recorded as a latent property of the
test rather than a finding — but it is the bound to check first if this test ever
flakes again, and it would present as `2` where `1` is expected, not `0`.

---

## Findings

### P1 (Partial closure of I1) — the coalesce *window* is still unpinned; `coalesce-10x` survives

**File.** `app/PrintworksCore/Tests/PrintworksCoreTests/RepoWatcherTests.swift:98-122`

**What is wrong.** I1's evidence named two surviving mutants, not one:
`no-coalesce` **and** `coalesce-10x` ("500 ms default becomes 5 s, violating
spec §6's stated 500 ms"). The new test kills the first. It does not kill the
second, and I confirmed that independently:

```
coalesce-10x   exit=0   SURVIVED   23.6s
```

The ABSENCE assert (50 ms against a 200 ms configured coalesce) catches a
zero-delay implementation, which is what the review's concrete fix asked for.
Nothing catches inflation: the ARRIVAL poll now runs to a 5 s ceiling, and a
10× window still lands inside it (capped by `maxCoalesceWait` at ~1.6 s after
the last write).

**Failure scenario.** Someone changes `coalesceDelay` — a units slip in
`Self.seconds`, a "let's debounce a bit harder" tweak, a changed default in
`init(repo:coalesce:)` — from 500 ms to 5 s. All 58 tests stay green. Every
`config/styles/*.pp3` edit, every `recipes/` write, every lock acquire in `run/`
now takes 5 s to reach the UI instead of the 500 ms spec §6 states. Since spec
§6 item 5 makes this stream the app's only refresh path, that is the app's
entire perceived responsiveness, silently 10× worse.

**Concrete fix (load-free, so it cannot flake).** Do not try to pin the window
with another wall-clock assertion — the whole point of `c4a10d1` is that
wall-clock upper bounds are what break under load. Pin the *configuration*
instead: expose the computed delay to `@testable` (`var effectiveCoalesceDelay:
Double { coalesceDelay }`, alongside the existing `openFileDescriptors` seam)
and assert `RepoWatcher(repo:).effectiveCoalesceDelay == 0.5` and that an
injected `.milliseconds(200)` arrives as `0.2`. Three lines, no timing, kills
`coalesce-10x` and every units-slip mutant with it.

### N1 (Minor) — `start()` silently no-ops while a `stop()` is in flight, and a wedged `stop()` makes that permanent

**File.** `app/PrintworksCore/Sources/PrintworksCore/RepoWatcher.swift:87-91`,
`:116-155`, `:211-214`

**What is wrong.** New in `c36db76`. `stopsInFlight` is incremented inside
`stop()`'s first critical section and decremented only in its **last** statement
(:152-154), after the unbounded `watch.closed.wait()` loop (:144-148). While it
is non-zero, both `start()` (:88) and every `startWatching()` (:211) return
having installed nothing — no error, no `false`, no retry.

The review's I3 fix suggestion had two halves; the implementer took the
`DispatchSpecificKey` half (correctly — it is what closes I3) and left the
optional half: *"Optionally bound the wait (`.wait(timeout: .now() + 2)`) so a
future regression degrades instead of hanging."* Combining the unbounded wait
with the new flag is what raises this above bookkeeping.

**Failure scenario.** A future change adds work to the private queue that blocks
(a synchronous filesystem call in an event handler, a `yield` into a consumer
that back-pressures). An off-queue `stop()` now parks in `closed.wait()`
forever. Before this commit that hung exactly one caller. Now `stopsInFlight`
stays ≥ 1 for the lifetime of the process, so every subsequent `start()` from
every thread is a silent no-op and the watcher can never be revived — the same
"app goes blind with no error and no banner" outcome C1 was raised for, reached
by a different route.

**Not reachable today**: under the intended MainActor-only Task 7 wiring,
`start()` and `stop()` are serialised, so `stopsInFlight` is always 0 when
`start()` runs; and the original review measured `stop()`'s worst case at
0.48 ms with a 4000-file storm in flight. Both `start()` and `stop()` are
`public` and the type documents a restartable lifecycle, so this is a real
hardening gap, not a live defect.

**Concrete fix.** `watch.closed.wait(timeout: .now() + 2)` as the review
suggested, plus a `// call start()/stop() from a single actor` note on the type.

### N2 (Minor) — a coalesced change is silently dropped when no consumer is registered

**File.** `app/PrintworksCore/Sources/PrintworksCore/RepoWatcher.swift:319-333`

**What is wrong.** `emitCoalesced` clears `pendingChange` and
`firstPendingChangeAt` under the lock, then yields to the snapshot it took. If
that snapshot is **empty** the guard still succeeds (`[]` is not `nil`), so the
pending change is consumed and delivered to nobody. There is no "missed change"
latch: the next consumer to attach starts from a clean slate.

This is the one genuine hole in `c4a10d1`'s "never lost" phrasing. It cannot
affect the test that prompted that commit — it registers its consumer
synchronously via `let changes = watcher.changes` (RepoWatcherTests.swift:84)
before `watcher.start()` (:90).

**Evidence** (`scratchpad/probe/.../DropWithNoConsumerProbeTests.swift`): start
the watcher, write one file, wait 600 ms (6× the 100 ms coalesce) with nothing
consuming, *then* attach:

```
PROBE-N2 late-consumer-sees-earlier-change = false
PROBE-N2 next-change-still-delivered      = true   <- control: watcher is live
```

The change is gone, and the watcher is demonstrably still healthy — so this is a
dropped event, not a dead watcher.

**Failure scenario.** Task 7 wires this the natural SwiftUI way:

```swift
watcher.start()                       // sources live from here
...
.task { for await _ in watcher.changes { await model.refresh() } }   // registers later
```

Any filesystem change landing between `start()` and the first `changes` access
is coalesced, emitted into an empty registry, and forgotten. Same for the window
after `stop()` (which clears `continuations`, :135) and before the consumer
re-attaches. With no refresh button (spec §6 item 5) the UI stays stale until
the *next* unrelated change. The window is small but it is exactly app-launch
and app-resume, when the repo is most likely to have changed underneath.

**Concrete fix.** Either keep `pendingChange` set when the snapshot is empty
(so the next real event re-delivers), or have `changes` yield one priming `()`
to a newly registered consumer. Cheapest of all: document that `start()` must
be called *after* the consumer is established, and have Task 7 do that.

### N3 (Minor) — `changes`'s contract is undocumented, and it is exactly the contract C1 was about

**File.** `app/PrintworksCore/Sources/PrintworksCore/RepoWatcher.swift:52-67`

`changes` went from `public let` to a computed property with a **registration
side effect**, and carries no doc comment. Three non-obvious properties a Task 7
author has to infer from the implementation:

- each access vends an *independent* stream and permanently registers a
  continuation (so calling it inside a SwiftUI `body` accumulates registrations
  until each stream is deallocated);
- cancelling one consumer now ends only that consumer (the C1 fix), but
- `stop()` finishes **all** outstanding streams (:149-151), so a stored
  `let changes = watcher.changes` is dead after a `stop()`/`start()` cycle and
  must be re-read — a stop/start no longer restarts an existing consumer;
- and cancelling a read still permanently finishes *that* stream (unchanged
  `AsyncStream` semantics — C1's fix scoped the blast radius to one consumer, it
  did not remove the mechanism), so any consumer that times out a read must
  re-read `changes` too.

That last one is not theoretical: I tripped it in my own N2 probe. The first
version reused its iterator after a deliberately timed-out read and the control
assertion went red, which reads exactly like "the watcher is dead" — the same
symptom C1 described, now correctly scoped to one consumer. The shipped tests get
this right (`testVanishedDirectoryIsDiscardedAndRetriedOnlyWhenRequested`
allocates a fresh iterator after each expected-nil, RepoWatcherTests.swift:416,
:427), but they get it right silently.

Given that this task's Critical was a stream-lifetime trap, the replacement
lifetime rules deserve four lines of `///` rather than a re-read of the file.

### N4 (Minor) — I5's fix locks `mutateLog` but leaves the rest of `FakeClient` racy

**File.** `app/PrintworksCore/Tests/PrintworksCoreTests/AppModelTests.swift:9-10`, `:17-20`

`storedMutateLog` is now behind `mutateLogLock`, which is the right fix and is
the one TSan flagged. But `statusQueue` and `statusCalls` are still bare `var`s
on the same `@unchecked Sendable` class, mutated from `nonisolated func status()`
(`statusCalls += 1`, `statusQueue.removeFirst()`), which runs off the MainActor.

Not live today: `AppModel.refresh()`'s gate (AppModel.swift:222-233) keeps at
most one `status` in flight, so the calls are serialised in practice. Task 7 adds
a watcher-driven refresh loop on top of that gate; if it ever grows a second
call site, this is the same failure I5 documented (a lost/mis-ordered entry under
load) in a fixture whose neighbour has just been fixed. Two more `withLock`s.

---

## The two `#if DEBUG` seams — **ACCEPT**

`_startForTesting(afterEntry:)` and `_runOnPrivateQueueForTesting(_:)`
(RepoWatcher.swift:100-110). This needed an explicit call, so here it is, with
the reasoning rather than a rubber stamp.

**Accept, on four grounds.**

1. **They are not API.** Both are `internal`, inside `#if DEBUG`. They add
   nothing to the module's public surface and nothing at all to a Release build.
   `changes`, `start`, `stop`, `startPolling`, `stopPolling` remain the whole
   public contract.
2. **The production cost is one optional call.** `start()` is now
   `start(afterEntry: nil)`; the seam is a single `afterEntry?()` at :93. There
   is no branch on a test flag, no injected protocol, no stored hook — the
   shipping path is unconditional.
3. **They buy determinism for two hazards that were otherwise unreachable.**
   The original review proved the I3 deadlock only by adding this same hook to a
   scratch copy, and separately failed to reach it from unmodified code in 4500
   randomised iterations — a microsecond-wide reference-release window is not
   something a test suite can wait for. Without `_runOnPrivateQueueForTesting`,
   I3's regression test does not exist; with it, my `no-own-queue-check` mutant
   dies in 14 s. Same for `_startForTesting` and the original review's M6 start/stop race
   (`no-lifecycle-guards`, killed). Two of the review's findings are now
   permanently guarded because these seams exist.
4. **The precedent is already in the file and was already accepted.**
   `openFileDescriptors` (:192-196) is an internal `@testable` seam on this same
   type, added in `b3fcf2a` with a comment explaining why, and the original
   review not only accepted it but leaned on it (it is what makes the fd-closure
   assertion checkable at the OS boundary).

**One caveat worth recording rather than blocking on.** `swift test -c release`
will not compile the test target, because `_startForTesting` and
`_runOnPrivateQueueForTesting` vanish. That is fine as long as nobody adds a
release-configuration test gate later; if that ever happens, drop the `#if DEBUG`
and rely on `internal` + `@testable` alone, which is the same trade
`openFileDescriptors` already makes.

---

## Out of scope, not re-litigated

Per the dispatch: kqueue's invisibility to in-place non-atomic edits (M1 of the
original review); `Output/photos/<stem>/` unwatched (M2); the refresh gate living
in Task 5; `expected_review_revision` / `_state_stamps()`. All still logged for
the whole-branch review. I confirmed only that the fix round did not touch them.

## What I did not verify

- **`task-6-fix-round-1.md`'s "RED baseline before production edits" `[claimed]`
  line.** It describes the state of Codex's working tree at a moment that no
  longer exists; there is no artefact to re-run. Every *other* `[claimed]` line
  in that report — the mutation matrix, the repetition gate — I re-derived from
  scratch above rather than confirm, and my results agree with it.
- The real-world probability of the I3 `deinit`-on-queue deadlock. The original
  review could not put a number on it either; the fix is three lines and is now
  mutation-guarded, which is the right reason to have taken it.

---

## Verdict

**Task 6 ships.** The Critical is closed and mutation-guarded on both of its
halves; I1–I5 are closed with I1 partial (P1); the four minors from the original
review are closed and each is guarded by a mutant that dies. 58/58 green, both
builds clean, zero compiler warnings, TSan clean, and 15/15 consecutive full
suites green at load average 290–334 — twice the load at which the flake that
opened this round appeared.

The one thing I would not have accepted on the strength of the reasoning alone
is `c4a10d1`'s adjudication, because getting it wrong means shipping a live
product bug under a test that was quietly loosened to hide it. It holds: the
invariant is real, and I reproduced the failure and watched the emission arrive
anyway.

P1 and N1–N4 are all small, none of them blocks Task 7, and N2/N3 are most
naturally fixed *with* Task 7's wiring since that is where they bite. Recommend
carrying them into Task 7's brief rather than opening a fix round 2.
