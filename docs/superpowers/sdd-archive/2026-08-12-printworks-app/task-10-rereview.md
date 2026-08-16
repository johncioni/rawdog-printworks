# Task 10 re-review — ingest banner, Settings, notifications

Reviewer: Opus 5 xhigh. Scope `e9a16e7..de1e774` (two commits: `5784003`, the
already-reviewed Task 9 fix round, and `de1e774`, the new work). Findings below
are all against `de1e774` unless stated.

## Verdict

**Task 10 ships.** The headline deliverables are correct, the m11 fix is real on
the path it covers, and the failure mode the dispatch was most worried about —
a cancelled mutating subprocess orphaned against a real repo while holding the
driver lock — **is not reachable in this build**, for three independent reasons
(§1.3). Two follow-ups are required before the next task: **m12** (the
cancellation fix covers only half the client, and the half it misses is the
mutating half) and **m13** (n16's fix went one step too far and left a crop
fetch that never retries).

## Controller verification re-confirmed

- `swift test --disable-sandbox --package-path app/PrintworksCore` → exit 0,
  **80 tests**, working tree clean afterwards (my probe file removed).

---

## 1. Priority: subprocess cancellation (dispatch focus #2)

The implementer added `testCancellingRunTerminatesTheSubprocess`
(`PipelineClientTests.swift:135-161`) beyond the brief. The dispatch read that
correctly: cancelling a Swift `Task` was **not** killing the python subprocess,
and `ProcessCancellation` (`PipelineClient.swift:207-236`) is a new fix, not a
tidy-up. I verified the fix by probe rather than by reading, using a temporary
`ZZProbeTests.swift` (four spawn/cancel/reap scenarios against shell stubs that
`trap TERM`), since deleted.

### 1.1 The read path is genuinely fixed — and better than the test claims

`PipelineClient.run` (`:28-33`) awaits `execute` directly, so it is inside the
caller's task tree and `withTaskCancellationHandler` (`:56-61`) fires. Verified:

| Probe | Result |
|---|---|
| Cancel `run` mid-flight → stub's `TERM` trap fires before release | **PASS** |
| Child reaped after cancellation (`ps -o stat=`) | **PASS** — process gone, not `Z` |
| Exec'd **grandchild** (`/bin/sleep 30 &`, models python → RawTherapee) | **PASS** — grandchild dead too |
| Child's process group | `pid=29302 pgid=29302` vs runner `pgid=29301` |

The grandchild result is the interesting one, and it is not luck: Foundation
puts the child in **its own process group** (probe 5 above), and Darwin's
`Process.terminate()` is documented to signal "the receiver and all of its
subtasks". So on the read path, cancellation tears down the entire subprocess
tree without any risk of signalling the app itself, and Foundation reaps it.
No zombies, no orphans. `PipelineClient.crops` and `.status` both route through
`run`, so **every read spawn path is covered**.

`ProcessCancellation` also correctly closes the cancel-arrives-before-`run()`
race: `cancel()` and `didStart()` (`:217-235`) both read-and-set under one lock
and whichever runs second performs the terminate. I could not construct an
ordering that loses the signal.

### 1.2 m12 — `runMutating` cancellation is a silent no-op (CONFIRMED)

`PipelineClient.swift:35-48`

```swift
let work = Task { () -> CommandResult<R> in      // <- NEW top-level task
    await prior.value
    return await self.execute(resultType, args: args, onEvent: onEvent)
}
tail = Task { _ = await work.value }
return await work.value                          // <- Failure == Never
```

`Task { }` is **unstructured**: cancelling the task that called `runMutating`
does not cancel `work`, so `execute`'s `withTaskCancellationHandler` never sees
cancellation and the process is never terminated. And because `work.value` has
`Failure == Never`, awaiting it does not return early on cancellation either —
the caller blocks for the subprocess's entire remaining lifetime.

Measured, both directions:

- **Probe 1** — cancel `runMutating` against a stub trapping `TERM`: the trap
  **never fires**. `XCTAssertTrue(terminatedBeforeRelease)` fails.
- **Probe 2** — cancel `runMutating` against a stub that ignores `TERM` and
  sleeps 2 s: the cancelled call returns after **2.005 s**, not promptly.

`mutate` is the only door to a mutating command (`AppModel.swift:36-41`), and it
routes through `runMutating`. So `ingest`, `run`, `approve`, `adjust`, `preview`,
`render`, `verify` — every command that takes the driver lock — are exactly the
ones the fix does not cover. The added test uses `client.run(CropsResult.self,
…)`, so it pins the half that already worked and leaves the half that matters
untested.

**Failure scenario (latent, not live).** The next person adds a Cancel button to
the busy pill, or moves an action to `.task { await model.approve(stem:) }`, sees
a green test named `testCancellingRunTerminatesTheSubprocess`, and ships. The
button does nothing: python keeps rendering, the UI stays wedged awaiting a
result it asked to abandon, and there is no signal anywhere that cancellation
was dropped.

**Fix.** Propagate, and pin the decision with a test either way:

```swift
tail = Task { _ = await work.value }
return await withTaskCancellationHandler {
    await work.value
} onCancel: {
    work.cancel()
}
```

`ProcessCancellation` then handles the queued-but-not-yet-started case correctly
already (it launches, then immediately terminates); an early `Task.isCancelled`
check before `execute` would skip even that launch. If instead the deliberate
choice is that mutations are **not** cancellable, that is defensible — say so in
the doc comment and add a test asserting the no-op, so the next person cannot
mistake silence for coverage.

### 1.3 Can a cancelled `crops`/`run` leave an orphan holding the driver lock?

**No — and three independent things have to change before it can.**

1. **`crops` never takes the lock.** `pipeline/__main__.py:35-39` registers it
   `mutating=False` with an explicit comment ("Read-only … it must not contend
   for the driver lock"). So the one command the app *does* cancel
   (`AppModel.swift:350`, m11's churn branch) cannot strand a lock at all.
2. **No mutating command is ever cancelled today.** I checked every call site:
   `IngestBanner:14`, `ErrorBanner:60`, `InspectorView:116`/`:182`,
   `MainWindow:51`/`:81`/`:86`, `GridView:78`, `ReviewView:127` are all
   unstructured `Task { }` in button/menu/drop handlers, which SwiftUI never
   cancels. The slider path is doubly insulated: `Debouncer.schedule` cancels
   only the sleep task (`Debouncer.swift:19`), and `firePendingAdjust` runs
   `applyAdjust` inside its own `Task` (`AppModel.swift:590-596`) before awaiting
   a `Never`-failure value. Cancellation cannot reach `runMutating` from anywhere.
3. **Even a SIGTERM'd python self-heals.** The lock file stores the PID
   (`publish.py:48-77`) and `_lock_is_stale` (`:19-31`) tests it with
   `os.kill(pid, 0)`; a dead PID makes the lock stale, and `acquire_lock` unlinks
   and proceeds. So the `finally: lock.unlink()` that SIGTERM skips is not
   load-bearing.

The one thing worth carrying into m12's fix: if `runMutating` becomes
cancellable, a cancelled `run` will kill the **whole process group**, RawTherapee
and ImageMagick included, mid-write into `staging/<stem>.tmp/`. That is what
startup recovery is for, but it is a step up in blast radius from the read path
and should be a deliberate decision, not a side effect of propagating a flag.

---

## 2. m11's test fails by hanging (dispatch focus #1)

`AppModelTests.swift:683-729`. **It should be restructured. The hang is not
inherent to asserting peak concurrency — it is a property of this test's release
protocol.**

The stub holds every `crops` call open until *either* it is cancelled *or*
`shouldFinish` is set (`:701-703`), and `shouldFinish` is only set at `:723`,
after all four waves have started. With the fix in place, wave N+1 makes progress
solely because `pending.task.cancel()` (`AppModel.swift:350`) releases the wave-N
stub. Remove that line and `_ = await pending.task.value` (`:351`) waits on a
task nothing will ever finish → `waveStarted[1]` never opens → `await
waveStarted[wave].wait()` (`:718`) blocks forever. So "the implementation makes
progress" and "peak stays at 8" are collapsed into one signal, and losing the
first deadlocks instead of failing the second.

That is worse than it looks: **any** future regression that stalls `crops` —
not just the m11 line — hangs the whole suite rather than failing it. `AsyncGate`
(`:124-141`) has no timeout, and there is no suite-level time limit configured.

**Concrete restructure** — bound the wait and always release the stubs:

```swift
let waveStarted = (0..<4).map { _ in XCTestExpectation(description: "wave") }
defer { stateLock.withLock { shouldFinish = true } }   // FIRST statement
…
await fulfillment(of: [waveStarted[wave]], timeout: 5)
```

`XCTestExpectation` + `fulfillment(of:timeout:)` turns an 8-minute stall into a
5-second failure naming the wave that never started, and the `defer` matters
independently: without it a timed-out run leaves eight unstructured `Task`s
parked in the fake forever, leaking into whatever test runs next. Keep the
`observedPeak == 8` assertion exactly as it is — it is the right assertion, and
it survives the change unmodified.

---

## 3. Settings (dispatch focus #3)

Correct on all four points the dispatch named.

- **Tilde expansion.** Every construction site expands first:
  `PrintworksApp.swift:77-79` (default), `:129-136` (`repoURL`/`pathURL`, used by
  both `save` and `makeModel`), and `SettingsSheet.swift:88-96` for the throwaway
  validation client, with a comment explaining why. I found no
  `URL(fileURLWithPath:)` on an unexpanded path.
- **600 ms debounce.** `SettingsSheet.swift:82` inside `.task(id: candidate)`
  (`:56`). The debounce is real because `.task(id:)` cancels the in-flight
  validation when either field changes; the `catch { return }` on the sleep
  handles that cleanly.
- **Save gated on the *current* pair.** `.disabled(validatedCandidate !=
  candidate)` (`:51`), with `validatedCandidate = nil` set at the top of
  `validate` (`:80`) and re-checked against `self.candidate` after the probe
  returns (`:100`). Both orderings (keystroke-then-task, task-then-keystroke)
  leave Save disabled. `Candidate` compares the raw entered strings, so `~/foo`
  and its expansion validate independently — consistent, not a bug.
- **Save rebuilds both client and watcher.** `AppRuntime.save` (`:96-110`) stops
  the old watcher, builds a **new** `PipelineClient` inside a new `AppModel`
  (`:119-127`), builds a new `RepoWatcher`, and bumps `configurationRevision`,
  which re-fires `.task(id: runtime.configurationRevision)` (`:14`) and calls
  `watcher.start()`. Critically, `observeRepo` takes `model`/`watcher` as
  captured parameters (`:15-17`) rather than reading `runtime.*` later, so there
  is no stale-capture hole. **No stale watcher.** Confirmed by construction, and
  consistent with your smoke.

Two nits below (n20, n21).

## 4. Notifications (dispatch focus #4)

All three requirements hold.

- **Authorization requested once.** `PublishNotifier` is an `actor` and sets
  `requestedAuthorization = true` *before* the await (`PrintworksApp.swift:145-146`),
  so concurrent publishes cannot double-prompt. The notifier instance is created
  once in `init` (`:86`) and re-captured across a Settings save (`:105`), so the
  flag survives a repo switch.
- **Refusal ignored silently.** `catch { return }` (`:149-151`) plus an explicit
  `.denied`/`.notDetermined`/`@unknown` → `return` on the settings check
  (`:154-162`). Nothing is surfaced to the user. Correct per brief.
- **Nothing fires on an empty `published`.** Guarded twice:
  `AppModel.applyRunResult` only calls `onPublished` when
  `!result.published.isEmpty` (`:887-889`), and `post` re-guards `!photos.isEmpty`
  (`:143`). Title format matches the brief exactly, including the
  `file`/`files` pluralisation (`:165-168`).

## 5. `pendingInputFiles` (dispatch focus #5)

`AppModel.swift:303-318`. Excludes snapshot stems correctly
(`!knownStems.contains(file.deletingPathExtension().lastPathComponent)`, `:314`),
is non-recursive to match the pipeline's own non-recursive `Input/` scan
(`ingest.py:145-147`), skips hidden files, and sorts. The test
(`AppModelTests.swift:1257-1275`) covers both `.rw2` and `.RW2` and a non-RAW
file. One case-sensitivity nit below (n19).

Worth recording since it is the obvious worry and it turned out fine: `ingest.run()`
does **not** remove files from `Input/` (it archives a copy, `ingest.py:219-241`),
so the banner does not clear because the file moved — it clears because the stem
enters the snapshot. And a file that fails ingest stays pending *and* raises
`PARTIAL_FAILURE` (`__main__.py:247-250`), which `ingestPending` surfaces. The
banner cannot get stuck showing a count with no way to act on it.

## 6. Regressions and nit closure (dispatch focus #6)

- **n14 — closed.** The duplicate `.onChange(of: model.selectedStyle)` is gone
  (`de1e774`, InspectorView).
- **n15 — closed, properly.** `AppModelTests.swift:615-636` now re-reads P0 at
  `:628` and asserts it was a cache *hit*, then proves P1 (not P0) is evicted via
  `cropsLog.suffix(2) == ["P40", "P1"]`. That genuinely distinguishes LRU from
  FIFO; the old test would not have.
- **n16 — closed, but overshot.** See **m13** below.
- **n13 — handled as instructed.** The report states a recommendation (an
  explicit 8×10 / 5×7 active-crop selector, dragging the selected window) and
  changed no overlay code. That is the right call: it is a UX decision, and
  silently redesigning the hit region during a bugfix task is how the sliver got
  there in the first place.
- **Tasks 7–9 otherwise intact.** The m11 fix is sound on re-read: the
  check-then-assign of `cropRequests[stem]` (`AppModel.swift:356-371`) has no
  suspension point between the nil-check and the store, so two concurrent callers
  for the same stem cannot both create a request; the second joins the first. The
  eviction branch (`:357-364`) still waits rather than cancels, which is the
  correct asymmetry — an evicted request is not superseded, a churned one is.

---

## Findings, severity-ordered

### m12 (Moderate, CONFIRMED by probe) — cancellation is wired into `run` but not `runMutating`

`PipelineClient.swift:35-48`. Cancelling a task that awaits `runMutating`
terminates nothing and returns nothing early — measured: the `TERM` trap never
fires, and the cancelled call still takes 2.005 s to return. Every driver-lock
command routes through it. Not reachable today (§1.3), so this is a latent trap
plus a coverage claim the test name does not support, not a live defect.
Full analysis and fix in §1.2.

### m13 (Minor) — n16's fix removed the revision from the key *and* the guard, so a failed crops fetch never retries

`InspectorView.swift:45`/`:296`, `ReviewView.swift:37`/`:244`

`de1e774` changed both crop keys from `stem|reviewRevision|showingCrops` to
`stem|showingCrops` (n16's ask) and, in the same hunk, dropped the
`model.photo(stem)?.reviewRevision == photo.reviewRevision` guard from both task
bodies. The model still self-heals — `AppModel.crops` caches per revision and
re-checks before returning (`:389-392`) — but nothing re-drives the view, because
the only inputs that re-fire `.task(id:)` are now the stem and the overlay toggle.

**Failure scenario.** A photo whose previews have not been generated has no
recorded render dims, so `crops --stem` fails `BAD_INPUT: render dims not
recorded` (`driver.py:441-444`) and `AppModel` deliberately caches `nil` for that
revision (`:381-385`) — the inspector shows every crop row as "unavailable".
The user hits Retry on the render failure (`GridView:78`), `run --stem` succeeds,
dims are recorded, `review_revision` moves. `cropSelectionKey` is still
`"P1|false"`, so the fetch never re-runs and the crop rows stay "unavailable"
for the rest of the session — until the user happens to press `C` twice or select
another photo and come back. Before `de1e774` the revision in the key refetched
automatically.

**Fix.** Keep the revision out of the key (n16 was right about the cost) and put
freshness back where it belongs — either restore the revision guard and re-drive
on `photo.crops.isEmpty && photo.state` transitions, or key on a cheap
"crops could plausibly have changed" token (e.g. whether render dims exist) so a
photo that could not answer once is asked again after it can.

### m14 (Minor, test infrastructure) — the m11 regression test deadlocks instead of failing

`AppModelTests.swift:683-729`, `:718`. Any stall in `crops` — not only the m11
line — hangs the suite indefinitely rather than failing it: 8 min+ observed vs
0.012 s passing. `AsyncGate` has no timeout and no suite time limit is set.
Restructure with `XCTestExpectation` + `fulfillment(of:timeout:)` and a
`defer`-based stub release; keep the peak assertion unchanged. Detail in §2.

### n17 (Nit) — `ingestPending` chains `run` unconditionally and drops skip/conflict notices

`AppModel.swift:824-845` vs `:795-818`

`ingest(paths:)` guards the chained run — "Chain `run` only when something
actually landed — a failed or fully-deduped ingest has nothing to render, and
chaining anyway would just take the lock again to report the same failure twice"
— and collects `skipped`/`conflicts` into a user-facing `INGEST_NOTICE`.
`ingestPending` does neither: it fires `run --json` even when the ingest errored,
and never builds `notices`.

**Failure scenario.** The CLI holds the driver lock. The user clicks "Ingest
now": `ingest` returns `LOCK_HELD`, then `run --json` fires anyway and returns
`LOCK_HELD` too — two futile subprocesses, and `activeCommand` reads "run"
(`:832`) for a run that never had a chance. Separately, a RAW that ingest skips
or flags as a conflict produces no user-visible message at all on this path,
while the identical file dropped on the window does.

The brief specified `ingest … --json` + `run --json` for this path, so this is
not a spec violation — but the two ingest entry points should not disagree about
a rule one of them documents in a comment.

### n18 (Nit) — `pendingInputFiles` matches fewer spellings than the pipeline does

`AppModel.swift:313` tests `pathExtension == "rw2" || == "RW2"`; the pipeline
uses `path.suffix.lower() == ".rw2"` (`ingest.py:147`). A file named `P1.Rw2` is
ingestable by the pipeline but invisible to the banner, so the user is never told
there is an unimported RAW sitting in `Input/`. The GH7 writes `.RW2` so this is
unlikely in practice; `pathExtension.lowercased() == "rw2"` closes it and matches
the pipeline exactly.

### n19 (Nit) — Settings' Cancel does not revert abandoned edits

`SettingsSheet.swift:44-45`, `:8-9`. The macOS `Settings` scene keeps its root
view alive across close/reopen, so the `@State` fields survive `dismiss()`.
Type a bogus path, press Cancel, reopen Settings: the bogus path is still there
with its error, rather than the saved values. Re-seeding both fields from the
`initial…` parameters on Cancel (or on appear) fixes it.

### n20 (Nit) — Save is not gated on an idle model

`PrintworksApp.swift:96-110`. Nothing prevents a save while a `run` is in flight.
The old `AppModel`/`PipelineClient` are dropped from the view tree but the
subprocess keeps going against the *old* repo, and its `onPublished` still fires
a notification through the retained notifier — a publish toast for a repo the app
is no longer pointed at. Harmless to the data (the pipeline is resume-safe and
the lock self-heals), but confusing. Disabling Save while
`model.activeCommand != nil`, or noting the in-flight command in the sheet,
would close it.

### n21 (Nit) — publish notifications have no body, and `lastIngestFailures` is rendered nowhere

`PrintworksApp.swift:167-169` puts the whole string in `content.title` and leaves
`content.body` empty, which renders as a title-only banner. Splitting to
`title = photo.stem`, `body = "published (v004, 29 files)"` reads better. Separately,
`AppModel.lastIngestFailures` (`:148`, populated at `:905-911`) has no consumer in
any view — so on a `PARTIAL_FAILURE` the user sees "1 file(s) failed" with no way
to learn *which* file. Pre-existing, but `ingestPending` is a new caller of it.

---

## Out of scope, untouched

m6–m10, i11, Task 8's N3/N5, kqueue vs in-place edits, `Output/photos/<stem>/`,
the Task 5 refresh gate. No visual QA (Task 11). I did not open the app, and
nothing in this review touched `~/Projects/rawdog-printworks`.

## Ship statement

**Task 10 ships as `de1e774`.** The brief's deliverables are all present and
correct: `pendingInputFiles` and `ingestPending` are test-first and argv-exact,
the Settings scene validates live with correct tilde handling and rebuilds both
client and watcher, notifications meet all three constraints, and i12 is closed.
m11 is genuinely fixed for the path that can reach it, with an assertion that
would have caught the original regression. **m12** and **m13** should be the
first two items of the next task — m12 because a false cancellation guarantee on
the driver-lock path is a trap laid for the next person, and m13 because it is a
silent regression this commit introduced. **m14** should be fixed alongside them
so a future regression in `crops` fails CI in seconds instead of stalling it.
