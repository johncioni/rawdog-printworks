# HANDOFF

## Goal
RAWdog Printworks. Plan 1 (pipeline `--json`) is MERGED to main; its golden
fixtures are the binding contract. NOW EXECUTING Plan 2 — the macOS SwiftUI app
(RAW-2) in an Orca worktree. Tasks 1-5/11 done; Task 6 fix round 1 UNCOMMITTED,
pending the under-load gate. main = 8b8660b.

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
- GATE ROUND 1 FAILED 1/25 at loadavg 150 (coalesce test saw 0 emissions).
  ADJUDICATED A TEST DEFECT, NOT A PRODUCT BUG: `pendingChange` stays true and
  the newest work item holds the current generation, so an emission can only be
  LATE (bounded by `maxCoalesceWait = 2.0s`), never lost. I1 IS genuinely closed.
- I REWROTE that test (controller-authored, NOT Codex; production file untouched):
  absence assert keeps its fixed wait, arrival polls to 5s, ADDED a settle assert
  for "exactly once". Mutation-checked: per-change emit trips all 3 (30≠0,30≠1,31≠1).
- MODEL POLICY: Codex xhigh IMPLEMENTS, Opus 5 xhigh REVIEWS. Codex's writable
  root is the CWD THAT LAUNCHES IT (`cd $WT` first); it rewrites HANDOFF.md.

## Ruled out
- Settled, don't reopen: Task 6's refresh gate (§7), `_state_stamps()` (§4.2).
- Two Task 6 minors (kqueue blind to in-place edits; `Output/photos/<stem>/`
  unwatched) — deferred to whole-branch review.
- Redirecting Xcode caches to /tmp — the manifest cache is not redirectable.
- `danger-full-access` for Codex — would expose the main repo's live photo data.
- Chasing the 1/25 flake by repro — 0/20 in isolation; read the code instead.

## In flight
- WT=~/orca/workspaces/rawdog-printworks/plan2-printworks-app (HEAD b3fcf2a,
  branch johncioni/…). Ledger: $WT/.superpowers/sdd/2026-08-12-printworks-app/
- UNCOMMITTED in WT: Codex's fix round (+451/-29 over 3 files) PLUS my test
  rewrite. Backup of Codex's original: <scratchpad>/codex-task6-fixround1.patch
- GATE ROUND 2 RUNNING in background (25x `swift test` vs 20 spinners, exit code
  as oracle). Check `tail <scratchpad>/under-load-gate.out`; round 1's log is
  under-load-gate-round1.out. Script: <scratchpad>/under-load-gate.sh
- Task 7's dispatch was LOST with the crashed scratchpad; rewrite from brief.

## Next
1. On `GATE PASS`: `cd $WT && git add -A && git commit` the fix round for Codex
   (include task-6-fix-round-1.md). On FAIL, read the failing run-N.log first.
2. Then the scoped re-review of b3fcf2a..HEAD; tell it the test file is now
   controller-authored. USER DECISION PENDING: inline as Opus, or subagent.
3. Then Task 7; Tasks 8/9/10 dispatches add spec §5-§8, AppModel surface, Task
   7's view files, sandbox flags. Task 11 pins `-destination`. USER: swift-lsp.
