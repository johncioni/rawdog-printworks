# Task 8 dispatch — ReviewView + CompareView

You are the implementer. A separate Opus reviewer reviews this afterwards, so
optimise for a reviewable diff and an honest report, not for appearing done.

> **CARRY-FORWARD FROM TASK 7'S RE-REVIEW:** see the section appended at the
> bottom of this file. If that section says "none", there are none.

## Read first (pointers — read the actual files)

- `.superpowers/sdd/2026-08-12-printworks-app/task-8-brief.md` — **authoritative**
  for this task. It is short; the behaviour it compresses lives in the spec.
- `docs/superpowers/specs/2026-08-12-macos-app-design.md` §5-§8 — the review
  screen, style switching, compare, and the stale-preview rules.
- Task 7's shipped views (`MainWindow.swift`, `GridView.swift`,
  `SidebarView.swift`) — match their conventions; you are replacing
  `MainWindow`'s `ReviewScreen` stub, not inventing a parallel style.
- `AppModel.swift` for the surface you consume and extend.

## Order of work — tests before implementation

`rerenderPreview` is new **model** behaviour and the brief requires unit tests
FIRST in `AppModelTests`. Write them red, then implement:

1. asserts the argv is exactly `["preview","--stem","P1","--style","filmic","--json"]`
   and that a refresh follows.
2. asserts the result's `reviewRevisionBefore/After` pair flows through the SAME
   shared `rebase(stem:before:after:)` path as `applyAdjust` — a matching pair
   rebases the draft, a non-matching pair marks it stale.

Test 2 is the one that matters. A parallel copy of the rebase logic that happens
to pass is a defect, not a pass: the whole point is that both commands share one
path. **This project has been bitten twice by tests that could not fail** — so
for each new test, break the behaviour it guards, watch it go RED, and revert.
Record that evidence in your report.

The views themselves need no unit tests (their gate is the build + the
controller's smoke), matching Task 7.

## Binding constraints (Plan 2 globals — violating these fails review)

No pipeline logic in Swift. No repo writes from Swift. Argv-only subprocess.
Views add no model logic. Image loading uses `NSImage(contentsOfFile:)` with
`RepoPaths.resolve` and a **content-hash** `.id(previewHash)` key —
**never `AsyncImage`, never URL/mtime caching**. The brief is explicit about
this and Task 7 already set the pattern; follow it.

## Gates — BOTH `--disable-sandbox` flags are MANDATORY

```
swift test --disable-sandbox --package-path app/PrintworksCore
xcodebuild -project app/RAWdogPrintworks/RAWdogPrintworks.xcodeproj \
  -scheme RAWdogPrintworks -destination 'platform=macOS' \
  OTHER_SWIFT_FLAGS='$(inherited) -disable-sandbox' build
```

Without them SwiftPM/Xcode fail on nested Seatbelt and it looks like a compile
error but is not. `CoreSimulatorService` / `DVTFilePathFSEvents` lines are benign
— read the tail. **Exit code is the oracle, never a grep** (`cmd; echo $?`; this
shell is zsh, so `$PIPESTATUS[0]` silently expands to nothing). If you add files,
`xcodegen generate` — the checked-in project enumerates sources explicitly, which
bit Task 7 with `cannot find 'X' in scope`.

## STOP after the build — Step 3 is NOT yours

Step 3 (manual smoke: style switching updates the canvas, space shows the 4-up
compare) belongs to the **controller**, who runs it with computer-use against the
real repo. Do not open the app, do not claim the UI behaves correctly, and do not
report Task 8 complete on a green build. A build proves compilation only.

Also: the app points at a repo holding irreplaceable photo data. Nothing you add
may trigger `run --force`, `approve`, or any mutating pipeline command without
explicit user action in the UI.

## Report

Write `task-8-report.md`: what changed, the gate commands with exit codes, your
red-then-green evidence per new test (including the mutation you used), and what
you could NOT verify. State uncertainty plainly — an honest "I did not verify X"
is worth more than a confident overstatement.

**That report is your checkpoint. Do NOT rewrite `HANDOFF.md`**; if a stop hook
asks for a checkpoint, this report satisfies it. Restore HANDOFF.md from git
before finishing if anything touched it.

---

## Carry-forward from Task 7's three review rounds

**i4 — this one is aimed at you.** `PreviewImage`'s cache is a single shared pool
with a 256 MiB `totalCostLimit`. Your review canvas is a full-window image, so a
single canvas entry can be large enough to evict the entire grid cache — measured
rungs: sidebar 42pt→256px ≈ 197 KB, grid card 260pt→768px ≈ 1.8 MB, and a canvas
entry is far larger. **Reuse `PreviewImage` as the brief intends — do not write a
second loader** — but say in your report what a canvas-sized entry costs at your
rungs and whether one pool is still the right shape. If you believe it needs
splitting (e.g. a separate pool or cost ceiling for canvas-sized entries), say so
with the numbers rather than doing a large refactor unasked.

**Patterns Task 7 had to learn the hard way — do not repeat them:**
- A content-hash `.id()` is NOT a cache. Load off the main actor and memoize;
  constructing `NSImage(contentsOf:)` inside a view body re-decodes a 25 MP JPEG
  on every body pass.
- Size-keyed cache entries must be quantized (256 px ladder) and bounded by
  construction, or one window resize retains hundreds of MB permanently.
- Any chip/badge drawn over an arbitrary photo needs an OPAQUE fill; a
  semi-transparent material or color samples the photo and lands below WCAG's
  3:1 floor unpredictably.
- Never let a retry/refresh path widen scope: `--force` must never be reachable
  from a failure the user did not explicitly ask to force.
