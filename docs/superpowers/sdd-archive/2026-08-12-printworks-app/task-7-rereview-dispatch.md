# Task 7 re-review — dispatch brief

Reviewer: Opus 5 xhigh. Scope: `c4a10d1..bffbf56` (two commits).
Read `task-7-brief.md` (the spec for this task), `task-7-dispatch.md` (what the
implementer was told), and `task-7-report.md` (what it claims) before the diff.

## The two commits

- `51f6fc6` — core cleanup: **P1** (pin the coalesce window by configuration) plus
  the four minors carried over from `task-6-rereview.md` (the report calls them
  N1-N4; they are that file's M1-M4).
- `bffbf56` — the shell UI: `MainWindow`, `SidebarView`, `GridView`,
  `ErrorBanner`, `PrintworksApp` wiring, +631 lines.

## What the controller already did — do not just repeat it

I re-ran these myself; treat them as settled unless you find a reason to doubt:

- `swift test --disable-sandbox` → exit 0, 59 tests. `xcodebuild … build` → exit 0.
- The `coalesce-10x` mutant **dies**: I set the initializer default to 5000ms and
  the new test failed with `"5.0" is not equal to "0.5"`, then reverted.
- Step 3 smoke passed: the built app shows P1036163/P1036170 as **Published** and
  an **"Earlier"** sidebar group. Screenshot: `qa/task-7-shell-smoke.png`.
- Constraint grep: no repo writes and no subprocess in the app target; both views
  key images on `previewHashes["natural"]` and resolve via `RepoPaths.resolve`.

**Your value is in reading the code, not re-running the gates.** Task 7 ships
with NO unit tests by design — the brief says the gate is the build — so nothing
here is guarded by a test. That makes careful reading the only defence.

## Specific things to decide

1. **Spec §5-§8 conformance** of the four new views: the status-dot mapping, the
   grid card rules, the toolbar, the per-code `ErrorBanner` actions (§7), the
   busy pill, the empty state, the drop target.
2. **Plan 2's binding constraints** — no pipeline logic in Swift, no repo writes
   from Swift, argv-only subprocess, views add no model logic. My grep was
   shallow; verify by reading.
3. **M2's fix is contract-dependent.** `emitCoalesced` now retains
   `pendingChange` when no consumer is registered, but the retained change only
   re-fires when a *later* change arrives. `PrintworksApp.swift` registers
   `changes` before `start()`, which is what makes that safe. Is that contract
   actually sound, and is it honoured everywhere — including after a
   stop/restart? Also consider: `firstPendingChangeAt` is retained across a
   consumer-less gap, so a much later change can compute a `maxCoalesceWait`
   deadline already in the past and emit immediately. Is that acceptable?
4. **UNCONFIRMED, please look:** in the smoke screenshot the left grid card's
   "Published" text renders dimmer than the right card's, for the same state.
   Could be a mid-fade capture artifact. Decide whether it is a real defect.
5. **Reprocess wiring** calls `model.reprocess(stem:)` / `reprocessAll()`, which
   issue `run --stem S --force`. Confirm no path can fire those without explicit
   user intent — this app points at a repo holding irreplaceable photo data.

## Out of scope — do not re-litigate

kqueue's invisibility to in-place non-atomic edits; `Output/photos/<stem>/`
unwatched; the refresh gate living in Task 5; `expected_review_revision` /
`_state_stamps()`. `ReviewScreen` is deliberately a `Text` placeholder — Task 8
replaces it. The Settings scene is Task 10.

## Output

Write `task-7-rereview.md` in this directory: severity-ordered findings with
file:line and a concrete failure scenario each, and a plain statement of whether
Task 7 ships. If you think the controller's verification above was wrong or
insufficient, say so — that is more useful than agreement.
