# HANDOFF

## Goal
RAWdog Printworks. Plan 1 (pipeline `--json`) is MERGED. **Plan 2 — the macOS
SwiftUI app (RAW-2) — is COMPLETE and UNMERGED.** The whole-branch review says
MERGE AS-IS and **PR #5 is OPEN and MERGEABLE** (conflict resolved). Remaining:
CI + CodeRabbit land, reconcile, a 6-item fix round, user merges, cleanup.
WT = 460f72c.

## Done (this session)
- **Dispatched and completed the whole-branch review** (Opus 5 xhigh in the plan2
  worktree, 19 min). Verdict **MERGE AS-IS**; it re-ran both gates itself — 85
  Swift tests exit 0, 295 pytest exit 0 — leaving the worktree clean.
  Report: `docs/superpowers/sdd-archive/2026-08-12-printworks-app/whole-branch-review.md`
  - Keep this correction: `git diff main..HEAD` looked like it deleted ~14k
    archive lines — that was main moving forward, not the branch. Real change set
    is the three-dot diff: 38 files, +7153/−58 — what PR #5 shows.
  - **SIX fix-now items, none a merge blocker: F1 F2 F3 F4 F5 F6.** Take the list
    from the review's verdict TABLES, not its closing paragraph — the closing
    names only four (it omits F3 = m7 case 3, and F5 = m9). Nothing found can
    publish or approve pixels the user did not visually approve.
- Pushed main and the branch; **opened PR #5**.
- **Unblocked PR #5** (`460f72c`): it was CONFLICTING on one file, `HANDOFF.md`
  — branch stop-hook churn vs main's checkpoint. Merged origin/main into the
  branch taking MAIN's copy (authoritative by convention); verified the merge
  brought in **no `app/` or `scripts/` changes**, only main's docs archive.
  PR is now MERGEABLE and **the `tests` CI gate fired for the first time** —
  before this it had never run, because GitHub cannot build a merge ref for a
  conflicting PR.
- **The fix round has NOT started** — deliberately, pending CodeRabbit.

## Carried forward (still true)
- All 11 tasks verified by the controller (exit code + a mutation per new test).
  THREE tests that COULD NOT FAIL were caught that way (Tasks 6, 9, 11) — the
  recurring failure mode here, so always mutate a new test.
- VISUAL QA PASSED: full loop on the scratch repo → v002 published, v001 pruned.
- USER DECISION (m12, standing): `runMutating` is intentionally UNCANCELLABLE —
  cancelling would SIGTERM RawTherapee mid-write into `staging/`. Do not "fix".

## Ruled out
- Squashing Plan 2 — this history carries the Task 7 arc, the `--force` catch
  and m12. PR #5 asks for a merge commit.
- Making `runMutating` cancellable (m12). F2's fix is a confirmation, not cancel.
- **Starting the fix round before CodeRabbit lands** — its findings must be
  reconciled against F1–F6 first, or we double-fix or reopen dismissed items.
- Rebasing the branch onto main to clear the conflict — a merge commit keeps the
  25 per-task commits intact and the checkout is shared with agents.

## In flight
- **Watcher armed on PR #5's checks** (scratchpad `watch-pr5.sh`, bg
  `bm3a8q852`): polls every 30s, exits when nothing is `pending`, times out at
  ~45 min. Manual check: `gh pr checks 5`.
- `pytest` (macOS runner) in progress; **CodeRabbit re-queued** by the new commit.
- **THE APP POINTS AT THE SCRATCH REPO** `~/orca/workspaces/rawdog-printworks/
  smoke-repo`. Cleanup at the very end.

## Next
1. Read the watcher result. If `pytest` fails, that is a real regression — CI has
   never run on this branch before, so treat a failure as new information.
2. Reconcile CodeRabbit's findings against F1–F6 into ONE fix-vs-dismiss list
   before any code changes.
3. Fix round for the reconciled list — dispatch per memory `orca-agent-dispatch`.
4. User merges #5: `gh pr merge 5 --merge` (NOT squash). Not on their behalf.
5. Cleanup: `defaults delete com.john.rawdog-printworks repoPath` and
   `… pythonPath`, delete smoke-repo, re-refresh the archive.
