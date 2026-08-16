# Task 9 dispatch — CropOverlayView + InspectorView

You are the implementer; a separate Opus reviewer reviews this afterwards.
Optimise for a reviewable diff and an honest report.

## Read first

- `.superpowers/sdd/2026-08-12-printworks-app/task-9-brief.md` — **authoritative**.
- `docs/superpowers/specs/2026-08-12-macos-app-design.md` §5-§8, esp. §6.1 for the
  stale-draft banner and re-review flow.
- `task-8-rereview.md` §3 and §6 — the carry-forwards below come from it.
- Task 7/8's shipped views for conventions; `CropMath` and `AppModel` for the
  surfaces you consume.

## Order of work — model additions TEST-FIRST (brief Step 1)

In `AppModelTests`, red-then-green each:
1. `setSlider` composes `adjust --stem P1 --style natural --temperature 5600
   --json` — **only the changed control** appears.
2. `resetAdjust` sends `--reset`.
3. `crops(stem:)` sends `["crops","--stem","P1","--json"]` **once** and caches
   until `reviewRevision` changes — assert the second call does NOT re-issue, and
   that a revision change DOES.

For each test: break the behaviour it guards, watch it go RED, revert. Record that
evidence. This project has shipped tests that could not fail; do not add another.

## Carry-forward from Task 8's re-review — REQUIRED

**M1 — name your controls.** Every control Tasks 7-8 added is nameless in the
accessibility tree, which (a) leaves a VoiceOver user hearing "button" four times
in compare mode, and (b) broke the controller's smoke tooling, costing a round.
Task 9 adds many more (two sliders, three toggles, a text field, Reset, Approve,
Re-review, the basis chip). **Give every one an `.accessibilityLabel`**, and add
the missing ones on Task 8's compare toggle, stale chip, and four compare panels
(`ReviewView.swift:106-113`, `:63-83`, `CompareView.swift:29-61`) — one line each.

**M2 — collapse the duplicated delivery derivation.** "Photos in the open
delivery" is now derived in four places (`ReviewView.swift:171-176`,
`SidebarView.swift:159-165`, `MainWindow.swift:101-117`, `GridView.swift:126`).
They agree today; the next filter or sort silently desynchronises arrow
navigation from the sidebar. Add one `AppModel.photos(inDeliveryOf:)` and use it
in all four. This is model-level derivation living in views, which also brushes
the "views add no model logic" constraint.

**Nits, fix if cheap:** N5 (Escape should close compare), N4 ("not rendered yet"
and "failed to decode" currently look identical), N3 (compare cells are portrait,
so landscape previews use ~45% of them).

## Binding constraints

No pipeline logic in Swift. **No repo writes from Swift** — the brief's smoke
checks this explicitly (`git status` must show only pipeline-owned changes, none
made by the app process). Argv-only subprocess. Views add no model logic. Images
via `PreviewImage` (hash-keyed, quantized, bounded) — do not add a second loader.

The slider debounce (2 s) and `adjust` composition are already model-tested from
Task 5 — consume them, do not reimplement.

## Gates

```
swift test --disable-sandbox --package-path app/PrintworksCore
xcodegen generate            # you are adding two files
xcodebuild -project app/RAWdogPrintworks/RAWdogPrintworks.xcodeproj \
  -scheme RAWdogPrintworks -destination 'platform=macOS' \
  OTHER_SWIFT_FLAGS='$(inherited) -disable-sandbox' build
```

Exit code is the oracle, never a grep (zsh: `$PIPESTATUS[0]` expands to nothing).

## STOP after the build

Step 4's smoke is the controller's, and it is the first one that MUTATES the
user's irreplaceable photo data (sliders write sidecars; Approve runs the
pipeline). **Do not run it, do not open the app, and do not invoke `adjust`,
`approve`, `run`, or `preview` against the repo.** Report the build only.

## Report

Write `task-9-report.md` **in this ledger directory**, not the worktree root
(the last two rounds put it at the root). Include: what changed, gate commands
with exit codes, red-then-green evidence per new test with the mutation used, and
what you could not verify. You **cannot commit** — the worktree's git metadata is
outside your writable roots; leave the work uncommitted and state the intended
commit message. Do NOT rewrite `HANDOFF.md`; this report is your checkpoint.
