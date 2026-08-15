# HANDOFF

## Goal
RAWdog Printworks. Plan 1 (pipeline `--json`) is MERGED; its golden fixtures are
the binding contract. NOW EXECUTING Plan 2 — the macOS SwiftUI app (RAW-2) in the
Orca worktree. **Tasks 1-7 of 11 done** (7 built, gate-verified and smoked by me;
NOT yet re-reviewed). main = this checkpoint's own commit, pushed; WT = bffbf56.

## Done
- Tasks 1-4 clean (0bff85d, 3378ea9, e47ad9c, 3dc7904); Task 5 AppModel 532c311
  + 7e19bee "ship it"; F2-mirror gap closed 3212f6c. Detail in the WT ledger.
- TASK 6 SHIPS: c36db76 + c4a10d1; re-review SPEC ✅, 20 mutants re-derived, 19
  killed; `#if DEBUG` seams ACCEPTED. MY ADJUDICATION UPHELD BUT MIS-STATED —
  "bounded by `maxCoalesceWait` 2s" is WRONG (it bounds the scheduled deadline,
  not delivery) and "never lost" covers scheduling only. Full text in the archive.
- TASK 7 BUILT by Codex: 51f6fc6 (P1 + 4 minors) + bffbf56 (shell UI, +631). I
  VERIFIED MYSELF, not from its report: swift test exit 0 (59), xcodebuild exit
  0, `coalesce-10x` mutant DIES (5.0≠0.5). Constraints hold; consumer registered
  before `start()` (M2's contract). SMOKE PASSED — P1036163/P1036170 Published,
  "Earlier" group present; screenshot in ledger `qa/` + docs archive. Codex
  wrongly called its own HANDOFF.md rewrite "pre-existing" (its hook, 14:07:55);
  reverted, not staged in either commit.
- CODEX SANDBOX FIXED (memory `codex-swift-sandbox-fix`). EVERY Swift dispatch
  carries BOTH flags: `swift build/test --disable-sandbox`, `xcodebuild
  OTHER_SWIFT_FLAGS='-disable-sandbox'`.
- DISPATCH IS ORCA NOW (memory `orca-agent-dispatch`): `orca terminal create
  --worktree name:<wt> --command '<agent>'` + `terminal send --text ... --enter`
  / `wait --terminal <h> --for tui-idle` / `read`. Briefs go in the LEDGER, never
  the scratchpad — that is what destroyed Task 7's original prompt.
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
- Nothing running. The built app may still be open (read-only; do NOT click
  Reprocess — it runs the pipeline on live photo data).
- WT=~/orca/workspaces/.../plan2-printworks-app (HEAD bffbf56); ledger
  $WT/.superpowers/sdd/2026-08-12-printworks-app/ is GITIGNORED but now ARCHIVED
  through Task 6 to `docs/superpowers/sdd-archive/2026-08-12-printworks-app/`
  (f8546a4, on origin). Task 7's files are NOT yet archived.

## Next
1. RE-REVIEW Task 7 (`c4a10d1..bffbf56`) — the only step left on it. Dispatch an
   Opus reviewer per the Orca method; tell it commit A closes the Task 6
   carry-forwards and B is the shell UI, and that I already ran both gates and
   the P1 mutant myself. UNCONFIRMED, ask it to look: the left grid card's
   "Published" text renders dimmer than the right's for the same state.
2. Then Task 8. Briefs 8/9/10 are 23-25 lines and need spec §5-§8, the AppModel
   surface, Task 7's view files, the sandbox flags. Task 11 pins `-destination`.
   Refresh the docs/ archive (incl. qa/) when Plan 2 completes.
