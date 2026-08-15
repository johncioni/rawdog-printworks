# HANDOFF

## Goal
RAWdog Printworks. Plan 1 (pipeline `--json`) is MERGED to main; its golden
fixtures are the binding contract. NOW EXECUTING Plan 2 — the macOS SwiftUI app
(RAW-2) in an Orca worktree. Tasks 1-6/11 implemented; Task 6 is COMMITTED and
green, awaiting only its scoped re-review. main = 23fcd7e; WT = c4a10d1.

## Done
- Tasks 1-4 done, reviews clean: 0bff85d scaffold, 3378ea9 models, e47ad9c
  PipelineClient, 3dc7904 CropMath+Debouncer. Task 5 (AppModel) COMPLETE:
  532c311 + 7e19bee, re-review "ship it". Detail in the WT ledger.
- F2-MIRROR GAP CLOSED (3212f6c, TDD). The ledger's one-liner does NOT work — as
  `Int?` that compare is always true when captured idle, killing reconcile;
  `commandGeneration` had to become non-optional.
- TASK 6 FIX ROUND 1 COMMITTED as TWO commits, split for authorship clarity:
  c36db76 = Codex's fix for all 7 findings (C1 multicast `changes`, I1-I5, the
  4 minors); c4a10d1 = MY test rewrite (see below). Re-review both.
- GATE ROUND 1 FAILED 1/25 at loadavg 150 (coalesce test saw 0 emissions).
  ADJUDICATED A TEST DEFECT, NOT A PRODUCT BUG: `pendingChange` stays true and
  the newest work item holds the current generation, so an emission can only be
  LATE (bounded by `maxCoalesceWait` 2s), never lost. The test budgeted 350ms
  from the last write — tighter than the watcher promises. I1 IS closed.
- I REWROTE that test (c4a10d1, controller-authored, NOT Codex; production file
  byte-identical): absence assert keeps its fixed wait, arrival polls to 5s,
  ADDED a settle assert for "exactly once". Mutation-checked — per-change emit
  trips all 3 (30≠0, 30≠1, 31≠1). GATE ROUND 2: 25/25 green at loadavg 158.
- ALL GATES GREEN committed: swift 58/58, xcodebuild OK, pytest 295/1, clean.
- CODEX SANDBOX ROOT-CAUSED AND FIXED — supersedes "Codex cannot run xcodebuild".
  Config fix in `~/.codex/config.toml`; writeup in memory
  `codex-swift-sandbox-fix`. EVERY Swift dispatch carries BOTH flags: `swift
  build/test --disable-sandbox`, `xcodebuild OTHER_SWIFT_FLAGS='-disable-sandbox'`.
- `task-6-fix-round-1.md` is a controller RECONSTRUCTION (Codex died on a stream
  disconnect before reporting); claims tagged [claimed] vs [verified]. It lives
  on disk only (`.superpowers/` gitignored) — regenerable from its transcript.
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
- WT=~/orca/workspaces/rawdog-printworks/plan2-printworks-app (HEAD c4a10d1,
  branch johncioni/…). Ledger: $WT/.superpowers/sdd/2026-08-12-printworks-app/
- Nothing running. Gate logs + re-runnable script: <scratchpad>/under-load-gate*
- Task 7's dispatch was LOST with the crashed scratchpad; rewrite from brief.

## Next
1. Scoped re-review of b3fcf2a..c4a10d1. Tell it: c4a10d1's test file is
   controller-authored, and RepoWatcher.swift gained two `#if DEBUG` seams
   (`_startForTesting`, `_runOnPrivateQueueForTesting`) needing accept/reject.
   USER DECISION PENDING: inline as Opus, or dispatch a subagent.
2. Then Task 7; Tasks 8/9/10 dispatches add spec §5-§8, AppModel surface, Task
   7's view files, sandbox flags. Task 11 pins `-destination`. USER: swift-lsp.
