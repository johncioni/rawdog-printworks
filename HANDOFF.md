# HANDOFF

## Goal
RAWdog Printworks. Plan 1 and **Plan 2 are both MERGED to main** — PR #5 landed
as `3919b99`, a merge commit preserving the 25 per-task commits, both checks
green. Remaining: the fix round on `johncioni/plan2-fixes` (3 batches), cleanup.

## Done (this session)
- **Whole-branch review** done (Opus 5 xhigh); verdict MERGE AS-IS. **SIX
  fix-now items F1–F6 — read them off its verdict TABLES**, not its closing
  paragraph, which names only four (omits F3 = m7 case 3, F5 = m9).
- **Unblocked and merged PR #5.** It was CONFLICTING on `HANDOFF.md` alone;
  merged origin/main in taking MAIN's copy. That also fired the `tests` CI gate
  **for the first time** — GitHub cannot build a merge ref for a conflicting PR.
  pytest green pre-merge (1m4s) and on main after (1m45s).
- **CodeRabbit: 32 findings** (16 Major) which it could NOT post inline (GitHub
  limit) — so there are **zero inline comments to reply to**; they live in the
  COMMENTED review body. Five overlap F1–F6, F1/F2/F6 are review-only, and it
  found a weak-test cluster the review missed. Both documents are archived under
  `docs/superpowers/sdd-archive/2026-08-12-printworks-app/`.
- **USER DECISIONS (standing):** (a) the m12-adjacent FIFO stall is fixed by
  **surfacing, never killing** — no signal to the subprocess, ever; (b) fix-round
  scope is **F1–F6 + CR Majors + the weak tests**, excluding CR Minors/Trivials;
  (c) merge first, fix on a follow-up branch. All three are encoded in the briefs.

## Ruled out
- `scripts/build-app.sh:5-7` (CR Major, "pass `OTHER_SWIFT_FLAGS=…-disable-sandbox`")
  — **false positive**: that flag is the Codex seatbelt workaround
  (`codex-swift-sandbox-fix`), not a production build requirement. Confirmed —
  my own `xcodebuild` Release gate passes without it.
- Making `runMutating` cancellable (m12), including via CR's watchdog→SIGKILL.
- Fixing CR Minors/Trivials in this round — deliberately filed.

## In flight
- **BATCH 1 DONE and COMMITTED** as `f93ec85` (10 files, +426/−85). All four
  gates re-run by me, plus three of its seven mutations, chosen independently.
- **BATCH 2 DONE and COMMITTED** as `964d708` (6 files, +117/−57). Gates re-run
  by me: swift test **93** exit 0 ×3, xcodebuild Release SUCCEEDED without
  sandbox flags, pytest 295. Two mutations re-derived independently and
  stronger than Codex's — deleting Debouncer's cancellation handling outright
  still fails the cancellation test (which previously exercised none).
- **Batch 3 running** in a FRESH terminal
  `term_8f69f5e5-4f02-4615-a472-ccad08aadadf` (the batch-1+2 terminal hit 69%
  context); watcher bg `b2kg358jm`. An earlier watcher was reaped by the harness
  while Codex was healthy — if one dies, re-arm and read the terminal.
- Briefs: `<plan2-fixes>/.superpowers/sdd/2026-08-16-plan2-fixes/` — `README.md`
  (scope contract + out-of-scope list), `batch-1-brief.md` (gating: F1–F6),
  `batch-2-brief.md` (tests that cannot fail), `batch-3-brief.md` (concurrency).
- **APP STILL POINTS AT THE SCRATCH REPO** `smoke-repo`. Cleanup at the end.

## Next
1. On the watcher: re-run the claimed RED mutations YOURSELF — batch 2 is
   *entirely* about tests that cannot fail. Restore-point trick: `git add -A`
   first, mutate, then `git checkout -- <file>` restores from the index without
   losing Codex's uncommitted work. Then all four gates, then commit on its
   behalf (its `.git` is read-only); check `git status -- HANDOFF.md` first.
2. Dispatch batch 3 to a FRESH Codex terminal (create → wait tui-idle → read →
   send → read, confirm the prompt took → arm a watcher).
3. PR the fix branch; user merges. Then cleanup: `defaults delete
   com.john.rawdog-printworks repoPath` and `… pythonPath`, delete smoke-repo,
   archive the fix-round ledger.
