# HANDOFF

## Goal
RAWdog Printworks. Plan 1 (pipeline `--json` interface) is MERGED to main; its
golden fixtures are the binding contract. NOW EXECUTING Plan 2 — the macOS
SwiftUI app (RAW-2) — subagent-driven in an Orca worktree. Tasks 1-5 of 11 are
done; Task 6 is in flight. main = 9b7941a, clean, CI green.

## Done
- Plan 2 Tasks 1-4 complete, reviews clean: 0bff85d scaffold, 3378ea9 contract
  models, e47ad9c PipelineClient, 3dc7904 CropMath+Debouncer.
- Task 5 (AppModel) COMPLETE: 532c311 + fix round 7e19bee (Codex implemented,
  I committed — its sandbox mounts .git read-only), re-review CLEAN, "ship it".
- F2-MIRROR GAP CLOSED (3212f6c, I implemented it, TDD): a status dispatched
  while IDLE that landed after an adjust rebased the draft marked it
  permanently stale. SnapshotCapture now always stamps commandGeneration and
  reconcile skips when it moved. NOTE the naive one-liner does NOT work — as
  `Int?`, `capture.commandGeneration != commandGeneration` is always true when
  captured idle, killing reconcile entirely; the field had to go non-optional.
  Guard removed in a scratch copy = new test fails 5/5 and nothing else does.
  20/20 green suite runs at 46 tests, xcodebuild OK, pytest 295/1.
- MODEL POLICY (in memory): Codex Sol 5.6 xhigh IMPLEMENTS, Opus 5 xhigh
  REVIEWS. Fable exhausted — never route to it. Codex's writable root is the
  CWD THAT LAUNCHES IT, so always `cd $WT` first; job state is keyed the same
  way (`status <id>` from the wrong cwd says "No job found"). Codex cannot run
  xcodebuild (sandbox, exit 74) — controller does it.

## Ruled out
- Squash-merging Plan 1 — the 16 per-task commits are the record.
- Requiring `expected_review_revision`; widening `_state_stamps()` — both
  adjudicated (spec §4.2; review rounds 2+3).
- Moving Task 6's refresh gate out of Task 5 — it is spec §7's watcher-storm
  rule verbatim, so it belongs regardless. Task 6 must NOT duplicate it.
- Deleting the 38MB raw Plan 1 transcript at ~/.claude/projects/-Users-john-
  photo-edits--claude-worktrees-json-interface/ — superseded by the archive.

## In flight
- WT=~/orca/workspaces/rawdog-printworks/plan2-printworks-app (branch
  johncioni/plan2-printworks-app, HEAD 3212f6c). Ledger + 11 briefs + reports:
  $WT/.superpowers/sdd/2026-08-12-printworks-app/progress.md
- TASK 6 (RepoWatcher) RUNNING: Codex job task-mssrwrc5-9wl7s9, dispatched from
  $WT. Background poll bcvprprzu notifies on terminal status. Its dispatch
  carries 5 rulings the brief lacks (bare-`Sources/` = app/PrintworksCore/;
  gate already exists; hard file scope incl. DO NOT TOUCH HANDOFF.md — it
  overwrote this file last time; no git, no xcodebuild; 20-run anti-flake gate).

## Next
1. When Codex finishes: `cd $WT`, read
   .superpowers/sdd/.../task-6-report.md, confirm ONLY the 2 intended files
   changed (`git status`), then stage+commit for it, run xcodebuild yourself
   (`cd $WT/app/RAWdogPrintworks && xcodebuild -project RAWdogPrintworks
   .xcodeproj -scheme RAWdogPrintworks -destination 'platform=macOS,arch=arm64'
   build`) and 20x `swift test` in $WT/app/PrintworksCore.
2. Then review Task 6 (ASK the user first — this harness is configured not to
   spawn Agent subagents unless requested).
3. CARRY: Task 7's spec §7 badge is UNBLOCKED — F5 added lastFailures/
   lastAdvanced/lastIngestFailures, single write site. Tasks 8/9/10 briefs are
   23-25 lines and need fuller dispatches (point at spec §5-§8, the AppModel
   surface, the view files Task 7 leaves). Task 11 must pin an xcodebuild
   `-destination`.
4. Deferred minors are in the ledger — point the final whole-branch review at
   them. USER: enable swift-lsp.
