# HANDOFF

## Goal
RAWdog Printworks. Plan 1 (pipeline `--json`) is MERGED to main; its golden
fixtures are the binding contract. NOW EXECUTING Plan 2 — the macOS SwiftUI app
(RAW-2), subagent-driven in an Orca worktree. Tasks 1-5 of 11 complete; Task 6's
fix round 1 is done on disk but UNCOMMITTED. main = e890e19.

## Done
- Plan 2 Tasks 1-4 complete, reviews clean: 0bff85d scaffold, 3378ea9 contract
  models, e47ad9c PipelineClient, 3dc7904 CropMath+Debouncer.
- Task 5 (AppModel) COMPLETE: 532c311 + fix round 7e19bee, re-review "ship it".
- F2-MIRROR GAP CLOSED (3212f6c, TDD). The ledger's suggested one-liner does NOT
  work — as `Int?`, `capture.commandGeneration != commandGeneration` is always
  true when captured idle, killing reconcile; the field had to go non-optional.
- Task 6 (RepoWatcher) IMPLEMENTED b3fcf2a (Codex); review returned SPEC ❌ +
  1 Critical + 5 Important; fix round 1 addressed all 7 (see In flight).
- CODEX SANDBOX ROOT-CAUSED AND FIXED 2026-08-15 — supersedes "Codex cannot run
  xcodebuild (exit 74)"; it can now. Seatbelt broke SwiftPM/Xcode 3 ways (write
  outside workspace, nested `sandbox-exec`, macro plugin server). Config fix is
  applied in `~/.codex/config.toml`; full writeup in memory
  `codex-swift-sandbox-fix`. EVERY Swift dispatch must carry both flags —
  `swift build/test --disable-sandbox` and `xcodebuild
  OTHER_SWIFT_FLAGS='$(inherited) -disable-sandbox'` — config alone is NOT
  enough. `CoreSimulatorService`/`DVTFilePathFSEvents` noise is benign.
- RECONSTRUCTED the missing `task-6-fix-round-1.md` into the WT ledger from the
  crashed job's transcript + the diff. Claims are tagged [claimed] (Codex's
  narration) vs [verified] (I re-ran it). Flagged for the re-review: the fix
  adds two `#if DEBUG` seams to production RepoWatcher.swift
  (`_startForTesting`, `_runOnPrivateQueueForTesting`) — accept/reject call.
- MODEL POLICY: Codex Sol 5.6 xhigh IMPLEMENTS, Opus 5 xhigh REVIEWS (Fable
  exhausted, never route to it). Codex's writable root is the CWD THAT LAUNCHES
  IT, so always `cd $WT` first. It rewrites HANDOFF.md (its own Stop hook
  outranks any prohibition) — revert, don't argue.

## Ruled out
- Squash-merging Plan 1 — the 16 per-task commits are the record.
- Requiring `expected_review_revision`; widening `_state_stamps()` — adjudicated.
- Moving Task 6's refresh gate out of Task 5 — spec §7's watcher-storm rule
  verbatim, re-confirmed by Task 6's reviewer.
- Two Task 6 minors (in-place edits invisible to kqueue; `Output/photos/<stem>/`
  unwatched) — deferred to the whole-branch review.
- Redirecting Xcode caches to /tmp — 5 variants failed; the manifest-loading
  cache is not redirectable. Fixed properly instead.
- `danger-full-access` for Codex — would expose the main repo's live photo data.

## In flight
- WT=~/orca/workspaces/rawdog-printworks/plan2-printworks-app (branch
  johncioni/plan2-printworks-app, HEAD b3fcf2a). Ledger:
  $WT/.superpowers/sdd/2026-08-12-printworks-app/
- TASK 6 FIX ROUND 1 COMPLETE BUT UNCOMMITTED: 3 files, +451/-29 (RepoWatcher,
  RepoWatcherTests, AppModelTests); all 7 findings map to new tests. Backup
  patch: <scratchpad>/codex-task6-fixround1.patch. I confirmed xcodebuild BUILD
  SUCCEEDED + 58 XCTests pass.
- UNDER-LOAD GATE RUNNING in background (25x `swift test` vs 20 spinners on 10
  cores, exit code as oracle). Check: `tail <scratchpad>/under-load-gate.out`;
  `pgrep -f under-load-gate.sh`. At checkpoint time: 4/25 GREEN, still running.
  Script: <scratchpad>/under-load-gate.sh (re-runnable).
- Task 7's dispatch was LOST with the crashed scratchpad; rewrite from brief.

## Next
1. When the gate prints `GATE PASS`, `cd $WT && git add -A && git commit` the
   fix round on Codex's behalf (include task-6-fix-round-1.md). If it prints
   GATE FAIL, read the failing `<scratchpad>/run-N.log` before anything else.
2. Then the scoped re-review of the fix diff (b3fcf2a..HEAD). USER DECISION
   PENDING: run it inline as Opus, or dispatch a subagent — asked, not answered.
3. Then Task 7; Tasks 8/9/10 dispatches must add spec §5-§8, the AppModel
   surface, Task 7's view files, and the sandbox flags. Task 11 pins
   `-destination`. Deferred minors ride the whole-branch review. USER: swift-lsp.
