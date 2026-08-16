# Task 7 fix round 2 — dispatch

Read `task-7-fix-round-1-rereview.md` first; it is the authority. Small round:
the reviewer scopes it at ~10 lines in `PreviewImage.swift` and ~3 in
`AppModel.applyRunResult`. Fix these four, then stop. One commit.

M1 (watcher) and M3 (`--force`) from the previous round are **confirmed done** —
do not touch them.

## In scope

**M1 (Major) — the preview cache is unbounded and grows permanently on resize.**
`PreviewImage.swift:74` (key construction), `:17` (the store). The key includes
the exact `maxPixelSize`, so one grid card across one ordinary 140 pt window
resize retains **178.9 MB permanently** — measured. Two parts, do both:

1. Quantize the size before it enters the key, e.g.
   `let maxPixelSize = (raw + 255) / 256 * 256` — a 256 px ladder. The reviewer
   measured this collapsing 141 keys / 178.9 MB to 3 keys / ~6 MB.
2. **Bound the cache by construction** — `NSCache` with a `totalCostLimit`, or an
   LRU capped around 40 entries. Do not rely on the eviction path happening to
   fire; that is what failed here.

This matters beyond Task 7: `PreviewImage.swift:60-61` advertises itself as the
loader for the review canvas too, and Task 8's canvas is a full-window image that
resizes with the window — the single worst consumer of a size-keyed cache.

**m2 (Minor) — every size change blanks the card to the grey placeholder.**
`PreviewImage.swift:122`: move `preview = nil` inside the hash-changed branch, so
a resize does not flash the placeholder. M1's quantization removes most of this
for free; do both anyway.

**m3 (Minor) — `lastFailures` is a per-command result rendered as per-photo
state, so m5's badge lies in both directions.** `AppModel.swift:662`
(`applyRunResult`): stop it clobbering other stems' failures, and clear entries
that disk truth has invalidated. Read the finding for the two failure directions.

**m4 (Minor) — the new render-failed badge reintroduces the defect m4 was filed
for.** The reviewer calls this a judgement call and would accept deferring it to
Task 11's visual QA. **The controller's decision: fix it now.** It is the same
defect class this round just fixed, in the same file, and a semi-transparent
`Color.red.opacity(0.9)` chip over an arbitrary photo has the same
unpredictable-contrast problem as the material chip did. Use an opaque fill, as
the Published badge now does.

## Out of scope

i5, i6, and everything already deferred (m6-m10, i11, i12, kqueue vs in-place
edits, `Output/photos/<stem>/`, the Task 5 refresh gate). Do not "while I'm
here" them.

## Gates — BOTH `--disable-sandbox` flags are MANDATORY

```
swift test --disable-sandbox --package-path app/PrintworksCore
xcodebuild -project app/RAWdogPrintworks/RAWdogPrintworks.xcodeproj \
  -scheme RAWdogPrintworks -destination 'platform=macOS' \
  OTHER_SWIFT_FLAGS='$(inherited) -disable-sandbox' build
```

Exit code is the oracle, never a grep (zsh: `$PIPESTATUS[0]` expands to nothing).
`xcodegen generate` if you add files.

If m3's change is testable at the model layer, add a test and red-then-green it.
The cache changes are view-layer and are not unit-testable here; instead, state
in your report what the bound is, what evicts, and what the worst-case retained
bytes are for a full-window canvas — the number, not "it is bounded now".

## Report + stop

Write `task-7-fix-round-2-report.md`. You **cannot commit** — a linked worktree's
git metadata lives in the main repo, outside your writable roots; the last round
hit `index.lock: Operation not permitted`. Do not fight it: leave the work
uncommitted, state the intended commit message, and the controller commits after
verifying. Do not open the app; the controller owns the smoke. Do NOT rewrite
`HANDOFF.md` — this report is your checkpoint.
