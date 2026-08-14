# HANDOFF

## Goal
RAWdog Printworks. Plan 1 (pipeline `--json` interface) is MERGED to main; its
golden fixtures are the binding contract. NOW EXECUTING Plan 2 — the macOS
SwiftUI app (RAW-2) — subagent-driven in an Orca worktree. Tasks 1-5 of 11 are
complete; Task 6 is implemented and in its first fix round. main = 0fb1dfa.

## Done
- Plan 2 Tasks 1-4 complete, reviews clean: 0bff85d scaffold, 3378ea9 contract
  models, e47ad9c PipelineClient, 3dc7904 CropMath+Debouncer.
- Task 5 (AppModel) COMPLETE: 532c311 + fix round 7e19bee, re-review "ship it".
- F2-MIRROR GAP CLOSED (3212f6c, I implemented it, TDD): a status dispatched
  while IDLE that landed after an adjust rebased the draft marked it
  permanently stale. NOTE the ledger's suggested one-liner does NOT work — as
  `Int?`, `capture.commandGeneration != commandGeneration` is always true when
  captured idle, killing reconcile entirely; the field had to go non-optional.
- Task 6 (RepoWatcher) IMPLEMENTED b3fcf2a (Codex), gates green, BUT review
  returned SPEC ❌ + 1 Critical + 5 Important. Fix round 1 is running.
- MODEL POLICY: Codex Sol 5.6 xhigh IMPLEMENTS, Opus 5 xhigh REVIEWS (user
  re-confirmed 2026-08-14; Fable exhausted, never route to it). Codex's
  writable root is the CWD THAT LAUNCHES IT, so always `cd $WT` first; job
  state is keyed the same way (`status <id>` elsewhere = "No job found").
- CODEX + HANDOFF.md, root cause found: it rewrites this file because the Stop
  hook fires in ITS session and outranks any prohibition I write. Expect it,
  revert it, or point its checkpoint at task-N-report.md. Don't re-litigate.
- Codex CANNOT run xcodebuild (exit 74), which would leave every remaining
  view task uncompilable by its implementer. Workaround = the `swiftc
  -typecheck` recipe in the ledger (verified non-vacuous; type-check only, so
  I still run the real build gate myself).

## Ruled out
- Squash-merging Plan 1 — the 16 per-task commits are the record.
- Requiring `expected_review_revision`; widening `_state_stamps()` — both
  adjudicated (spec §4.2; review rounds 2+3).
- Moving Task 6's refresh gate out of Task 5 — it is spec §7's watcher-storm
  rule verbatim. Task 6's reviewer re-confirmed it satisfies Task 6's brief.
- Fixing two Task 6 minors (kqueue misses in-place edits; `Output/photos/
  <stem>/` unwatched) — both logged for the whole-branch review.

## In flight
- WT=~/orca/workspaces/rawdog-printworks/plan2-printworks-app (branch
  johncioni/plan2-printworks-app, HEAD b3fcf2a). Ledger + briefs + reports +
  reviews: $WT/.superpowers/sdd/2026-08-12-printworks-app/ (progress.md)
- TASK 6 FIX ROUND 1: Codex job task-mssxil2l-p8mc9m, poll bffde0f3e. F1 is
  the Critical — `changes` is single-shot, so one cancelled consumer kills the
  watcher forever and `stop()` cannot end a consumer loop. F2-F7 (untested
  coalescing, 6/11 untested dirs, `stop()` self-queue deadlock, no coalesce
  max-wait, the FakeClient.mutateLog race, 4 minors) are in the ledger.
- Task 7's full dispatch is WRITTEN and ready to fire once Task 6 closes:
  <scratchpad>/task7-prompt.md (session e7e004ec-ea32-40c7-ad29-efa604d73354)

## Next
1. On fix-round completion: revert HANDOFF.md in $WT, confirm scope, commit for
   Codex, run xcodebuild + the suite UNDER LOAD (idle green is weak evidence
   for this package — use the exit code, never a grep, as the oracle), then
   dispatch the scoped re-review on the fix diff.
2. Then Task 7 (dispatch above). Tasks 8/9/10 briefs are 23-25 lines and need
   the same treatment: spec §5-§8, the AppModel surface, the view files Task 7
   leaves, the typecheck recipe. Task 11 must pin a `-destination`.
3. Deferred minors: in the ledger, for the whole-branch review. USER: swift-lsp.
