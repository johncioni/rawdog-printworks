# Task 7 fix round 3 — dispatch (final round)

Read `task-7-fix-round-2-rereview.md` first; it is the authority. This is a
small, closing round: ~4 lines + one test for M1, plus two ride-alongs. One
commit. Then Task 7 is done.

**Confirmed done — do not touch:** the bounded cache and 256 px ladder, m2's
flash fix, m3's clobbering half, m4's opacity, the watcher lifetime fix, and the
`--force` guarantees. The reviewer verified all of them by execution.

## In scope

**M1 (Major, a regression this branch introduced) — the terminal refresh deletes
the failure the same command just recorded.**
`AppModel.swift:249-251`. The "clear entries disk truth invalidated" filter keys
on `state == "verified"`, but a photo that fails a *forced* re-render is still
`verified` on disk — the previously published version is still in the tree, and
`pipeline/driver.py` says so in its own docstring. So `reprocess`/`reprocessAll`
records a failure and then wipes it three lines later. The render-failed badge
and its Retry never appear, and `PARTIAL_FAILURE` maps to no banner action, so
nothing in the UI names the photo that failed. This sits on Task 7's own toolbar
(Reprocess ▸ This Photo / All Photos).

Fix per the review: stop `performRefresh` clearing a failure unless the stem
actually published something new — the version-stamp approach, four lines plus
one stored dictionary.

**The test, verbatim from the review's probe:** verified snapshot →
`reprocess(stem:)` returning `failed: [P1]` → assert the failure survives the
terminal refresh. It is RED on `87511e8` today, so it is a real regression test,
not a restatement. Confirm it goes RED before your fix and GREEN after, and say
so in the report.

**m2 (Minor) — controller's decision: FIX IT NOW, do not defer.**
Failures currently clear on only two signals, so a stem that resolves into any
state other than `verified` keeps its badge forever — including the contradictory
case where a card shows an amber "Needs review" chip and a red failed badge at
once. The review says the same stamp resolves it if extended to
`reviewRevision`; do that rather than adding a second mechanism.

**i3 (ride-along) — delete `evict(contentHash:)`.**
`PreviewImage.swift:74-82`, called from `:150`. It is redundant now the LRU
bounds the cache, and actively harmful: keyed on `contentHash` alone, it removes
every rung globally, so a grid card's hash change evicts the sidebar's entry for
a photo the sidebar is still displaying. The review calls it a three-line
deletion that makes the cache strictly better.

## Out of scope

i4 (one shared 256 MiB pool means a Task-8 canvas entry can evict the whole grid
cache) — I am carrying that into Task 8's dispatch, where the canvas actually
lands. Everything previously deferred stays deferred.

## Gates

```
swift test --disable-sandbox --package-path app/PrintworksCore
xcodebuild -project app/RAWdogPrintworks/RAWdogPrintworks.xcodeproj \
  -scheme RAWdogPrintworks -destination 'platform=macOS' \
  OTHER_SWIFT_FLAGS='$(inherited) -disable-sandbox' build
```

Exit code is the oracle, never a grep (zsh: `$PIPESTATUS[0]` expands to nothing).

## Report + stop

Write `task-7-fix-round-3-report.md`. You **cannot commit** — the worktree's git
metadata is outside your writable roots; leave the work uncommitted and state the
intended commit message. Do not open the app. Do NOT rewrite `HANDOFF.md`.

The controller verifies this one by reading the diff and re-running the gates
rather than commissioning a fourth review round, so your report should make the
diff easy to read: say exactly what the stamp stores, when it is written, and
which paths now clear a failure.
