# HANDOFF

## Goal
RAWdog Printworks. Plan 1 and **Plan 2 are both MERGED to main** — PR #5 landed
as `3919b99` with a merge commit preserving the 25 per-task commits, both checks
green. Remaining: the agreed fix round on `johncioni/plan2-fixes` (3 batches),
then cleanup. main = this checkpoint; fix worktree = `plan2-fixes`.

## Done (this session)
- **Whole-branch review** dispatched and completed (Opus 5 xhigh, 19 min).
  Verdict MERGE AS-IS; it re-ran both gates itself. Archived at
  `docs/superpowers/sdd-archive/2026-08-12-printworks-app/whole-branch-review.md`.
  **SIX fix-now items F1–F6** — take them from its verdict TABLES, not its
  closing paragraph, which names only four (omits F3 = m7 case 3, F5 = m9).
- **Unblocked PR #5**, which was CONFLICTING on `HANDOFF.md` alone (branch
  stop-hook churn vs main's checkpoint). Merged origin/main in taking MAIN's
  copy; verified no `app/`/`scripts/` changes came with it. That also fired the
  `tests` CI gate **for the first time** — GitHub cannot build a merge ref for a
  conflicting PR, so it had never run. pytest green in 1m4s.
- **CodeRabbit: 32 findings** (16 Major), which it could NOT post inline (GitHub
  limit) — they live in the COMMENTED review body, so there are **zero inline
  comments to reply to**. Reconciled against the review in
  `docs/superpowers/sdd-archive/2026-08-12-printworks-app/coderabbit-reconciliation.md`.
  Five overlap with F1–F6; F1/F2/F6 are review-only; CR found a weak-test cluster
  the review missed.
- **Merged PR #5**; main's post-merge CI green (1m45s).
- **USER DECISIONS (standing):** (a) the m12-adjacent FIFO stall is fixed by
  **surfacing, never killing** — no signal to the subprocess, ever; (b) fix-round
  scope is **F1–F6 + CR Majors + the weak tests**, excluding CR Minors/Trivials;
  (c) merge first, fix on a follow-up branch. All three are encoded in the briefs.

## Ruled out
- `scripts/build-app.sh:5-7` (CR Major, "pass `OTHER_SWIFT_FLAGS=…-disable-sandbox`")
  — **false positive.** That flag is the Codex seatbelt workaround
  (`codex-swift-sandbox-fix`), not a production build requirement.
- Squashing Plan 2 — merged with a merge commit, history preserved.
- Making `runMutating` cancellable (m12), including via CR's watchdog→SIGKILL.
- Fixing CR Minors/Trivials in this round — deliberately filed.

## In flight
- **Batch 1 dispatched to Codex** (`gpt-5.6-sol` xhigh) in worktree
  `plan2-fixes`, terminal `term_64e51b11-2734-4516-8a51-8bf403cb5d30`; took.
- **Watcher armed** (scratchpad `watch-batch1.sh`, bg `bxx0icqbl`): exits 0 when
  `batch-1-report.md` lands, 2 on a 30-min stall, 3 if the terminal vanishes.
- Briefs: `<plan2-fixes>/.superpowers/sdd/2026-08-16-plan2-fixes/` — `README.md`
  (scope contract + out-of-scope list), `batch-1-brief.md` (gating: F1–F6),
  `batch-2-brief.md` (tests that cannot fail), `batch-3-brief.md` (concurrency).
- **THE APP STILL POINTS AT THE SCRATCH REPO** `~/orca/workspaces/
  rawdog-printworks/smoke-repo`. Cleanup at the very end.

## Next
1. On the watcher: re-run Codex's claimed RED mutations YOURSELF before accepting
   — this repo has shipped three tests that could not fail. Then run all four
   gates, commit batch 1 on Codex's behalf (its sandbox mounts `.git` read-only),
   and check `git status` for HANDOFF churn before staging.
2. Dispatch batch 2, then batch 3, same ritual (create → wait tui-idle → read →
   send → read, confirm the prompt took → arm a watcher).
3. PR the fix branch; user merges.
4. Cleanup: `defaults delete com.john.rawdog-printworks repoPath` and
   `… pythonPath`, delete smoke-repo, archive the fix-round ledger.
