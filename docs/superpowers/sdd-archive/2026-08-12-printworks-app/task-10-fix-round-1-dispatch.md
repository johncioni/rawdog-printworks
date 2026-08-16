# Task 10 fix round 1 — dispatch

Read `task-10-rereview.md` first; it is the authority. Task 10 SHIPS — these are
the two required follow-ups plus cheap cleanup. One commit, then stop.

## m12 — USER DECISION MADE: do NOT make `runMutating` cancellable

`PipelineClient.swift:35-48`. The finding is correct: `runMutating` wraps work in
an unstructured `Task { }`, so cancelling the caller never reaches `execute`'s
`withTaskCancellationHandler`, and `work.value` (`Failure == Never`) does not
return early either. Every lock-taking command (`ingest`, `run`, `approve`,
`adjust`, `preview`, `render`, `verify`) is therefore uncancellable, while
`testCancellingRunTerminatesTheSubprocess` exercises only the READ path
(`client.run(CropsResult.self, …)`) and implies coverage it does not have.

**The user has decided NOT to make it cancellable now.** Reason: nothing cancels
a mutating command today (every call site is an unstructured `Task` in a SwiftUI
button/menu/drop handler, and the slider path is doubly insulated), so there is
no active bug — while making it cancellable would SIGTERM the whole process
group, RawTherapee and ImageMagick included, mid-write into `staging/<stem>.tmp/`.
That is a deliberate feature decision to take alongside a real Cancel affordance,
not a side effect of propagating a flag.

So do exactly this, and nothing more:
1. **Rename or re-scope the test** so it cannot be read as covering mutations —
   e.g. `testCancellingReadCommandTerminatesTheSubprocess` — and add a sibling
   test asserting the CURRENT, intended behaviour: cancelling a `runMutating`
   caller does **not** terminate the subprocess. A test that pins today's
   behaviour is what stops this being rediscovered as a bug later.
2. **Comment `runMutating`** stating that it is intentionally uncancellable, why
   (FIFO ordering + blast radius mid-render), and what would have to change.
Do NOT rewire the task structure.

## m13 (Minor) — a failed crops fetch never retries

n16's fix removed the revision from the cache key **and** from the guard, so a
fetch that fails is remembered as a permanent negative. Restore the retry path
per the finding, without reintroducing the per-revision refetch n16 removed.

## m14 (Minor, test infrastructure) — the m11 regression test deadlocks

`testCropsStayAtEightAcrossRevisionChurn` fails by **hanging past 8 minutes**
rather than asserting (the fixed code passes in 0.012 s). The controller
confirmed this by mutation. A CI regression here stalls the run instead of going
red. Restructure it to fail fast — bound the wait and assert on the observed peak.

## Cheap nits, fix if genuinely cheap

n17 (`ingestPending` chains `run` unconditionally and drops skip/conflict
notices), n18 (`pendingInputFiles` matches fewer spellings than the pipeline),
n19 (Settings' Cancel does not revert abandoned edits), n20 (Save is not gated on
an idle model), n21 (publish notifications have no body; `lastIngestFailures` is
rendered nowhere). Skip any that turn out to be more than small.

## Gates

```
swift test --disable-sandbox --package-path app/PrintworksCore
xcodebuild -project app/RAWdogPrintworks/RAWdogPrintworks.xcodeproj \
  -scheme RAWdogPrintworks -destination 'platform=macOS' \
  OTHER_SWIFT_FLAGS='$(inherited) -disable-sandbox' build
```

Exit code is the oracle, never a grep (zsh: `$PIPESTATUS[0]` expands to nothing).

## Report + stop

Write `task-10-fix-round-1-report.md` **in this ledger directory**. You cannot
commit — leave the work uncommitted and state the intended commit message. Do not
open the app; the controller owns the smoke. The app points at a scratch repo —
never at `~/Projects/rawdog-printworks`. Do NOT rewrite `HANDOFF.md`.
