# Task 5 report — `AppModel`: state tree, drafts, actions

**Commit:** `532c3118aabacdc05f05fbce2268bd7db50add9c` — `feat(app): AppModel — snapshot state, draft lifecycle, approve chain`
**Branch:** `johncioni/plan2-printworks-app` (not pushed, per instructions)
**Files:** 3 changed, 1255 insertions

- Created `app/PrintworksCore/Sources/PrintworksCore/AppModel.swift`
- Created `app/PrintworksCore/Tests/PrintworksCoreTests/AppModelTests.swift`
- Modified `app/PrintworksCore/Sources/PrintworksCore/Contract.swift` (public memberwise inits only — no shape, no key, no type changes)

---

## What I built

### `PipelineRunning` (protocol) + `PipelineClient` conformance

Three verbs, matching the three shapes of pipeline interaction the app has: `status()`,
`crops(stem:)`, `mutate(_:args:onEvent:)`. The conformance extension on `PipelineClient` is
the single place the canonical arg spellings live (`["status", "--json"]`,
`["crops", "--stem", S, "--json"]`), and it routes **every** `mutate` through `runMutating`
— the FIFO queue — so no action on the model can put two mutations on the pipeline at once.
Task 11 passes a real `PipelineClient` straight in, with no adapter type, exactly as its brief
assumes.

The brief's fake compiles verbatim: `func mutate<R>(…) -> CommandResult<R>` picks up
`R: Codable & Sendable & Equatable` by Swift's requirement inference from `CommandResult<R>`,
so the witness matches the constrained protocol requirement without the test writing the
constraints out.

### `ReviewDraft`

Exactly the briefed shape, plus two statics that keep the three check keys spelled once:
`ReviewDraft.checkKeys` (ordered `eyes_open`, `expressions_natural`, `no_blinks_in_crops`) and
`ReviewDraft.emptyChecks`. `startDraft` and `reReview` both build from `emptyChecks`, so
"reset all three to false" can't drift from "create with all three false".

### `AppModel` — the action cycle

Every mutating action is the same four beats, and the shape is the thing Tasks 7/9/10 extend:

```
beginCommand(name, stem:)   → activeCommand/activeStem set, banner cleared, progress generation bumped
send(R.self, args:)         → client.mutate (FIFO), optional streamed progress
apply result, then error    → applyRunResult(...) / rebase(...) BEFORE surface(error)
endCommand()                → activeCommand/activeStem cleared, progress keys dropped, then refresh()
```

`endCommand()` is the only exit path, and its last act is always `refresh()` — so "every
action's exit path, success or failure, ends with `refresh()`" is structural rather than
something each action has to remember. Clearing `activeCommand` *before* the terminal refresh is
what makes that refresh the one that reconciles the stem's draft (see below).

**Result-before-error** is enforced by ordering inside each action: `applyRunResult` (which sets
`lastPublished`) and `rebase` run before `surface(error)`. `refresh()` deliberately does **not**
clear the banner, so a `PARTIAL_FAILURE` banner survives its own terminal refresh; banners are
cleared at the *start* of the next action (or by `dismissBanner()`).

**Error surface (§7):** `surface()` maps code → `BannerAction` (`RENDER_FAILED`/`VERIFY_FAILED`/
`INTERNAL` → `.retry`, `TOOLCHAIN_FAILED` → `.openSettings`, `STALE_REVIEW` → `.reReview`,
everything else → no button), stores `stderrTail` in `bannerDetails` for the Show Details
disclosure, and short-circuits `LOCK_HELD` into `busyExternally = true` with **no banner**, per
spec §7. Each action hands `surface` a closure that re-runs it; `retryBannerAction()` invokes
that closure and only for `.retry` banners. (A stored closure rather than replayed args: replaying
`lastMutatingArgs` alone can't work, because the decode needs the static result type. The args are
still exposed as `lastMutatingArgs` for tests/inspection.)

### The two behaviours flagged as load-bearing

**1. Draft rebase rule.** One shared path, `rebase(stem:before:after:)`, called by both
`applyAdjust` and `rerenderPreview` (whose results carry the same revision pair). It rebases
**iff** `draft.baseRevision == before`; anything else stales the draft. The second half of the
rule — *and the refreshed state equals `after`* — is enforced by `reconcileDrafts` at the terminal
refresh: after a matching rebase `baseRevision == after`, so a refreshed revision that is anything
other than `after` fails the comparison and stales the draft. An external edit hiding behind our
own command therefore cannot survive as a valid draft. Both halves are now tested (they were not
in the brief's test set — see "Tests I added").

A failed `adjust` is deliberately **not** force-staled. The terminal refresh compares the refreshed
revision against the draft, so a failure that moved the sidecar stales the draft and one that
changed nothing leaves it alone. That is disk truth instead of a guess, and it is what spec §6.1's
"any other movement" actually means.

**2. Deferred reconcile (§6.1).** `reconcileDrafts` skips a stem while `activeCommand != nil &&
activeStem == stem`, so watcher refreshes during the command's intermediate states (sidecar
written, preview not yet replaced) can't flap the draft. Because `endCommand` clears
`activeCommand`/`activeStem` before refreshing, the terminal refresh is the one reconcile that
runs. Tested directly.

### Structuring for Tasks 7 / 9 / 10

- **Task 7** (computed helpers only, no behaviour change): `photo(_:)`, `deliveries()`,
  `canApprove(_:)`, `reprocess`/`reprocessAll`, `banner`/`bannerDetails`/`bannerAction`,
  `busyExternally`, `renderProgress`, `selectedStem`/`selectedStyle`/`selectedDeliveryId`,
  and `repo` (for `RepoPaths.resolve`) are all public already. The sidebar/grid read `snapshot`
  and load images off disk — nothing in that path calls the pipeline, so a grid refresh issues
  zero subprocesses.
- **Task 9** adds `resetAdjust` and the cached public `crops(stem:)`. The private
  `approveCropWindows` is the single crops-fetch site today, so Task 9 re-points one call and adds
  its cache without touching approve's logic. `setSlider`/`applyAdjust` already emit only the
  changed control, which is what Task 9's first test asserts.
- **Task 10** adds `pendingInputFiles` and `ingestPending()`. `repo` is stored, `ingest(paths:)`
  is factored so the flag-less variant is a different arg array through the same cycle, and
  `lastPublished` is populated on every run result (including `PARTIAL_FAILURE`) for the publish
  notification.

---

## The unbounded-`run()` question (carried concern from Task 3)

**Answer: the brief's design does not imply per-photo or per-keystroke `run()` fan-out, but it
does leave one real fan-out edge — and I closed it, deliberately and visibly, rather than
shipping it.**

The audit, path by path:

| Path | Unqueued `run()` calls |
|---|---|
| `refresh()` | 1 × `status` |
| `approve` (crops fetch) | ≤ 1 × `crops`, only when the photo has no persisted windows; sequential |
| Every mutating action | 0 — all go through `mutate` → `runMutating` (FIFO) |
| Grid / sidebar rendering (Task 7) | 0 — reads `snapshot`, loads JPGs off disk |
| Slider keystrokes | 0 — coalesced by the per-(stem, style) `Debouncer`, and the resulting `adjust` is a queued mutation |

So nothing scales a `run()` call with the number of photos or with typing. Each action issues at
most one `status` and one `crops`, sequentially awaited.

The edge is `refresh()` itself. It is called by every action's terminal exit **and** (from Task 6
on) by every coalesced watcher burst plus a 5 s poll while the lock is held. Those are independent
callers on the main actor, and `refresh()` suspends at `await client.status()` — so two or more
`status` subprocesses could be alive at once, each holding two `drain` worker threads for its
lifetime. A regeneration storm during an active command is exactly the scenario.

I implemented the gate that Task 6's brief already rules for this ("Refresh gate (AppModel-side,
spec §7 watcher storms)"): at most one `status` in flight, with a single trailing refresh for
anything that arrived meanwhile. Five rapid `refresh()` calls produce exactly two `status`
invocations, which is Task 6's stated expectation, and never two concurrently.

**Two reasons I did it now instead of leaving it to Task 6:**

1. Task 5's own action cycle is the second independent caller, so the fan-out exists the moment
   this task lands, not when Task 6 lands.
2. Without it, the brief's own `testDebouncersAreKeyedPerStemAndStyle` has a latent data race. With
   `.zero` debounce, P1's flush-driven `applyAdjust` and P2's timer-driven one overlap at their
   `await client.status()`, and both then call `FakeClient.status()`, which does
   `statusQueue.removeFirst()` on a plain `Array` from two threads. The gate makes that
   structurally impossible, and the test deterministic.

**What this leaves for Task 6:** the gate's unit test (its brief specifies "5 rapid `refresh()`
calls → exactly 2 client `status()` invocations"). I wrote an equivalent test here
(`testConcurrentRefreshesCollapseToOneActiveAndOneTrailing`, which also asserts max concurrency
is 1); Task 6 can adopt it rather than duplicate it. **Flagging for the reviewer:** this is the
one place I implemented behaviour assigned to a later task's brief. If you'd rather it move, the
gate is six lines at the top of `refresh()` plus two `@ObservationIgnored` flags — but the data
race in Task 5's own test moves with it.

---

## Deviations from the brief, and judgement calls

All deviations are internal; no briefed signature, value, arg spelling, or test changed.

1. **`init(client: any PipelineRunning, …)`** — the brief writes `client: PipelineRunning`. The
   `any` is required spelling for an existential; call sites are identical. (Same class of
   deviation as Task 4's `import CoreGraphics`.)
2. **Public memberwise inits in `Contract.swift`** — the brief instructs adding them for the types
   its tests construct. I added them to *all* public contract structs rather than a subset, so the
   rule is uniform and Tasks 10/11 don't need another edit. Each init's parameter list is identical
   to the implicit memberwise one it replaces (same order, same labels), decoding is untouched,
   and `ContractTests`' 10 golden-fixture tests still pass unchanged.
3. **Progress lifecycle.** The brief defines `renderProgress` but not when entries leave it. Left
   alone, Task 7's toolbar progress bar would never stop showing. `endCommand` removes the keys
   this command wrote, and each command stamps a generation into its `onEvent` handler so a late
   event arriving after the envelope can't resurrect a finished command's bar.
4. **`ingest` chains `run` only when something landed** (`result.ingested` non-empty). Chaining
   unconditionally after e.g. a `LOCK_HELD` ingest just takes the lock again to report the same
   failure twice; a fully-deduped ingest has nothing to render. Banner priority within `ingest`
   is ingest error → run error → skip/conflict notices.
5. **Skip/conflict notices need a code**, since `banner` is a `PipelineErrorInfo`. They get
   `"INGEST_NOTICE"` — not a pipeline code, and it maps to no action button. Legal because `code`
   is a plain `String` by ruling. Say the word if you'd rather these got their own state field
   instead of riding the error banner.
6. **`rerenderPreview(stem:style:)` implemented.** The brief names it as one of the two callers of
   the shared rebase path but doesn't spell its signature. It's `preview --stem S --style Y --json`
   decoded as `AdjustResult` (§4.3 gives preview and adjust the same result schema). Task 9's
   stale-preview chip needs it.
7. **`dismissBanner()`** added — one line, so a banner with no action button isn't stuck until the
   next action.
8. **`deliveries()` ordering:** groups newest-`ingestedAt` first (RFC 3339 UTC sorts
   lexicographically), ties broken by id, `nil` group last as "Earlier". Photo order *inside* a
   group is left as the snapshot's own order rather than invented.
9. **Audit strings are the brief's fixed three + note**, unconditionally `: pass`. That is correct
   only because `canApprove` requires all three checks; `approve(stem:)` itself does not re-check
   them (the brief doesn't ask it to, and views gate on `canApprove`). Worth knowing if a later
   task ever calls `approve` from a path that isn't the Approve button.

---

## Tests I added beyond the brief

The brief's nine cases went in verbatim and pass. Mutation-testing them showed the rebase rule —
the thing that decides whether pixels the user never saw can be approved — was covered only in its
"happy pair" direction, so I added six cases. Each was confirmed to fail under a targeted mutation
of the code it covers (mutation applied, single test run, mutation reverted):

| Test | Mutation it catches |
|---|---|
| `testRebaseStalesDirectlyOnUnmatchedBefore` | `rebase`'s else-branch deleted → **failed** ✅ |
| `testAdjustWithUnmatchedBeforeMarksDraftStale` | (defense-in-depth: reconcile also catches this; kept as the through-`applyAdjust` case) |
| `testRebasedDraftStalesWhenRefreshedStateIsNotAfter` | terminal `refresh()` removed from `endCommand` → **failed** ✅ |
| `testReconcileIsDeferredWhileTheStemsOwnCommandRuns` | §6.1 deferral `continue` removed → **failed** ✅ |
| `testReviewFileLivesOutsideTheRepoIsDeletedAndCarriesNudges` | temp-file `defer` delete removed → **failed** ✅ |
| `testConcurrentRefreshesCollapseToOneActiveAndOneTrailing` | refresh gate removed → **failed** ✅ (2 assertions) |

The review-file test also pins the no-repo-writes constraint (path is under
`FileManager.default.temporaryDirectory`, not under `repo`), that `source` is dropped from crop
windows, and that a draft's `cropNudges` override the persisted windows.

---

## Verification

### 1. `swift test --package-path app/PrintworksCore` (run 4×, all green)

```
$ cd /Users/john/orca/workspaces/rawdog-printworks/plan2-printworks-app
$ swift test --package-path app/PrintworksCore
Test Suite 'AppModelTests' passed at 2026-08-14 02:18:26.229.
	 Executed 15 tests, with 0 failures (0 unexpected) in 0.188 (0.190) seconds
Test Suite 'ContractTests' passed at 2026-08-14 02:18:26.245.
	 Executed 10 tests, with 0 failures (0 unexpected) in 0.014 (0.015) seconds
Test Suite 'CropMathTests' passed at 2026-08-14 02:18:26.245.
	 Executed 2 tests, with 0 failures (0 unexpected) in 0.000 (0.001) seconds
Test Suite 'DebouncerTests' passed at 2026-08-14 02:18:26.401.
	 Executed 2 tests, with 0 failures (0 unexpected) in 0.156 (0.156) seconds
Test Suite 'LineCollectorTests' passed at 2026-08-14 02:18:26.402.
	 Executed 2 tests, with 0 failures (0 unexpected) in 0.000 (0.001) seconds
Test Suite 'PipelineClientTests' passed at 2026-08-14 02:18:28.887.
	 Executed 8 tests, with 0 failures (0 unexpected) in 2.483 (2.485) seconds
Test Suite 'RepoPathsTests' passed at 2026-08-14 02:18:28.888.
	 Executed 1 test, with 0 failures (0 unexpected) in 0.000 (0.000) seconds
Test Suite 'All tests' passed at 2026-08-14 02:18:28.888.
	 Executed 40 tests, with 0 failures (0 unexpected) in 2.841 (2.850) seconds
```

Repeat runs (the concurrency-sensitive cases are the reason for repeating):

```
=== run 1 ===
Test Suite 'All tests' passed at 2026-08-14 02:17:20.305.
	 Executed 40 tests, with 0 failures (0 unexpected) in 2.581 (2.591) seconds
=== run 2 ===
Test Suite 'All tests' passed at 2026-08-14 02:17:23.910.
	 Executed 40 tests, with 0 failures (0 unexpected) in 2.646 (2.664) seconds
=== run 3 ===
Test Suite 'All tests' passed at 2026-08-14 02:17:27.412.
	 Executed 40 tests, with 0 failures (0 unexpected) in 2.544 (2.557) seconds
```

40 = the 25 pre-existing (all still green, none modified) + 15 `AppModelTests` (9 verbatim from
the brief + 6 added). Build is warning-free.

### 2. xcodebuild — app target

```
$ cd app/RAWdogPrintworks && xcodebuild -project RAWdogPrintworks.xcodeproj \
    -scheme RAWdogPrintworks -configuration Debug -destination 'platform=macOS' build
2026-08-14 02:17:40.203 appintentsmetadataprocessor[37494:6462150] warning: Metadata extraction skipped. No AppIntents.framework dependency found.
** BUILD SUCCEEDED **
```

The `appintentsmetadataprocessor` warning is the known benign one recorded since Task 1. No
`project.yml`/`xcodeproj` change was needed — the package target has no explicit source list, so
`AppModel.swift` is picked up automatically.

### 3. Python suite — unchanged

```
$ .venv/bin/python -m pytest tests/ -q
............................................s........................... [ 97%]
........                                                                 [100%]
295 passed, 1 skipped in 21.12s
```

No Python file or fixture was touched (see the file list in §4).

### 4. `git status --porcelain`

Before commit — only the three intended files, no build products:

```
 M app/PrintworksCore/Sources/PrintworksCore/Contract.swift
?? app/PrintworksCore/Sources/PrintworksCore/AppModel.swift
?? app/PrintworksCore/Tests/PrintworksCoreTests/AppModelTests.swift
```

After `git add app/PrintworksCore && git commit`:

```
$ git status --porcelain
(empty)
$ git log -1 --format="%H %s"
532c3118aabacdc05f05fbce2268bd7db50add9c feat(app): AppModel — snapshot state, draft lifecycle, approve chain
```

---

## Concerns for the reviewer

1. **The refresh gate is Task 6's briefed interface, landed here.** Reasoning and the exact escape
   hatch are in the unbounded-`run()` section above. This is the one deliberate cross-task
   decision in the commit and the first thing worth ruling on.
2. **`INGEST_NOTICE` is a synthetic code on the error banner.** Skips and conflicts aren't
   failures, but the brief routes them to `banner`, which is typed `PipelineErrorInfo`. Legal
   (codes are `String` by ruling) but it does mean a non-error rides the error surface.
3. **`approve(stem:)` trusts `canApprove`.** It writes all three audit strings as `: pass`
   unconditionally, per the brief. Any future caller that reaches `approve` without the
   `canApprove` gate would record an audit the user didn't perform. Worth a guard if Task 9 or 11
   ever calls it from a non-button path.
4. **Concurrent actions aren't blocked.** `activeCommand`/`activeStem` are single-valued, so two
   overlapping actions (Approve while Reprocess All runs) clobber them, which would briefly widen
   the §6.1 deferral window to the wrong stem. `PipelineClient`'s FIFO still serializes the actual
   commands, and Task 7's views gate on `activeCommand == nil`. Not briefed as a model-level
   concern; flagging rather than adding un-briefed locking.
5. **`lastPublished` is replaced, not accumulated**, on each run result ("successes from the most
   recent run result"). Task 10 should post its notifications from the value applied during the
   action, not read it later, if it ever needs multiple runs' worth.
6. **`RunResult.failed` entries are not stored.** Spec §7 wants a per-card "render failed" badge;
   the aggregate error reaches the banner, but the per-stem list is dropped after
   `applyRunResult`. Task 7's brief doesn't ask for the badge, so I didn't add un-briefed state —
   whoever writes the badge will need one more field here.

---

# Fix round 1 report — 2026-08-14

## Status

All six findings are implemented and covered by regression tests. The required
Swift stability gate is **25 passed / 0 failed**, and Python is **295 passed / 1
skipped**. The app-target build could not reach compilation in this managed
session: Xcode's local-package resolver attempted a nested `sandbox-exec` and a
write to the read-only user SwiftPM cache. The exact failure and the required
external rerun are recorded below; this report does not claim that gate green.

The controller auto-captured the four Swift files as `7e19bee` while validation
was still running. I did not run `git add` or `git commit`.

## Finding disposition

1. **F1 Critical — fixed.** `AppModel` now tracks each fired slider adjustment
   as an identity-stamped `Task` keyed by `(stem, style)`. A second batch chains
   behind its predecessor. `flushPendingAdjustments(stem:)` unions pending and
   in-flight keys, flushes every style, and awaits already-fired work before
   `approve` re-reads the draft. `testApproveWaitsForDebouncedAdjustAlreadyInFlight`
   blocks an adjust after the debounce has fired and proves the review file uses
   rebased revision `r2`; the keyed test now covers two styles for P1 plus P2.

2. **F2 Important — fixed.** Each status dispatch captures the current
   `commandGeneration` and `activeStem`; reconciliation skips the captured
   stem even if the status lands after `endCommand` clears live flags. The
   rewritten race test starts refresh during `adjust`, ends the command while
   status remains blocked, then lands the captured snapshot before the queued
   terminal refresh.

3. **F3 Important — fixed.** `Debouncer` generation-stamps timers. The
   timer-fired path clears its stored task without cancelling itself; explicit
   flush still invalidates and cancels the sleeper. The generation also stops
   a just-replaced old timer from stealing the new action. The fired-action test
   observes `Task.isCancelled == false`.

4. **F4 Important — fixed.** `surface` suppresses `.retry` whenever no retry
   closure exists. Tests cover both `performRefresh` INTERNAL failure and temp
   review-file write failure; invoking `retryBannerAction()` produces neither a
   second status call nor a mutation. Production still writes review files only
   to `FileManager.default.temporaryDirectory`; an internal-only directory seam
   reaches the write-failure branch in tests.

5. **F5 Important — fixed.** The model now preserves `lastAdvanced`,
   `lastFailures: [String: StemFailure]`, and
   `lastIngestFailures: [String: FileFailure]` alongside `lastPublished`.
   `applyRunResult` remains the single run-result write site. Tests cover an
   `ok: false` PARTIAL_FAILURE result and a per-file ingest failure.

6. **F6 — fixed and stress-verified.** F1's in-flight tracking makes flush
   wait for zero-delay debounce work rather than racing the assertion. The
   discriminating F2/F6 race test was verified RED on pre-fix production and
   GREEN afterward. Twenty-five complete package runs had zero failures.

## F2/F6 required RED -> GREEN evidence

Pre-fix production, after rewriting only the test:

```text
$ swift test --package-path app/PrintworksCore --filter AppModelTests.testReconcileIsDeferredWhileTheStemsOwnCommandRuns
AppModelTests.swift:426: error: ... XCTAssertFalse failed
Test Suite 'Selected tests' failed.
    Executed 1 test, with 1 failure (0 unexpected)
EXIT_CODE=1
```

Post-fix production, identical command:

```text
$ swift test --package-path app/PrintworksCore --filter AppModelTests.testReconcileIsDeferredWhileTheStemsOwnCommandRuns
Test Case '-[PrintworksCoreTests.AppModelTests testReconcileIsDeferredWhileTheStemsOwnCommandRuns]' passed (0.009 seconds).
Test Suite 'Selected tests' passed.
    Executed 1 test, with 0 failures (0 unexpected) in 0.009 (0.023) seconds
EXIT_CODE=0
```

Both directions were therefore verified, with the refresh dispatched during
the command and deliberately released only after `activeCommand` became nil.

## Verification

### Swift package — exact command repeated 25 times

```text
$ swift test --package-path app/PrintworksCore
run=01 PASS | Executed 45 tests, with 0 failures in 2.790 (2.804) seconds
run=02 PASS | Executed 45 tests, with 0 failures in 2.756 (2.767) seconds
run=03 PASS | Executed 45 tests, with 0 failures in 2.804 (2.814) seconds
run=04 PASS | Executed 45 tests, with 0 failures in 2.748 (2.759) seconds
run=05 PASS | Executed 45 tests, with 0 failures in 2.798 (2.807) seconds
run=06 PASS | Executed 45 tests, with 0 failures in 2.758 (2.768) seconds
run=07 PASS | Executed 45 tests, with 0 failures in 2.869 (2.884) seconds
run=08 PASS | Executed 45 tests, with 0 failures in 2.920 (2.933) seconds
run=09 PASS | Executed 45 tests, with 0 failures in 2.885 (2.895) seconds
run=10 PASS | Executed 45 tests, with 0 failures in 2.812 (2.823) seconds
run=11 PASS | Executed 45 tests, with 0 failures in 2.814 (2.825) seconds
run=12 PASS | Executed 45 tests, with 0 failures in 2.737 (2.749) seconds
run=13 PASS | Executed 45 tests, with 0 failures in 2.762 (2.772) seconds
run=14 PASS | Executed 45 tests, with 0 failures in 2.887 (2.900) seconds
run=15 PASS | Executed 45 tests, with 0 failures in 2.762 (2.776) seconds
run=16 PASS | Executed 45 tests, with 0 failures in 2.882 (2.892) seconds
run=17 PASS | Executed 45 tests, with 0 failures in 2.818 (2.833) seconds
run=18 PASS | Executed 45 tests, with 0 failures in 2.819 (2.830) seconds
run=19 PASS | Executed 45 tests, with 0 failures in 2.739 (2.750) seconds
run=20 PASS | Executed 45 tests, with 0 failures in 2.807 (2.822) seconds
run=21 PASS | Executed 45 tests, with 0 failures in 2.923 (2.936) seconds
run=22 PASS | Executed 45 tests, with 0 failures in 2.793 (2.801) seconds
run=23 PASS | Executed 45 tests, with 0 failures in 2.825 (2.835) seconds
run=24 PASS | Executed 45 tests, with 0 failures in 2.842 (2.859) seconds
run=25 PASS | Executed 45 tests, with 0 failures in 2.834 (2.845) seconds
FINAL_TALLY pass=25 fail=0 total=25
```

The command was dispatched individually because wrapping it in a long-lived
shell loop caused the managed runner—not XCTest—to lose its nested sandbox
entitlement. Those manifest-resolution attempts never executed tests and are
excluded from the tally above.

### Xcode app-target build — blocked before compilation

Exact required command:

```text
$ xcodebuild -project app/RAWdogPrintworks/RAWdogPrintworks.xcodeproj -scheme RAWdogPrintworks build
Resolve Package Graph
xcodebuild: error: Could not resolve package dependencies:
  <unknown>:0: error: cannot open file '/Users/john/Library/Caches/org.swift.swiftpm/manifests/ManifestLoading/printworkscore.dia' for diagnostics emission (Operation not permitted)
EXIT_CODE=74
```

Routing package cache and DerivedData to `/tmp` advanced to the underlying
managed-environment failure but still did not compile the target:

```text
xcodebuild: error: Could not resolve package dependencies:
  sandbox-exec: sandbox_apply: Operation not permitted
EXIT_CODE=74
```

No global Xcode preference was changed. Required follow-up from a normal macOS
terminal is the exact command above; expected success evidence is
`** BUILD SUCCEEDED **`.

### Python suite — exact command

```text
$ .venv/bin/python -m pytest tests/ -q
........................................................................ [ 24%]
........................................................................ [ 48%]
........................................................................ [ 72%]
............................................s........................... [ 97%]
........                                                                 [100%]
295 passed, 1 skipped in 19.87s
EXIT_CODE=0
```

### Changed-path audit

Controller-created commit `7e19bee` contains exactly these four Swift files:

```text
app/PrintworksCore/Sources/PrintworksCore/AppModel.swift
app/PrintworksCore/Sources/PrintworksCore/Debouncer.swift
app/PrintworksCore/Tests/PrintworksCoreTests/AppModelTests.swift
app/PrintworksCore/Tests/PrintworksCoreTests/DebouncerTests.swift
```

No Python file and no test fixture changed. This appended report and the
checkpoint `HANDOFF.md` remain controller-owned working-tree documentation.

## Concerns

- The current code has not received a successful app-target `xcodebuild` in
  this managed session. Package tests compile the changed Swift code, but that
  is not a substitute for the required Xcode project build.
- A NaN crop initially used to force JSON serialization failure crashed this
  Foundation build; it was discarded. The final test uses an internal-only
  unwritable review directory, leaving production behavior unchanged.
- No other known concern remains for F1-F6 after 25/25 package runs.
