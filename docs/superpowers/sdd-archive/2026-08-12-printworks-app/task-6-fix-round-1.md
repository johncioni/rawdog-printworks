# Task 6 — Fix Round 1 report (RECONSTRUCTED)

> **Provenance.** Codex completed this round but its job died at
> `13:00:50Z` on `stream disconnected before completion` with
> `last_agent_message: null` — after the final gate passed, before it could
> write this file. This report was reconstructed by the controller (Opus 5) on
> 2026-08-15 from two primary sources, not from Codex's summary:
> - transcript `~/.codex/sessions/2026/08/14/rollout-2026-08-14T08-34-23-01a00044-2ea0-72d0-a9b2-b70e3f5ec1a2.jsonl`
> - the working-tree diff itself (3 files, +451/−29)
>
> Claims below that originate in Codex's narration are labelled **[claimed]**.
> Claims the controller re-verified independently are labelled **[verified]**.
> Do not treat [claimed] evidence as controller-confirmed.

## Scope

Findings F1–F7 from `task-6-review.md` (C1, I1–I5, plus the four minors).
Two review items were explicitly OUT of scope as deliberate deferrals and were
correctly left untouched: kqueue's invisibility to in-place non-atomic edits,
and `Output/photos/<stem>/` being unwatched. Both remain logged for the
whole-branch review.

## Production changes (`RepoWatcher.swift`, +135)

| Finding | Change |
|---|---|
| **C1** — one cancelled consumer killed the watcher permanently; `stop()` could not end a consumer loop | `changes` went from a single stored `AsyncStream` + one `continuation` to a **computed property**: each consumer gets a fresh stream registered in `continuations: [UInt64: Continuation]` keyed by a monotonic `nextConsumerID`, with `onTermination` removing only that consumer. `stop()` finishes all current continuations. |
| **I3** — `stop()` deadlocked if reached on the watcher's own queue (`deinit` is that path) | `queueKey: DispatchSpecificKey<Void>` set on the source queue; `stop()` detects `onOwnQueue` and skips the wait, letting cancellation handlers drain after return instead of self-deadlocking. |
| **I4** — coalesce had no max-wait, so sustained activity emitted nothing | `maxCoalesceWait = 2.0` plus `firstPendingChangeAt` to cap the debounce. |
| minors | `lifecycleGeneration` + `stopsInFlight` guard a `start()` already in flight from outliving a concurrent `stop()`; vanished-directory discard/retry made explicit. |

**Scope flag for the reviewer:** the production file gained two `#if DEBUG`
test seams — `_startForTesting(afterEntry:)` and
`_runOnPrivateQueueForTesting(_:)`. These are debug-only and were needed to make
the F4/start-stop race deterministic, but they are new test-only API on a
production type and are a legitimate thing for the re-review to accept or
reject.

Only one edit landed outside the two Task 6 files, and it was the one the
dispatch permitted: `AppModelTests.swift` (+8) locks `FakeClient.mutateLog`'s
backing storage (**I5**). Production `AppModel` was not touched.

## Tests added (`RepoWatcherTests.swift`, +337)

| Finding | Test |
|---|---|
| C1 | `testCancellingOneConsumerDoesNotFinishAnother`, `testStopFinishesConsumerAndFreshStreamWorksAfterRestart` |
| I1 coalescing untested | `testBurstIsEmittedExactlyOnceAfterCoalesceDelay` |
| I2 6/11 directories unprotected | `testEveryWatchedDirectoryEmits` |
| I3 | `testStopReturnsWhenCalledFromPrivateQueue` |
| I4 | `testSustainedChangesEmitBeforeActivityStops` |
| minors | `testStartAlreadyInFlightCannotOutliveConcurrentStop`, `testVanishedDirectoryIsDiscardedAndRetriedOnlyWhenRequested` |

## Evidence

**RED baseline before production edits [claimed].** Consumer cancellation killed
later delivery; `stop()` neither ended the loop nor supported restart;
private-queue `stop()` timed out leaving the fd open; sustained writes produced
0 emissions; a paused in-flight `start()` installed watches after `stop()`
returned. TSan was run first to capture the objective I5 baseline.

**Mutation checks [claimed]** — the dispatch required each new test to die when
its behaviour is re-broken, because I1/I2 existed precisely because tests were
written that could not fail. Reported results: exactly 30 emissions for the
no-coalesce mutant; RED for each of the six formerly unprotected directories;
the own-queue timeout reproduced; 0 sustained-activity emissions without the
cap; the original TSan warning with the fixture lock removed; RED lifecycle,
discard and cleanup mutants. All mutations reverted, suite back to 12/12.

**Final repetition gate [claimed]** — 30 runs as separate direct processes,
each checked by process exit code, all `GREEN (exit 0)`. The first attempt was
discarded as an *infrastructure* RED, not a test failure: running the loop
inside one long-lived shell tripped SwiftPM's nested `sandbox-exec`
(`sandbox_apply: Operation not permitted`). That artifact has since been
root-caused and fixed — see memory `codex-swift-sandbox-fix`; Codex can now run
`swift build/test` and `xcodebuild` directly.

**Controller verification [verified], 2026-08-15:**
- `xcodebuild -scheme RAWdogPrintworks -destination 'platform=macOS' build` →
  `** BUILD SUCCEEDED **`
- `swift test` → `Executed 58 tests, with 0 failures`
- under-load gate: see the controller's note appended at commit time.

## Status

All 7 findings addressed. Awaiting the scoped re-review on the fix diff.
