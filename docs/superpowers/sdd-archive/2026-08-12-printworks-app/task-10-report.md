# Task 10 report — Ingest banner, Settings, notifications

## Implemented

- `AppModel.pendingInputFiles` is recomputed after each successful status refresh
  from `Input/*.rw2|*.RW2`, excluding stems already present in the snapshot.
- `ingestPending()` sends exactly `ingest --delivery-id <UUID> --json`, then
  `run --json`; the new top banner exposes this action.
- Added the macOS Settings scene, closing i12. Both fields validate live after a
  600 ms debounce through a throwaway `PipelineClient.status()` call. Save is
  enabled only for the currently validated pair.
- Every repo/python path is expanded with `NSString.expandingTildeInPath` before
  URL/client/watcher use. Save persists the entered spelling and rebuilds both
  the production `PipelineClient`/`AppModel` and `RepoWatcher`.
- Published run results invoke a notification hook. The app requests notification
  authorization once on first publish use, silently ignores refusal/error, and
  posts e.g. `P1036163 published (v004, 29 files)`.
- m11: a superseded crop task is cancelled and retained in the accounting until
  it stops; `PipelineClient` now maps task cancellation to `Process.terminate()`.
  The eight-query limit therefore bounds live work, not dictionary entries.
- n14: removed the duplicate selected-style handler. n16: removed review revision
  from the two SwiftUI crop task identities. n15: the LRU test now refreshes P0's
  recency and proves P1, not P0, is evicted.

## RED then GREEN evidence

- Tests-first Task 10 RED:
  `swift test --disable-sandbox --package-path app/PrintworksCore --filter
  'AppModelTests.test(PendingInputFiles|IngestPending)'` -> exit 1; compiler
  reported both missing `pendingInputFiles` and missing `ingestPending`.
- Initial Task 10 GREEN: same filter -> exit 0, 2 tests passed.
- `pendingInputFiles` mutation: inverted the known-stem exclusion -> exit 1;
  actual `[P1.RW2]` vs expected `[P2.rw2, P3.RW2]`. Restored.
- `ingestPending` mutation: changed the chained argv to `run --force --json` ->
  exit 1 against exact expected `run --json`. Restored.
- m11 RED: four waves over eight stems -> exit 1, measured peak 32 vs bound 8.
- subprocess-cancellation RED: cancelling `PipelineClient.run` did not terminate
  the held stub -> exit 1. After implementation, both tests passed.
- Restored focused set -> exit 0, 6 tests passed (Task 10 model behavior,
  notification hook, LRU recency, m11 churn, subprocess cancellation).

## Required gates

- `swift test --disable-sandbox --package-path app/PrintworksCore` -> exit 0,
  80 tests passed.
- `xcodegen generate` from `app/RAWdogPrintworks` -> exit 0; both new Swift files
  were added to the generated project.
- `xcodebuild -project app/RAWdogPrintworks/RAWdogPrintworks.xcodeproj -scheme
  RAWdogPrintworks -destination 'platform=macOS'
  OTHER_SWIFT_FLAGS='$(inherited) -disable-sandbox' build` -> exit 0,
  `BUILD SUCCEEDED`.

## Deferred / boundaries

- n13 recommendation only, no overlay redesign: add an explicit 8x10 / 5x7
  active-crop selector and make dragging target that selected window, so the
  user does not need to discover the approximately 5%-height 8x10-only sliver.
- Did not open the app, run smoke, capture screenshots, touch the real photo
  repo, or change the controller's `repoPath` / `pythonPath` defaults.
- Did not rewrite `HANDOFF.md`, stage, or commit. Intended commit message:
  `feat(app): ingest banner, settings sheet with validation, publish notifications`.
