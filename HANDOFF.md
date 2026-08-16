# HANDOFF

## Goal
RAWdog Printworks. Plan 1 (pipeline `--json`) is MERGED. **Plan 2 — the macOS
SwiftUI app (RAW-2) — is COMPLETE and UNMERGED on
`johncioni/plan2-printworks-app`.** The whole-branch review is DONE and says
MERGE AS-IS. **PR #5 IS OPEN** (25 commits, 38 files, +7153/−58). Remaining: the
user merges #5, a 6-item fix round, then cleanup. WT = 839d574.

## Done
- All 11 tasks complete. Branch-tip gates: **85 Swift tests exit 0**, xcodebuild
  exit 0, `zsh scripts/build-app.sh` exit 0 → verified-signed bundle.
- Every task verified by ME (exit code + a mutation per new test), not by report.
  Task reviews are in the archive; do not re-derive them.
- VISUAL QA PASSED (`task-11-visual-qa-note.md`): 11 verified-distinct shots,
  full loop on the scratch repo → v002 published, 29 artifacts, v001 pruned.
- THREE tests that COULD NOT FAIL were found and fixed (Tasks 6, 9, 11) — the
  recurring failure mode here, so always mutate a new test.
- USER DECISION (m12, standing): `runMutating` is intentionally UNCANCELLABLE —
  cancelling would SIGTERM RawTherapee mid-write into `staging/`. Do not "fix".
- **THIS SESSION: whole-branch review dispatched and completed** (Opus 5 xhigh in
  the plan2 worktree, 19 min). Verdict **MERGE AS-IS**; it re-ran both gates
  itself (85 Swift, 295 pytest, both exit 0) and left the worktree clean.
  Report: `docs/superpowers/sdd-archive/2026-08-12-printworks-app/whole-branch-review.md`.
  - Keep this correction: `git diff main..HEAD` looks like it deletes ~14k
    archive lines — that is main moving forward, not the branch. Real change set
    is `main...HEAD` (base 60facc9): 38 files, +7153/−58 — what PR #5 shows.
  - **SIX fix-now items, none a merge blocker: F1 F2 F3 F4 F5 F6.** Take the list
    from the review's verdict TABLES, not its closing paragraph — the closing
    names only four (it omits F3 = m7 case 3, and F5 = m9). Nothing found can
    publish or approve pixels the user did not visually approve; that was
    verified against the pipeline, not assumed.
- Archive refreshed through the review; the ledger is gitignored, archive durable.

## Ruled out
- Squashing Plan 2 — Plan 1 merged as a PR preserving its 16 per-task commits;
  this history carries the Task 7 arc, the `--force` catch and m12. User decides.
- Making `runMutating` cancellable (m12). F2's fix is a confirmation, not cancel.
- Widening Codex's writable roots — controller-commits-after-verifying IS the gate.
- Smoking mutating features against the real repo — scratch repo instead.
- Pinning main's sha here — the commit writing it invalidates it instantly.

## In flight
- **Nothing running.** Reviewer terminal `term_274c8aef…` is idle and finished
  (safe to close). The OLD Codex terminal `term_4d74c3eb…` is idle at 56%
  context — do NOT send to it.
- **THE APP POINTS AT THE SCRATCH REPO** `~/orca/workspaces/rawdog-printworks/
  smoke-repo` (P1036163 there is published v002 from the QA). CLEANUP AT THE END:
  `defaults delete com.john.rawdog-printworks repoPath` and `… pythonPath`, then
  delete smoke-repo.

## Next
1. **USER MERGES https://github.com/johncioni/rawdog-printworks/pull/5** — the
   only open question; nothing else blocks. Use a MERGE COMMIT, not squash
   (`gh pr merge 5 --merge`), preserving the 25 per-task commits per Plan 1's
   pattern. Do not merge it on the user's behalf.
2. Fix round for all SIX (F1 F2 F3 F4 F5 F6) — dispatch via the Orca loop per
   memory `orca-agent-dispatch`; the review already gives file:line and a
   concrete failure scenario for each, so the brief is a copy-out.
3. Then cleanup: restore the two defaults, delete smoke-repo, re-refresh archive.
