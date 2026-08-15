# Task 7 fix round 1 — re-review dispatch

Reviewer: Opus 5 xhigh. Scope: **`bffbf56..c9165c2`** — the fix commit only.
Read `task-7-rereview.md` (the findings) and `task-7-fix-round-1-report.md`
(what the implementer claims) first.

The prior review said Task 7 "ships once M1 and M2 are fixed, and M3 should go
with them". Your job is to decide whether it now ships.

## What the controller already verified — don't just repeat it

- `swift test --disable-sandbox` → exit 0, **60** tests. `xcodebuild` → exit 0.
- **M3 mutation, re-run by me:** restoring `--force` to `runAll()` turns
  `testIngestRunFailureRetryDoesNotForceWholeRepo` RED on both assertions.
- **M1, observed not reasoned:** with the app running I took `lsof` of the
  watched dirs (11 FDs, one per watched directory), pressed ⌘N then ⌘W, and
  re-took it — still **11**. Under the old bug `stop()` would have cancelled
  every source and closed all 11.
- **m4, measured:** the chip is now opaque `(46,47,50)` regardless of the photo
  beneath, and the badge contrast is **6.13:1** on both cards (was 1.45:1 and
  1.85:1). Screenshot: `qa/task-7-fix1-smoke.png`.

## What I could NOT verify — your focus

1. **M2's cache under real load.** I read `PreviewImage.swift` and it is a real
   actor-isolated, hash-keyed, downsampling cache — but I could not observe it
   during a live render, because triggering one means running the pipeline on
   irreplaceable photo data. Judge it by reading. Two things I noticed and want a
   second opinion on: (a) the cache key includes `maxPixelSize`, so a window
   resize generates a new key per size — better than before, but is it churn
   worth bounding? (b) `load()` evicts by `contentHash` alone, so a grid card
   changing hash also evicts the sidebar's still-live 42 pt entry for that hash.
   Correctness or just waste?
2. **Is M1's fix complete?** The per-window `defer { watcher.stop() }` is gone
   and `RepoWatcher.deinit` now owns `stop()`. Does anything still stop the
   watcher early, and does the app ever leak it instead (deinit never firing on a
   long-lived `App` struct is expected — confirm that is actually fine here)?
3. **m5's new render-failed badge** and the `retryRender(stem:)` path it calls:
   confirm it can only ever issue `run --stem S --json`, never `--force`, and
   that no UI path reaches a mutating command without explicit user action.
4. Anything the fix **broke** in Task 7's previously-correct behaviour.

## Out of scope

m6-m10 and i11/i12 were deliberately left for the whole-branch review; do not
re-litigate them or count them against shipping. Same for the earlier deferred
items (kqueue vs in-place edits, `Output/photos/<stem>/`, the Task 5 refresh
gate). `ReviewScreen` is still Task 8's; Settings is Task 10's.

## Output

Write `task-7-fix-round-1-rereview.md`: severity-ordered findings with file:line
and a concrete failure scenario, and a plain statement of whether Task 7 ships
now. If my verification above is insufficient or wrong, say so — last round's
critique of it was the most useful part of the review.
