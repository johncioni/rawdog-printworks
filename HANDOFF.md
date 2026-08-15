# HANDOFF

## Goal
RAWdog Printworks. Plan 1 (pipeline `--json`) is MERGED to main; its golden
fixtures are the binding contract. NOW EXECUTING Plan 2 — the macOS SwiftUI app
(RAW-2) in an Orca worktree. Tasks 1-5/11 done; Task 6's fix round 1 is on disk
but UNCOMMITTED. main = 7f20c01.

## Done
- Tasks 1-4 done, reviews clean: 0bff85d scaffold, 3378ea9 models, e47ad9c
  PipelineClient, 3dc7904 CropMath+Debouncer. Task 5 (AppModel) COMPLETE:
  532c311 + fix round 7e19bee, re-review "ship it". Detail in the WT ledger.
- F2-MIRROR GAP CLOSED (3212f6c, TDD). The ledger's one-liner does NOT work — as
  `Int?` that compare is always true when captured idle, killing reconcile
  entirely; `commandGeneration` had to become non-optional.
- Task 6 (RepoWatcher) IMPLEMENTED b3fcf2a (Codex); review = SPEC ❌ + 1 Critical
  + 5 Important; fix round 1 addressed all 7 (see In flight).
- CODEX SANDBOX ROOT-CAUSED AND FIXED 2026-08-15 — supersedes "Codex cannot run
  xcodebuild"; it can now. Config fix in `~/.codex/config.toml`; writeup in memory
  `codex-swift-sandbox-fix`. EVERY Swift dispatch carries BOTH flags: `swift
  build/test --disable-sandbox`, `xcodebuild OTHER_SWIFT_FLAGS='-disable-sandbox'`.
- RECONSTRUCTED the missing `task-6-fix-round-1.md` from the crashed job's
  transcript + diff; claims tagged [claimed] vs [verified]. FOR THE RE-REVIEW:
  the fix adds two `#if DEBUG` seams to production RepoWatcher.swift.
- MODEL POLICY: Codex Sol 5.6 xhigh IMPLEMENTS, Opus 5 xhigh REVIEWS (Fable
  exhausted). Codex's writable root is the CWD THAT LAUNCHES IT — `cd $WT` first.
  It rewrites HANDOFF.md (its own Stop hook wins) — revert, don't argue.

## Ruled out
- Requiring `expected_review_revision`; widening `_state_stamps()` — adjudicated.
- Moving Task 6's refresh gate out of Task 5 — spec §7's watcher-storm rule
  verbatim, re-confirmed by its reviewer.
- Two Task 6 minors (kqueue blind to in-place edits; `Output/photos/<stem>/`
  unwatched) — deferred to the whole-branch review.
- Redirecting Xcode caches to /tmp — 5 variants failed; the manifest cache is
  not redirectable. Fixed properly instead.
- `danger-full-access` for Codex — would expose the main repo's live photo data.

## In flight
- WT=~/orca/workspaces/rawdog-printworks/plan2-printworks-app (HEAD b3fcf2a,
  branch johncioni/…). Ledger: $WT/.superpowers/sdd/2026-08-12-printworks-app/
- TASK 6 FIX ROUND 1 COMPLETE BUT UNCOMMITTED: 3 files, +451/-29 (RepoWatcher,
  RepoWatcherTests, AppModelTests); all 7 findings map to new tests. Backup:
  <scratchpad>/codex-task6-fixround1.patch. xcodebuild BUILD SUCCEEDED + 58
  XCTests pass (verified by me).
- UNDER-LOAD GATE RUNNING in background (25x `swift test` vs 20 spinners on 10
  cores, exit code as oracle). Check `tail <scratchpad>/under-load-gate.out` and
  `pgrep -f under-load-gate.sh`. At checkpoint: 14/25 GREEN. Re-runnable script:
  <scratchpad>/under-load-gate.sh. Task 7's dispatch was LOST with the crashed
  scratchpad; rewrite it from task-7-brief.md.

## Next
1. On `GATE PASS`: `cd $WT && git add -A && git commit` the fix round for Codex
   (include task-6-fix-round-1.md). On FAIL, read the failing run-N.log first.
2. Then the scoped re-review of b3fcf2a..HEAD. USER DECISION PENDING: inline as
   Opus, or dispatch a subagent — asked, not yet answered.
3. Then Task 7; Tasks 8/9/10 dispatches must add spec §5-§8, the AppModel
   surface, Task 7's view files, and the sandbox flags. Task 11 pins
   `-destination`. Deferred minors ride the whole-branch review. USER: swift-lsp.
