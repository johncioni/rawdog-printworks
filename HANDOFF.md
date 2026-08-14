# HANDOFF

## Goal
RAWdog Printworks. Plan 1 (pipeline `--json` interface) is MERGED to main; its
golden fixtures are the binding contract. NOW EXECUTING Plan 2 — the macOS
SwiftUI app (RAW-2) — subagent-driven in an Orca worktree. main = 225eedb,
clean, CI green.

## Done
- Plan 2 Tasks 1-4 COMPLETE, reviews clean (0bff85d, 3378ea9, e47ad9c,
  3dc7904). Task 5 AppModel implemented (532c311, 40/40) — reviewer running.
- Task 3 took 1 fix round: a CRITICAL event loss in the brief's OWN mandated
  code (readabilityHandler race); replaced with a blocking-read loop per pipe.
- RAW-10 (a3e8363): run_partial_failure shows RENDER_FAILED beside
  VERIFY_FAILED, so the decoder can't be built from a one-value fixture.
- REPO-MOVE ORPHAN AUDIT (docs/repo-move-orphans.md). Tool state is keyed by
  absolute path; the move stranded 4 memories (incl. the model-usage directive
  — why Tasks 1-5 wrongly ran Claude implementers) and the Codex trust entry.
  Both fixed (trust backup: ~/.codex/config.toml.bak-premove-fix).
- MODEL POLICY (memory updated): Codex Sol 5.6 xhigh IMPLEMENTS, Opus 5 xhigh
  REVIEWS. Fable is exhausted — never route work to it.
- Plan 1 SDD ledger/briefs/reports ARCHIVED to docs/superpowers/sdd-archive/
  (305c396) — they lived only in the json-interface worktree's gitignored
  .superpowers/. Removing that worktree is now safe.

## Ruled out
- Squash-merging Plan 1 — the 16 per-task commits are the record.
- Requiring `expected_review_revision`; widening `_state_stamps()` — adjudicated
  design decisions (spec §4.2; spec review rounds 2+3).
- Archiving or deleting the 38MB raw Plan 1 transcript at
  ~/.claude/projects/-Users-john-photo-edits--claude-worktrees-json-interface/
  — too big to commit, and everything durable in it is now in the sdd-archive,
  the plan doc, or git. Leave it; deletion is irreversible for marginal gain.
- Moving Task 6's refresh gate out of Task 5 — the reviewer confirmed it is
  spec §7's watcher-storm rule verbatim, so it belongs regardless.

## In flight
- WT=~/orca/workspaces/rawdog-printworks/plan2-printworks-app (branch
  johncioni/plan2-printworks-app). Ledger + all 11 briefs + task reports:
  $WT/.superpowers/sdd/2026-08-12-printworks-app/
- TASK 5 IN FIX ROUND 1/5, dispatched to CODEX (gpt-5.6-sol xhigh, --fresh) —
  the first Codex dispatch of this run. Spec ❌: review found 1 Critical +
  5 Important, all probe-reproduced, incl. `flushPendingAdjustments` not
  flushing (approve can serialize a pre-adjust revision) and a ~14% flaky
  suite. Fix spec: $WT/.superpowers/sdd/.../task-5-fix-round-1.md.
  CODEX CANNOT COMMIT (.git read-only in its sandbox) — I stage and commit.

## Next
1. When Task 5's review lands: ledger it, then dispatch TASK 6 TO CODEX —
   `gpt-5.6-sol` at xhigh, `--fresh` (never `--resume`). Its sandbox mounts
   `.git` read-only so I commit on its behalf; if it rejects all writes twice,
   fall back to Opus. Then Tasks 7-11 the same way, Opus 5 reviewing.
2. Tasks 8/9/10 briefs are only 23-25 lines — Codex needs fuller dispatches
   than Claude did: spec §5-§8 pointers, the AppModel surface Task 5 actually
   produced, and the view files Task 7 leaves behind.
3. CARRY INTO TASK 6: the refresh gate already exists in AppModel; do not
   duplicate it. CARRY INTO TASK 7: `RunResult.failed` is not stored, so spec
   §7's per-card "render failed" badge needs one more field, unbriefed.
4. CARRY INTO TASK 11: pin an xcodebuild `-destination`; any task editing
   `project.yml` must regenerate + commit the `.xcodeproj` in the same commit.
5. Deferred minors are logged in the ledger — point the final whole-branch
   review at them. USER: enable swift-lsp.
