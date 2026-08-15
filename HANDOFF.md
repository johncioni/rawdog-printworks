# HANDOFF

## Goal
RAWdog Printworks. Plan 1 (pipeline `--json`) is MERGED to main; its golden
fixtures are the binding contract. NOW EXECUTING Plan 2 — the macOS SwiftUI app
(RAW-2) — subagent-driven in an Orca worktree. Tasks 1-5 of 11 complete; Task
6's fix round 1 is done on disk but UNCOMMITTED. main = 1dd2295.

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
- MODEL POLICY: Codex Sol 5.6 xhigh IMPLEMENTS, Opus 5 xhigh REVIEWS (Fable
  exhausted, never route to it). Codex's writable root is the CWD THAT LAUNCHES
  IT, so always `cd $WT` first; job state is keyed the same way. It rewrites
  HANDOFF.md (its own Stop hook outranks any prohibition) — revert, don't argue.

## Ruled out
- Squash-merging Plan 1 — the 16 per-task commits are the record.
- Requiring `expected_review_revision`; widening `_state_stamps()` — both
  adjudicated (spec §4.2; review rounds 2+3).
- Moving Task 6's refresh gate out of Task 5 — spec §7's watcher-storm rule
  verbatim, re-confirmed by Task 6's reviewer.
- Two Task 6 minors (kqueue misses in-place edits; `Output/photos/<stem>/`
  unwatched) — deferred to the whole-branch review.
- Redirecting Xcode caches to /tmp to dodge the sandbox — 5 variants all failed;
  the manifest-loading cache is not redirectable. Fixed properly instead.

## In flight
- WT=~/orca/workspaces/rawdog-printworks/plan2-printworks-app (branch
  johncioni/plan2-printworks-app, HEAD b3fcf2a). Ledger + briefs + reports:
  $WT/.superpowers/sdd/2026-08-12-printworks-app/ (progress.md)
- TASK 6 FIX ROUND 1 IS COMPLETE BUT UNCOMMITTED: 3 files, +451/-29
  (RepoWatcher.swift, RepoWatcherTests.swift, AppModelTests.swift). Codex ran
  30/30 green then DIED on `stream disconnected` before writing its report, so
  `task-6-fix-round-1.md` does not exist. Reconstruct it from the transcript:
  ~/.codex/sessions/2026/08/14/rollout-2026-08-14T08-34-23-01a00044-*.jsonl
  Backup patch: <scratchpad>/codex-task6-fixround1.patch
  All 7 findings map to new tests. I have since confirmed `xcodebuild` BUILD
  SUCCEEDED and 58 XCTests pass — but NOT yet under load.
- Task 7's written dispatch was LOST with the crashed session's scratchpad;
  rewrite it from task-7-brief.md.

## Next
1. Run the suite UNDER LOAD in $WT (exit code as oracle, never a grep), then
   commit the fix round for Codex, then dispatch the scoped re-review on it.
2. Then Task 7. Tasks 8/9/10 briefs are 23-25 lines and need the same
   treatment: spec §5-§8, the AppModel surface, the view files Task 7 leaves,
   and the Swift sandbox flags. Task 11 must pin a `-destination`.
3. Deferred minors: in the ledger, for the whole-branch review. USER: swift-lsp.
