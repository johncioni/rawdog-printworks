# HANDOFF

## Goal
RAWdog Printworks. Plan 1 (pipeline `--json` interface) is MERGED to main; its
golden fixtures are the binding contract. NOW EXECUTING Plan 2 — the macOS
SwiftUI app (RAW-2) — subagent-driven in an Orca worktree. Tasks 1-5 of 11 are
done. main = e193a22, clean, CI green.

## Done
- Plan 2 Tasks 1-4 complete, reviews clean: 0bff85d scaffold, 3378ea9 contract
  models, e47ad9c PipelineClient, 3dc7904 CropMath+Debouncer.
- Task 5 (AppModel) COMPLETE: implemented 532c311, review returned spec ❌
  (1 Critical + 5 Important), fix round 1 committed 7e19bee (Codex implemented,
  I committed — its sandbox mounts .git read-only), re-review CLEAN: all six
  ADDRESSED, no new breakage, "ship it". Verified by reverting individual
  fixes and reproducing each bug. 30 consecutive green suite runs across two
  parties, 45 tests; xcodebuild SUCCEEDED; pytest 295/1.
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
- Nothing running. Tasks 1-5 done and reviewed; Task 6 is next.
- NOTE for future Codex dispatches: it rewrote the worktree's HANDOFF.md with a
  task-scoped summary (reverted). Forbid that explicitly in the prompt.

## Next
1. START WITH THE F2-MIRROR FIX, as part of Task 6 and before its poll lands:
   a status dispatched while IDLE that lands after an adjust rebased the draft
   falsely marks it PERMANENTLY stale. Pre-existing, but Task 6's 5s poll makes
   it everyday. One line — the field already exists: in `reconcileDrafts` also
   skip when `capture.commandGeneration != commandGeneration`. Ledger has it.
2. Dispatch Task 6 (RepoWatcher) to Codex:
   `cd $WT && node ~/.claude/plugins/cache/openai-codex/codex/1.0.6/scripts/
   codex-companion.mjs task --background --write --fresh --model gpt-5.6-sol
   --effort xhigh "<prompt>"` — then stage/commit for it, and run xcodebuild
   yourself. Brief: $WT/.superpowers/sdd/.../task-6-brief.md
3. CARRY: Task 6 must NOT duplicate the refresh gate (already in AppModel).
   Task 7's spec §7 badge is UNBLOCKED — F5 added lastFailures/lastAdvanced/
   lastIngestFailures, single write site. Tasks 8/9/10 briefs are 23-25 lines
   and need fuller dispatches. Task 11 must pin an xcodebuild `-destination`.
4. Deferred minors are in the ledger — point the final whole-branch review at
   them. USER: enable swift-lsp.
