# HANDOFF

## Goal
RAWdog Printworks. Plan 1 and **Plan 2 are both MERGED to main** (PR #5,
`3919b99`). The agreed fix round is **complete on `johncioni/plan2-fixes` and
open as PR #6** — 3 commits, 23 files, +1114/−263. Remaining: the user merges
#6, then cleanup. WT `plan2-fixes` = 852b0e5.

## Done (this session)
- **Whole-branch review** (Opus 5 xhigh): verdict MERGE AS-IS, six fix-now items.
  **Read F1–F6 off its verdict TABLES**, not its closing paragraph, which names
  only four (omits F3 = m7 case 3, F5 = m9).
- **Unblocked and merged PR #5.** It was CONFLICTING on `HANDOFF.md` alone;
  merged origin/main in taking MAIN's copy. That also fired the `tests` CI gate
  **for the first time** — GitHub cannot build a merge ref for a conflicting PR.
- **CodeRabbit: 32 findings** (16 Major) which it could NOT post inline (GitHub
  limit) — **zero inline comments to reply to**; they live in the COMMENTED
  review body. Reconciled and archived; it found a weak-test cluster the human
  review missed, and missed F1/F2/F6 entirely.
- **Fix round: all 3 batches done, verified, committed** — `f93ec85` gating,
  `964d708` weak tests, `852b0e5` concurrency. Gates re-run by ME per batch, with
  `xcodebuild` run WITHOUT the sandbox flags (the production path): swift test
  92 → 93 → **99**, always exit 0; pytest 295 throughout.
- **Mutations re-derived independently, not replayed** — and made stronger:
  deleting Debouncer's cancellation handling outright, restoring filled-interior
  crop targeting, renaming the display label (correctly breaks nothing), and
  injecting `process.terminate()` into the new watchdog, which fails three
  assertions. That last one pins the no-kill property the user chose.
- Ledgers archived: `docs/superpowers/sdd-archive/2026-08-12-printworks-app/`
  (review + CodeRabbit reconciliation) and `…/2026-08-16-plan2-fixes/`.

## Ruled out
- Making `runMutating` cancellable (m12), including via CodeRabbit's
  watchdog→SIGKILL. Batch 3 surfaces the stall instead and signals nothing.
- `scripts/build-app.sh:5-7` (CR Major) — **false positive**: that flag is the
  Codex seatbelt workaround, not a build requirement. Confirmed empirically —
  my `xcodebuild` Release gate passes without it.
- Fixing CR Minors/Trivials — filed. Named in the fix round's archived README.
- Squashing either branch; both preserve per-task commits.

## In flight
- **Nothing running.** Both Codex terminals are idle and finished:
  `term_64e51b11…` (batches 1–2, 69% context) and `term_8f69f5e5…` (batch 3).
- **PR #6 awaits the user.** Its checks were still resolving at handoff —
  `gh pr checks 6`. Batch 3's HANDOFF churn was reverted before staging (Codex's
  stop hook rewrote it despite the brief, and its report wrongly claims it did
  not — always verify with `git status -- HANDOFF.md`).
- **APP STILL POINTS AT THE SCRATCH REPO** `smoke-repo`. Cleanup below.

## Next
1. **USER MERGES https://github.com/johncioni/rawdog-printworks/pull/6** —
   `gh pr merge 6 --merge`. Do not merge on their behalf. Confirm `gh pr checks 6`
   is green first; if CodeRabbit re-reviews, reconcile before acting on it.
2. Cleanup after the merge: `defaults delete com.john.rawdog-printworks repoPath`
   and `defaults delete com.john.rawdog-printworks pythonPath`, then delete
   `~/orca/workspaces/rawdog-printworks/smoke-repo`, then remove the
   `plan2-printworks-app` and `plan2-fixes` worktrees.
3. Consider a visual QA pass on the fix round before or after merge — batch 1
   changed the crop-grab interaction and batch 3 changed the grid card into a
   Button, and neither was exercised against the real app.
