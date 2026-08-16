# Task 7 dispatch — Shell UI (MainWindow, Sidebar, Grid, ErrorBanner)

You are the implementer. A separate Opus reviewer reviews your work afterwards —
so optimise for a reviewable diff and an honest report, not for appearing done.

## Read first (pointers, not pasted text — read the actual files)

- `.superpowers/sdd/2026-08-12-printworks-app/task-7-brief.md` — **authoritative**
  for this task: the four files, the `MainWindow` skeleton (keep those names),
  the status-dot mapping, the grid/card rules, the toolbar and Reprocess wiring.
- `.superpowers/sdd/2026-08-12-printworks-app/task-6-rereview.md` — sections
  **P1** and **M1-M4**. Three of them carry a "Concrete fix" block; follow it.
- `docs/superpowers/specs/2026-08-12-macos-app-design.md` §5-§8 — the UI the
  brief is compressing, incl. §7's per-code banner actions.
- The AppModel surface you consume: `app/PrintworksCore/Sources/PrintworksCore/
  AppModel.swift`. `Theme` is `app/RAWdogPrintworks/Sources/Theme.swift`.

## Two commits, in this order — do not squash them

**Commit A — core cleanup carried over from Task 6's re-review.** Land this
FIRST, alone, so the shell UI sits on a fixed watcher and the review can read
them apart:

- **P1**: pin the coalesce *window*. Do it by configuration, NOT by another
  wall-clock assertion — the whole point of `c4a10d1` is that wall-clock upper
  bounds break under load. Expose the computed delay to `@testable` alongside the
  existing `openFileDescriptors` seam and assert the default is `0.5` and an
  injected `.milliseconds(200)` arrives as `0.2`. Today `coalesce-10x` survives:
  a 500ms→5s slip keeps all 58 tests green while making the app 10x less
  responsive. Your new test MUST kill that mutant — verify by actually making the
  change temporarily, watching the test go RED, then reverting it.
- **M1-M4**: per the re-review's text.

**Commit B — the shell UI**, per `task-7-brief.md` Step 1: create
`MainWindow.swift`, `SidebarView.swift`, `GridView.swift`, `ErrorBanner.swift`
and wire `PrintworksApp.swift`. `ReviewScreen` stays a `Text` placeholder — Task
8 replaces it. Touch `AppModel.swift` only if a computed helper is genuinely
missing, and add no behaviour there.

## Binding constraints (Plan 2 globals — violating these fails review)

No pipeline logic in Swift. No repo writes from Swift. Argv-only subprocess
invocation. Views add no model logic — the brief's Reprocess menu calls
`model.reprocess(stem:)` / `reprocessAll()`, which already exist from Task 5.
Image loads resolve via `RepoPaths.resolve(path, repo:)` and are keyed on the
content hash (`.id(photo.previewHashes["natural"] ?? "")`) — never URL/mtime
caching.

## Gates — BOTH `--disable-sandbox` flags are MANDATORY

```
swift test --disable-sandbox --package-path app/PrintworksCore    # 58/58 + your P1 test
xcodegen generate                                                  # only if project.yml changed
xcodebuild -project app/RAWdogPrintworks/RAWdogPrintworks.xcodeproj \
  -scheme RAWdogPrintworks -destination 'platform=macOS' \
  OTHER_SWIFT_FLAGS='$(inherited) -disable-sandbox' build
```

Without those flags SwiftPM/Xcode fail on nested Seatbelt and it looks like a
compile error but is not. `CoreSimulatorService` / `DVTFilePathFSEvents` lines
are benign noise — read the tail. **Use the exit code as the oracle, never a
grep** (`cmd; echo $?`; note this shell is zsh, so `$PIPESTATUS[0]` silently
expands to nothing — a prior reviewer recorded a false green that way).

## STOP after the build — Step 3 is NOT yours

`task-7-brief.md` Step 3 is a manual smoke + screenshot. **The controller does
that**, with computer-use. Do not attempt visual QA, do not claim the UI looks
right, and do not report Task 7 complete on a green build alone — a build proves
it compiles, not that the grid renders P1036163/P1036170 as Published.

## Report

Write `.superpowers/sdd/2026-08-12-printworks-app/task-7-report.md`: what you
changed per commit, the exact gate commands with their exit codes, your P1
mutation check (RED then GREEN, with the mutant you used), and anything you were
unsure about or could not verify. State uncertainty plainly — an honest "I did
not verify X" is worth more to the reviewer than a confident overstatement.

**That report is your checkpoint. Do NOT rewrite `HANDOFF.md`** — if a stop hook
tells you to refresh a checkpoint, this report satisfies it; restore HANDOFF.md
from git before you finish if you touched it.
