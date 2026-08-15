# HANDOFF

## Goal
RAWdog Printworks. Plan 1 (pipeline `--json`) is MERGED; its golden fixtures are
the binding contract. NOW EXECUTING Plan 2 — the macOS SwiftUI app (RAW-2) in the
Orca worktree. **Tasks 1-8 of 11 built**; Task 8 committed + gate-verified, its
SMOKE IS BLOCKED (see In flight). main = this checkpoint's commit; WT = e512205.

## Done
- Tasks 1-5 clean (0bff85d, 3378ea9, e47ad9c, 3dc7904, 532c311+7e19bee, 3212f6c).
- TASK 6 SHIPS: c36db76 + c4a10d1. (My "bounded by `maxCoalesceWait` 2s" phrasing
  was WRONG — it bounds the scheduled deadline, not delivery; see archive README.)
- TASK 7 COMPLETE after 3 review rounds: built 51f6fc6+bffbf56; c9165c2 fixed 3
  Majors (⌘N/⌘W killed the shared watcher; `.id(hash)` was a cache key with NO
  cache; ingest-Retry escalated to whole-repo `run --force`); 87511e8 bounded the
  cache that fix introduced (178.9MB/resize); bf4cbd1 fixed the regression 87511e8
  introduced. Codex implemented all; I commit each (its sandbox can't write .git).
- TASK 8 BUILT e512205: ReviewView + CompareView, ReviewScreen stub replaced.
  `rerenderPreview` already existed (Task 5), so it added the 2 required tests.
  I verified: 66 tests exit 0, xcodebuild exit 0, and I mutation-checked the
  shared-rebase test — a parallel-copy rebase turns it RED. SMOKE NOT DONE.
- VERIFICATION LESSONS (hard-won, apply to every task): (1) I GREPPED for the
  hash key instead of READING whether a cache sat behind it — that is how the
  25MP re-decode reached me; greps confirm the letter, reading the intent. (2) A
  green suite proves what is TESTED, not what is correct — 62/62 passed straight
  over the bf4cbd1 regression. (3) `open` does NOT relaunch a running app; check
  binary mtime vs process start before trusting a smoke. (4) Codex writes its
  report to the worktree ROOT, not the ledger — move it.
- CODEX SANDBOX FIXED (memory `codex-swift-sandbox-fix`). EVERY Swift dispatch
  carries BOTH flags: `swift build/test --disable-sandbox`, `xcodebuild
  OTHER_SWIFT_FLAGS='-disable-sandbox'`.
- DISPATCH IS ORCA (memory `orca-agent-dispatch`): `terminal create --worktree
  name:<wt> --command '<agent>'`, then `send --text .. --enter` / `wait --terminal
  <h> --for tui-idle` / `read`. Briefs go in the LEDGER, never the scratchpad.
- CLEANUP DONE: merged `json-interface` worktree + local/remote branch removed
  (e7afc61), merged branches 1bfe1e1/e112c86/efbdbc0 deleted, main pushed. Live
  photo data verified intact. SWIFT-LSP DROPPED by user — do not reintroduce.

## Ruled out
- Settled, don't reopen: Task 6's refresh gate (§7), `_state_stamps()` (§4.2).
- Two original-review minors (kqueue blind to in-place edits; `Output/photos/
  <stem>/` unwatched) — still deferred to the whole-branch review.
- Redirecting Xcode caches to /tmp — the manifest cache is not redirectable.
- `danger-full-access` for Codex — would expose the main repo's live photo data.
- Fix round 2 for Task 6 — reviewer's call and mine: carry P1+M1-M4 into Task 7.
- Pinning main's sha here — the commit writing it invalidates it instantly.

## In flight
- TASK 8 SMOKE BLOCKED: macOS Accessibility re-blocks each freshly built binary
  ("visible windows but no accessibility window"), so computer-use cannot drive
  the review canvas. USER ACTION: toggle Orca Computer Use off/on in System
  Settings ▸ Privacy & Security ▸ Accessibility, then the smoke can run.
  The built app is open (read-only; do NOT click Reprocess — live photo data).
- WT=~/orca/workspaces/.../plan2-printworks-app (HEAD e512205); ledger
  $WT/.superpowers/sdd/2026-08-12-printworks-app/ is GITIGNORED but now ARCHIVED
  through Task 6 to `docs/superpowers/sdd-archive/2026-08-12-printworks-app/`
  (on origin), REFRESHED through Task 7 incl. qa/ screenshots.

## Next
1. Task 8 smoke once Accessibility is toggled: open P1036163's review, confirm
   ⌘1-⌘4 switch style and space shows the 4-up compare. Then dispatch Task 8's
   re-review (scope bf4cbd1..e512205) per the Orca method.
2. Then Task 8. Briefs 8/9/10 are 23-25 lines and need spec §5-§8, the AppModel
   surface, Task 7's view files, the sandbox flags. Task 11 pins `-destination`.
   Refresh the docs/ archive (incl. qa/) when Plan 2 completes.
