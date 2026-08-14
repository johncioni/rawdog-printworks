# HANDOFF

## Goal
RAWdog Printworks. Plan 1 (pipeline `--json` interface) is MERGED to main; its
golden fixtures are the binding contract. NOW EXECUTING Plan 2 — the macOS
SwiftUI app (RAW-2) — subagent-driven in an Orca worktree. Tasks 1-5 of 11 are
done. main = a20cdfc, clean, CI green.

## Done
- Plan 2 Tasks 1-4 complete, reviews clean: 0bff85d scaffold, 3378ea9 contract
  models, e47ad9c PipelineClient, 3dc7904 CropMath+Debouncer.
- Task 5 (AppModel) implemented 532c311; review returned spec ❌ with 1 Critical
  + 5 Important, all probe-reproduced. Fix round 1 committed as 7e19bee —
  Codex implemented, I committed (its sandbox mounts .git read-only).
  Controller-verified: xcodebuild SUCCEEDED, `swift test` 15/15 consecutive
  runs green at 45 tests (was ~14% flaky before), pytest 295/1 skipped.
- MODEL POLICY (in memory): Codex Sol 5.6 xhigh IMPLEMENTS, Opus 5 xhigh
  REVIEWS. Fable exhausted — never route to it. Codex's writable root is the
  CWD THAT LAUNCHES IT, so always `cd $WT` first; job state is keyed the same
  way. Codex cannot run xcodebuild (sandbox, exit 74) — controller does it.
- REPO-MOVE ORPHAN AUDIT (docs/repo-move-orphans.md): the move stranded 4
  memories (incl. the model directive) and the Codex trust entry; both fixed.

## Ruled out
- Squash-merging Plan 1 — the 16 per-task commits are the record.
- Requiring `expected_review_revision`; widening `_state_stamps()` — both
  adjudicated (spec §4.2; review rounds 2+3).
- Moving Task 6's refresh gate out of Task 5 — the reviewer confirmed it is
  spec §7's watcher-storm rule verbatim, so it belongs regardless.
- Deleting the 38MB raw Plan 1 transcript at ~/.claude/projects/-Users-john-
  photo-edits--claude-worktrees-json-interface/ — superseded by the archive.

## In flight
- WT=~/orca/workspaces/rawdog-printworks/plan2-printworks-app (branch
  johncioni/plan2-printworks-app, HEAD 7e19bee). Ledger + 11 briefs + reports:
  $WT/.superpowers/sdd/2026-08-12-printworks-app/progress.md
- TASK 5 SCOPED RE-REVIEW running (opus) on review-532c311..7e19bee.diff. It
  verdicts F1-F6 ADDRESSED/NOT. If it is gone when you resume, re-dispatch it
  from that diff file — it is the last step before Task 5 closes.
- Codex job task-mssl68qs-lmks2k COMPLETED (20m21s), corroborating my own
  verification: 25/25 suite runs, and its rewritten race test failed pre-fix
  and passes post-fix. NOTE: it also rewrote the worktree's HANDOFF.md with a
  task-scoped summary — reverted; forbid that in future Codex prompts.

## Next
1. Read the re-review verdict; if all six ADDRESSED, append to the ledger
   `Task 5: complete (commits 3dc7904..7e19bee, 1 fix round)` and start Task 6.
   Any NOT ADDRESSED → fix round 2 (max 5), same Codex recipe.
2. Dispatch Task 6 (RepoWatcher) to Codex:
   `cd $WT && node ~/.claude/plugins/cache/openai-codex/codex/1.0.6/scripts/
   codex-companion.mjs task --background --write --fresh --model gpt-5.6-sol
   --effort xhigh "<prompt>"` — then stage/commit for it, and run xcodebuild
   yourself. Brief: $WT/.superpowers/sdd/.../task-6-brief.md
3. CARRY: Task 6 must NOT duplicate the refresh gate (already in AppModel).
   Task 7 needs a `RunResult.failed` field for spec §7's badge — F5 may have
   added it; check before briefing. Tasks 8/9/10 briefs are 23-25 lines and
   need fuller dispatches. Task 11 must pin an xcodebuild `-destination`.
4. Deferred minors are in the ledger — point the final whole-branch review at
   them. USER: enable swift-lsp.
