# Task 9 fix round 1 — dispatch

Read `task-9-rereview.md` first; it is the authority. One commit. Then stop.

## The blocker

**M1 (Major) — the crop drag hit region is the whole canvas.**
`CropOverlayView.swift:44-51`. `.position(x:y:)` makes the view take the parent's
full proposed size and `.offset` does not shrink it back, so a
`.contentShape(Rectangle())` applied *after* them installs the entire overlay as
the hit shape. Consequences: the 8×10 window **cannot be dragged at all**, and a
drag anywhere — including the black letterbox outside the photo — silently nudges
the 5×7 window into the draft that Approve later persists.

Fix: move `.contentShape(Rectangle())` **above** `.position`/`.offset`. Verify
both halves afterwards: 8×10 becomes draggable, and a press in the letterbox does
nothing.

## Also in scope

- **M2** — `crops` is fetched eagerly per selection *and* per style switch, and
  cannot be cancelled. Style switching does not change crop windows; do not refetch.
- **M3** — selecting a not-yet-previewed photo pops a red error banner.
  `crop_windows` raises `BAD_INPUT "render dims not recorded"` for a
  freshly-ingested photo, and `AppModel.crops` surfaces it as a banner, uncached,
  so it re-fires on every re-selection. Treat that specific error as "no
  suggestion yet", not a banner. Second half: `cropStatus`
  (`InspectorView.swift:275-285`) consults only `cropResult`, so both rows read
  "unavailable" even when persisted windows are already in `photo.crops` — fall
  back to `photo.crops`.
- **M4** — the `--exposure` half of `setSlider` has never executed under test:
  every call site passes `exposure: nil`. Add asserts for the exposure branch
  (`%.2f`) **and** the both-touched composition (both flags in one argv).
  Red-then-green both.
- **M5** — Approve can be permanently disabled with no on-screen reason:
  `canApprove` requires ALL styles' previews fresh (correct per §6.3), but the
  "preview out of date" chip only shows for the *selected* style. Add one line
  under Approve naming the stale styles.
- **N6** — the drag's live preview is unclamped: the outline leaves the photo and
  snaps back on release. Run the preview through the same `CropMath.nudged`.
- **N11** — `cropCache` / `cropRequests` are never pruned. We have been bitten
  twice already by unbounded caches in this app; bound it.
- **N12** — Task 9 deleted Task 8's keyboard shortcut legend and put nothing
  back. Restore it (it is how a user learns ⌘1-⌘4 / Space / ←→ / c).

## Out of scope

N7, N8, N9, N10, and everything previously deferred (m6-m10, i11, i12, kqueue vs
in-place edits, `Output/photos/<stem>/`, the Task 5 refresh gate). Settings is
Task 10. Do not "while I'm here" them.

## Gates

```
swift test --disable-sandbox --package-path app/PrintworksCore
xcodebuild -project app/RAWdogPrintworks/RAWdogPrintworks.xcodeproj \
  -scheme RAWdogPrintworks -destination 'platform=macOS' \
  OTHER_SWIFT_FLAGS='$(inherited) -disable-sandbox' build
```

Exit code is the oracle, never a grep (zsh: `$PIPESTATUS[0]` expands to nothing).

## Report + stop

Write `task-9-fix-round-1-report.md` **in this ledger directory** (not the
worktree root). You **cannot commit** — the worktree's git metadata is outside
your writable roots; leave the work uncommitted and state the intended commit
message. Do not open the app: the controller owns the smoke, and it now runs
against a scratch repo, so do not point anything at the real one. Do NOT rewrite
`HANDOFF.md`.
