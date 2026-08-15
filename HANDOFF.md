# HANDOFF

## Goal
RAWdog Printworks. Plan 1 (pipeline `--json`) is MERGED; its golden fixtures are
the binding contract. NOW EXECUTING Plan 2 — the macOS SwiftUI app (RAW-2) in the
Orca worktree. **Tasks 1-7 of 11 COMPLETE** (Task 7 took 3 review rounds, all
closed). TASK 8 RUNNING. main = this checkpoint's own commit; WT = bf4cbd1.

## Done
- Tasks 1-5 clean (0bff85d, 3378ea9, e47ad9c, 3dc7904, 532c311+7e19bee, 3212f6c).
- TASK 6 SHIPS: c36db76 + c4a10d1. (My "bounded by `maxCoalesceWait` 2s" phrasing
  was WRONG — it bounds the scheduled deadline, not delivery; see archive README.)
- TASK 7 COMPLETE after 3 review rounds: 51f6fc6+bffbf56 built it; c9165c2 fixed
  3 Majors (⌘N/⌘W killed the shared watcher; `.id(hash)` was a cache key with NO
  cache; ingest-Retry escalated to whole-repo `run --force`); 87511e8 bounded the
  cache that fix introduced (one resize retained 178.9MB); bf4cbd1 fixed a
  regression 87511e8 introduced (the terminal refresh deleted the failure the
  same command recorded, because a forced-render failure is still "verified" on
  disk). Codex implemented all; I committed each, its sandbox can't write .git.
- I VERIFIED EVERY ROUND MYSELF (gates by exit code + a mutation per fix): M3's
  `--force`, m3's clobbering, and the bf4cbd1 regression test all go RED when
  reverted. M1 OBSERVED via lsof (11 watched-dir FDs survive ⌘N/⌘W). m4 measured
  6.13:1 (was 1.45/1.85). LESSONS: (1) I GREPPED for the hash key instead of
  READING whether a cache sat behind it — that is how M2 reached me; (2) a green
  suite proves what is tested, not what is correct — 62/62 passed over the
  bf4cbd1 regression; (3) `open` does NOT relaunch a running app — check binary
  mtime vs process start before trusting any smoke.
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
- TASK 8 RUNNING: Codex `term_82c0f5c5-…`, brief `task-8-dispatch.md` (its last
  section carries Task 7's lessons + i4). Watcher polls for `task-8-report.md`.
  The built app is open (read-only; do NOT click Reprocess — live photo data).
- WT=~/orca/workspaces/.../plan2-printworks-app (HEAD bf4cbd1); ledger
  $WT/.superpowers/sdd/2026-08-12-printworks-app/ is GITIGNORED but now ARCHIVED
  through Task 6 to `docs/superpowers/sdd-archive/2026-08-12-printworks-app/`
  (on origin), REFRESHED through Task 7 incl. qa/ screenshots.

## Next
1. On the fix re-review: if it ships, move to Task 8 (`task-8-dispatch.md` is
   WRITTEN and waiting — append the carry-forwards to its last section first).
   If not, another fix round via the same loop.
2. Then Task 8. Briefs 8/9/10 are 23-25 lines and need spec §5-§8, the AppModel
   surface, Task 7's view files, the sandbox flags. Task 11 pins `-destination`.
   Refresh the docs/ archive (incl. qa/) when Plan 2 completes.
