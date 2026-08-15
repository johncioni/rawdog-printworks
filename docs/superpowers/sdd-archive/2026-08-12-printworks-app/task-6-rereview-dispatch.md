# Task 6 re-review — dispatch brief

Reviewer: Opus 5 at xhigh. Scope: `b3fcf2a..c4a10d1` in this worktree.
Read `task-6-review.md` (the original findings) and `task-6-fix-round-1.md`
(the reconstructed fix report) before the diff.

## What you are deciding

Whether fix round 1 actually closes the review's 1 Critical + 5 Important + 4
minors, and whether it introduced anything new. Two commits, deliberately split:

- `c36db76` — Codex's fix (C1 multicast `changes`, I1-I5, the minors)
- `c4a10d1` — **controller-authored** (Opus), NOT the implementer's work

## Carry these in with you

1. **`task-6-fix-round-1.md` is a reconstruction, not Codex's own report.**
   Codex's job died on a stream disconnect before writing it. Claims are tagged
   `[claimed]` (from its transcript) vs `[verified]` (controller re-ran it).
   **Do not treat `[claimed]` mutation evidence as confirmed.** If a finding's
   closure rests only on a `[claimed]` line, re-verify it or say you did not.

2. **Two new `#if DEBUG` seams on production `RepoWatcher.swift`** —
   `_startForTesting(afterEntry:)` and `_runOnPrivateQueueForTesting(_:)`.
   They exist to make the start/stop race deterministic. This needs an explicit
   accept or reject: debug-only test API on a production type is a real design
   call, not a rubber stamp.

3. **`c4a10d1` is the controller's, so review it adversarially, not deferentially.**
   The original coalescing test failed 1/25 under load. It was adjudicated a TEST
   defect on this reasoning: in `scheduleCoalescedChange` every change sets
   `pendingChange = true` and the newest work item carries the current
   `coalesceGeneration`, so `emitCoalesced` cannot be starved permanently — an
   emission can only be LATE (bounded by `maxCoalesceWait` 2s), never lost.
   **If that reasoning is wrong, the product bug is still live and I1 is not
   closed.** Check it rather than accepting it.

4. **Deliberately out of scope — do not re-litigate** (logged for the
   whole-branch review): kqueue's invisibility to in-place non-atomic edits;
   `Output/photos/<stem>/` unwatched. Also settled earlier: the refresh gate
   living in Task 5 (spec §7 verbatim), `expected_review_revision` /
   `_state_stamps()` (spec §4.2).

## Gates (the sandbox fix means you can run all of these directly)

```
swift build --disable-sandbox --package-path app/PrintworksCore
swift test  --disable-sandbox --package-path app/PrintworksCore      # expect 58/58
xcodebuild -project app/RAWdogPrintworks/RAWdogPrintworks.xcodeproj \
  -scheme RAWdogPrintworks -destination 'platform=macOS' \
  OTHER_SWIFT_FLAGS='$(inherited) -disable-sandbox' build
```

Both `--disable-sandbox` flags are REQUIRED — without them SwiftPM/Xcode fail on
nested Seatbelt, which looks like a compile error but is not. Ignore
`CoreSimulatorService` / `DVTFilePathFSEvents` noise; read the tail.

Use the **exit code** as the oracle, never a grep — a prior reviewer reported a
false "20/20 green" by grepping. Idle green is weak evidence for this package:
the flake that started this round only appears in the full suite under load.

## Output

Write findings to `task-6-rereview.md` in this directory, severity-ordered, each
with file:line and a concrete failure scenario. State plainly whether Task 6
ships. If you disagree with an adjudication above, say so with evidence — a
confident "ship it" that skipped verification is worse than a blocked finding.
