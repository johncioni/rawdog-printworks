# HANDOFF

## Goal
RAWdog Printworks. Plan 1 (pipeline `--json`) is MERGED. **Plan 2 — the macOS
SwiftUI app (RAW-2) — is COMPLETE and UNMERGED on
`johncioni/plan2-printworks-app`.** The whole-branch review is DONE and says
MERGE AS-IS. **PR #5 IS OPEN** (25 commits, 38 files, +7153/−58). Remaining: the
user merges #5, a 6-item fix round, then cleanup. WT = 839d574.

## Done (this session)
- **Dispatched the whole-branch review** from the archived brief: new Orca
  terminal in the plan2 worktree, `claude --model opus --effort xhigh
  --permission-mode bypassPermissions`. Verified the prompt TOOK, armed a
  watcher, re-read at completion (the file was still being revised on arrival).
- **Review completed (19 min). Verdict: MERGE AS-IS.** It re-ran both gates
  itself — 85 Swift tests exit 0, 295 pytest exit 0 — and left the worktree
  clean at 839d574. Report archived at
  `docs/superpowers/sdd-archive/2026-08-12-printworks-app/whole-branch-review.md`.
  - Keep this correction: `git diff main..HEAD` looks like it deletes ~14k
    archive lines — that is main moving forward, not the branch. Real change set
    is `main...HEAD` (base 60facc9): 38 files, +7153/−58 — what PR #5 shows.
  - **SIX fix-now items, none a merge blocker: F1 F2 F3 F4 F5 F6.** Take the list
    from the review's verdict TABLES, not its closing paragraph — the closing
    names only four (it omits F3 = m7 case 3, and F5 = m9). Nothing found can
    publish or approve pixels the user did not visually approve; that was
    verified against the pipeline, not assumed.
- **Pushed main and the branch; opened PR #5** with a body carrying the
  change-set correction, the four gates, the review verdict and the six items.

## Carried forward (prior sessions, still true)
- All 11 tasks verified by the controller (exit code + a mutation per new test).
  THREE tests that COULD NOT FAIL were caught that way (Tasks 6, 9, 11) — the
  recurring failure mode here, so always mutate a new test.
- VISUAL QA PASSED (`task-11-visual-qa-note.md`): full loop on the scratch repo
  → v002 published, 29 artifacts, v001 pruned, only pipeline-owned files written.
- USER DECISION (m12, standing): `runMutating` is intentionally UNCANCELLABLE —
  cancelling would SIGTERM RawTherapee mid-write into `staging/`. Do not "fix".

## Ruled out
- Squashing Plan 2 — this history carries the Task 7 arc, the `--force` catch
  and m12, as Plan 1's 16 commits did. PR #5 asks for a merge commit.
- Making `runMutating` cancellable (m12). F2's fix is a confirmation, not cancel.
- Widening Codex's writable roots — controller-commits-after-verifying IS the gate.
- Smoking mutating features against the real repo — scratch repo instead.

## In flight
- **Nothing running.** Reviewer terminal `term_274c8aef…` is finished (safe to
  close); the OLD Codex terminal `term_4d74c3eb…` is at 56% — do NOT send to it.
- **THE APP POINTS AT THE SCRATCH REPO** `~/orca/workspaces/rawdog-printworks/
  smoke-repo` (P1036163 there is published v002 from the QA).

## Next
1. **USER MERGES https://github.com/johncioni/rawdog-printworks/pull/5** — the
   only open question; nothing else blocks. `gh pr merge 5 --merge` (NOT squash).
   Do not merge it on the user's behalf.
2. Fix round for all SIX (F1 F2 F3 F4 F5 F6) — dispatch via the Orca loop per
   memory `orca-agent-dispatch`; the review gives file:line and a concrete
   failure scenario for each, so the brief is a copy-out.
3. Cleanup: `defaults delete com.john.rawdog-printworks repoPath` and
   `… pythonPath`, delete smoke-repo, re-refresh the archive.
