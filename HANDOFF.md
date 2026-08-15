# HANDOFF

## Goal
RAWdog Printworks. Plan 1 (pipeline `--json`) is MERGED; its golden fixtures are
the binding contract. NOW EXECUTING Plan 2 — the macOS SwiftUI app (RAW-2) in the
Orca worktree. **Tasks 1-7 of 11 done**; Task 7 had a review + fix round, whose
re-review is RUNNING. main = this checkpoint's own commit, pushed; WT = c9165c2.

## Done
- Tasks 1-4 clean (0bff85d, 3378ea9, e47ad9c, 3dc7904); Task 5 AppModel 532c311
  + 7e19bee "ship it"; F2-mirror gap closed 3212f6c. Detail in the WT ledger.
- TASK 6 SHIPS: c36db76 + c4a10d1; 20 mutants re-derived, 19 killed. My "bounded
  by `maxCoalesceWait` 2s" phrasing was WRONG (it bounds the scheduled deadline,
  not delivery); full correction in the docs archive README.
- TASK 7 BUILT by Codex: 51f6fc6 + bffbf56 (+631). Review found 3 MAJORS, all
  real: M1 ⌘N/⌘W killed the shared watcher for the surviving window; M2 `.id(hash)`
  was a cache key with NO cache (25MP re-decode per body pass, ~265ms/invalidation);
  M3 ingest-failure "Retry" escalated to a whole-repo `run --force`. Fixed in
  c9165c2 (+ m4 badge contrast, m5 render-failed badge), committed by me because
  a linked worktree's .git is outside Codex's writable roots.
- I VERIFIED THE FIX MYSELF: tests exit 0 (60), xcodebuild exit 0; M3 mutation
  RED when `--force` restored; M1 OBSERVED via lsof — 11 watched-dir FDs survive
  ⌘N/⌘W (old bug closed all 11); m4 measured 6.13:1 contrast (was 1.45/1.85).
  Screenshots in ledger `qa/` + docs archive. LESSON: my first pass GREPPED for
  the hash key instead of READING whether a cache sat behind it — that is how M2
  reached me. Greps confirm the letter, reading confirms the intent.
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
- TASK 7 FIX RE-REVIEW RUNNING (Opus, `term_72835830-…`), scope bffbf56..c9165c2,
  brief `task-7-fix-round-1-rereview-dispatch.md`; watcher polls for
  `task-7-fix-round-1-rereview.md`. The built app is open (read-only; do NOT
  click Reprocess — it runs the pipeline on live photo data).
- WT=~/orca/workspaces/.../plan2-printworks-app (HEAD c9165c2); ledger
  $WT/.superpowers/sdd/2026-08-12-printworks-app/ is GITIGNORED but now ARCHIVED
  through Task 6 to `docs/superpowers/sdd-archive/2026-08-12-printworks-app/`
  (f8546a4, on origin). Task 7's files are NOT yet archived.

## Next
1. On the fix re-review: if it ships, move to Task 8 (`task-8-dispatch.md` is
   WRITTEN and waiting — append the carry-forwards to its last section first).
   If not, another fix round via the same loop.
2. Then Task 8. Briefs 8/9/10 are 23-25 lines and need spec §5-§8, the AppModel
   surface, Task 7's view files, the sandbox flags. Task 11 pins `-destination`.
   Refresh the docs/ archive (incl. qa/) when Plan 2 completes.
