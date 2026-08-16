# HANDOFF

## Goal
RAWdog Printworks. Plan 1 and **Plan 2 are both MERGED to main** (PR #5,
`3919b99`). The fix round is **complete, visually QA'd, and PR #6 is CLEAN and
MERGEABLE** — 4 commits, both checks green. Only the user's merge and cleanup
remain. Fix worktree `plan2-fixes` = `1e60c72`.

## Done (this session)
- **Whole-branch review** (Opus 5 xhigh): MERGE AS-IS, six fix-now items. **Read
  F1–F6 off its verdict TABLES**, not its closing paragraph, which names four.
- **Unblocked and merged PR #5** — CONFLICTING on `HANDOFF.md` alone. Fixing that
  fired the `tests` CI gate **for the first time**: GitHub cannot build a merge
  ref for a conflicting PR, so it had never run.
- **CodeRabbit on #5: 32 findings** it could NOT post inline (GitHub limit).
  Archived; it found a weak-test cluster the review missed, missed F1/F2/F6, and
  raised 2 more on #6 — both fixed in batch 4.
- **Fix round: 4 batches committed** — `f93ec85` gating, `964d708` weak tests,
  `852b0e5` concurrency, `1e60c72` CodeRabbit's #6 findings. Gates re-run by ME
  per batch with `xcodebuild` WITHOUT sandbox flags (the production path):
  swift test 92 → 93 → 99 → **100**, all exit 0; pytest 295 throughout.
- **Mutations re-derived independently, never replayed** — injecting
  `process.terminate()` into batch 3's watchdog fails three assertions, pinning
  the no-kill rule; classifying the settings transient branch `.valid` fails only
  the NEW state assertion while `allowsSave` still passes, demonstrating the
  exact silent regression CodeRabbit described.
- **VISUAL QA DONE** — `docs/superpowers/sdd-archive/2026-08-16-plan2-fixes/visual-qa-note.md`
  + 5 screenshots. F1 confirmed on the running app (all three audit boxes ticked
  on a PUBLISHED photo → Approve stays disabled), F2's confirmation names the
  count with Cancel default, F7's cards activate via the accessibility API, F4's
  overlay renders the persisted geometry. Nothing was reprocessed.

## Ruled out
- Making `runMutating` cancellable (m12), including CodeRabbit's watchdog→SIGKILL.
- `scripts/build-app.sh:5-7` (CR Major) — false positive; that flag is the Codex
  seatbelt workaround and my Release gate passes without it.
- CR Minors/Trivials and PreviewImageCache cancellation propagation — filed.
- Re-running the full ingest→publish loop in QA: unchanged this round.

## In flight
- **Nothing running.** App is stopped and rebuilt from committed source.
- **SYNTHETIC INPUT DOES NOT REACH THIS APP.** `press-key`/`hotkey` return
  `ok:true` and do nothing (`c`, `⌘2` both no-ops, screenshots byte-identical);
  posted CGEvent mouse clicks also fail. Only AX actions work. So the crop DRAG,
  arrow-key nudge and all keyboard shortcuts are **unverified against the running
  app** — they rest on unit tests. Don't claim otherwise. To see a keyboard-gated
  view, temporarily default it on and rebuild (I did this for the overlay, then
  reverted; tree is clean).
- **APP STILL POINTS AT THE SCRATCH REPO** `smoke-repo`. Cleanup below.

## Next
1. **USER MERGES https://github.com/johncioni/rawdog-printworks/pull/6** —
   `gh pr merge 6 --merge` (NOT squash). Not on their behalf. CLEAN/MERGEABLE,
   pytest + CodeRabbit both pass; its 2 inline comments are the ones batch 4
   already fixed, and its CHANGES_REQUESTED review predates that commit.
2. Cleanup after merge: `defaults delete com.john.rawdog-printworks repoPath`
   and `… pythonPath`, delete `~/orca/workspaces/rawdog-printworks/smoke-repo`,
   remove the `plan2-printworks-app` and `plan2-fixes` worktrees.
3. Filed for later: CR Minors/Trivials, m6 coalesce reset, PreviewImageCache
   cancellation propagation, and the crop drag once real input can be delivered.
