# Task 5 — fix round 1

Six findings from an independent review of commit `532c311`. Every one was
reproduced by probe, not inferred. Fix all six. Do not commit — the controller
commits.

Files: `app/PrintworksCore/Sources/PrintworksCore/AppModel.swift` (primary),
`app/PrintworksCore/Sources/PrintworksCore/Debouncer.swift` (F3 only),
`app/PrintworksCore/Tests/PrintworksCoreTests/AppModelTests.swift`.

## F1 — CRITICAL. `flushPendingAdjustments(stem:)` does not flush.

`AppModel.swift:340-356` iterates `pendingAdjustments`, but `firePendingAdjust`
removes the entry BEFORE issuing the command. So once the debounce timer has
fired, the flush finds an empty collection and returns immediately while the
`adjust` is still in flight.

Required behaviour (brief + spec §5.3): it must issue any outstanding `adjust`
for every style of that stem **and wait for it to complete**.

Why it matters: user drags a slider, the 2s debounce fires, user clicks Approve
inside that window. Flush no-ops, and `approve` serializes
`expected_review_revision` from the PRE-adjust draft. Either ordering is wrong —
the adjust lands first and approve fails `STALE_REVIEW` (user must re-check all
three boxes), or approve wins and the adjust then demotes the just-published
photo.

Fix direction: track the in-flight task per (stem, style) key — or have
`firePendingAdjust` remove the entry only after the adjust completes — and have
`flushPendingAdjustments` await it. Both orderings must end with the adjust
complete before `approve` reads the draft.

This is also the cause of F6 (suite flakiness).

## F2 — IMPORTANT. The §6.1 deferral checks the wrong moment.

`reconcileDrafts` tests `activeCommand != nil && activeStem == stem` at
RECONCILE time, not at CAPTURE time. A refresh whose `status` was taken during
a command but which lands after `endCommand` cleared the flags reconciles that
intermediate snapshot and falsely marks the draft stale. `reconcileDrafts` only
ever SETS `isStale`, so a later correct refresh cannot undo it. Deterministic,
5/5 runs.

Fix direction: stamp the snapshot with the `commandGeneration` / `activeStem`
in force when its `status` was DISPATCHED, and skip reconcile for a stem whose
snapshot was captured during that stem's own command.

Urgency: Task 6 adds a file watcher and a 5-second poll, which turns this from
a race into an everyday occurrence.

## F3 — IMPORTANT. Debounced work runs inside an already-cancelled Task.

`Debouncer.fire()` calls `pendingTask?.cancel()` while executing INSIDE
`pendingTask`. Probe: inside the debounced action `Task.isCancelled == true` and
`Task.sleep(200ms)` returns in 0.3ms.

Harmless only because `PipelineClient`'s I/O happens to be
cancellation-insensitive. It is a landmine for any future timeout,
`Task.sleep`, or `withTaskCancellationHandler` beneath the slider path.

Fix in `Debouncer.swift`: do not cancel the task you are currently running
inside — compare task identity, or clear the stored reference before firing.
Add a test asserting `Task.isCancelled == false` inside the fired action.

## F4 — IMPORTANT. Retry banner button is dead on two paths.

`surface(error, details:)` with the default `retry: nil` still sets
`bannerAction = .retry` for `INTERNAL`, while leaving `lastFailedAction = nil`,
so `retryBannerAction()` silently returns. Reachable from `performRefresh`'s
failure path (`AppModel.swift:205`) and approve's "could not write the review
file" (`:425`). Task 7 will wire a button that does nothing.

Fix: either supply a real retry action on those paths, or do not offer
`.retry` when there is nothing to retry. Add a test that clicking retry after
each of those two failures produces the expected call (or no button).

## F5 — IMPORTANT. Run and ingest failure detail is discarded.

`applyRunResult` (`AppModel.swift:578-581`) stores only `result.published`.
`RunResult.failed`, `RunResult.advanced` and `IngestResult.failed` are all
dropped. Spec §7 requires the per-card "render failed" badge sourced from
`result.failed`, and per-file ingest failures currently vanish into the
aggregate banner.

Fix: store them — e.g. `lastFailures: [String: StemFailure]` keyed by stem,
populated in `applyRunResult` alongside `lastPublished`, plus the ingest
equivalent. Keep it additive; `applyRunResult` is the single write site, so
this is cheapest now. Add tests asserting a `PARTIAL_FAILURE` run populates
per-stem failures.

## F6 — The suite is flaky at ~14%, and one added test does not discriminate.

`swift test` failed 5 times in 35 runs, always
`testDebouncersAreKeyedPerStemAndStyle`, in both directions. It is a symptom of
F1 and should disappear when F1 is fixed. Verify that by running the suite at
least 25 times after your fix — for this package, fewer than 20 runs is not
evidence.

Separately, `testReconcileIsDeferredWhileTheStemsOwnCommandRuns` does NOT
discriminate: it sets the flags by hand and refreshes synchronously, so it only
proves the `continue` statement exists. It stays green while F2 fails.
Rewrite it to exercise a refresh that STARTS during a command and LANDS after
it — the only shape the bug takes in production. It must fail against the
current code and pass after your F2 fix; state that you verified both.

## Verification required

1. `swift test --package-path app/PrintworksCore` — run **at least 25 times**,
   report the pass/fail tally. Zero failures required.
2. `xcodebuild -project app/RAWdogPrintworks/RAWdogPrintworks.xcodeproj -scheme RAWdogPrintworks build`
   — must still succeed.
3. `.venv/bin/python -m pytest tests/ -q` from the worktree root — must stay
   295 passed / 1 skipped. Change no Python file and no fixture.

## Constraints

- No third-party dependencies. macOS 15. No pipeline logic in Swift. The only
  file Swift writes is the temp review-file, created OUTSIDE the repo.
- Do NOT run `git commit` — the controller stages and commits. Leave your work
  in the working tree.
- Do not weaken or delete an existing test to make something pass.
