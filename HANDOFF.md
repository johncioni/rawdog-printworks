# HANDOFF

## Goal
RAWdog Printworks. Plan 1 (pipeline `--json`) is MERGED. **Plan 2 — the macOS
SwiftUI app (RAW-2) — is COMPLETE: all 11 tasks built, reviewed and shipped, 25
commits on `johncioni/plan2-printworks-app`, UNMERGED.** The whole-branch review
is DONE and says MERGE AS-IS. Remaining: the user's merge decision, a 6-item fix
round, then cleanup. main = this checkpoint's own commit, NOT YET PUSHED;
WT = 839d574.

## Done
- All 11 tasks complete. Gates on the branch tip: **85 tests exit 0**, xcodebuild
  exit 0, `zsh scripts/build-app.sh` exit 0 → verified-signed bundle.
- Every task verified by ME (exit code + a mutation per new test), not by report.
  Task-level reviews are in the ledger/archive; do not re-derive them.
- VISUAL QA PASSED (`task-11-visual-qa-note.md`): 11 verified-distinct
  screenshots in `qa/pass/`, each saved only after a helper confirmed a marker was
  on screen AND the image differed from every prior capture. Drove the FULL loop
  on the scratch repo: slider → `adjust` (only pipeline-owned files written) →
  verified→review_required → 4 re-renders → audit → Approve enabled → approve+run
  → **v002 published, 29 artifacts, v001 pruned** → verified.
- THREE tests that COULD NOT FAIL were found and fixed across the plan (Task 6's
  coalescing, Task 9's concurrency bound, Task 11's smoke-test crops contract).
  That is the recurring failure mode here — always mutate a new test.
- USER DECISION (m12, standing): `runMutating` is intentionally UNCANCELLABLE.
  Making it cancellable would SIGTERM RawTherapee mid-write into `staging/`.
  Documented in code + pinned by a test. Do not "fix" it.
- Release-vs-Debug input anomaly RESOLVED as not-an-app-defect: the app target
  has no `#if DEBUG` code, one Info.plist, no entitlements in either config, so
  the Debug binary IS the Release binary for everything the QA exercised.
- Archive REFRESHED through Task 11: 65 md + 22 qa images in
  `docs/superpowers/sdd-archive/2026-08-12-printworks-app/` (on origin).

## Ruled out
- Squashing Plan 2 — Plan 1 merged as a PR preserving its 16 per-task commits and
  squashing was ruled out then; this branch's history carries the Task 7 arc, the
  `--force` catch and the m12 reasoning. Same pattern recommended, user decides.
- Making `runMutating` cancellable (see m12 above).
- Widening Codex's writable roots — controller-commits-after-verifying IS the gate.
- Smoking mutating features against the real repo — scratch repo instead.
- Pinning main's sha here — the commit writing it invalidates it instantly.

## In flight
- **Nothing running.** The whole-branch review is DONE (2026-08-16, Opus 5 xhigh,
  19 min). Verdict: **MERGE AS-IS.** Full report archived on main at
  `docs/superpowers/sdd-archive/2026-08-12-printworks-app/whole-branch-review.md`
  (ledger copy in the worktree). Worktree left clean, HEAD still 839d574.
  It re-ran both gates itself: 85 Swift tests exit 0, 295 pytest exit 0.
  - Its correction worth keeping: `git diff main..HEAD` LOOKS like it deletes
    ~14k archive lines — that is main moving forward, not the branch. The real
    change set is `main...HEAD` (base 60facc9): 38 files, +7153/−58.
  - **Fix-now list — SIX items, none a merge blocker.** Take this from the
    review's verdict TABLES, not its closing paragraph: the closing names only
    four, an internal inconsistency in the report. The six: F1 `canApprove`
    (`AppModel.swift:524-530`) has no `state` gate → re-approving a published
    photo demotes it and republishes v002, rmtree-ing v001; F2 "Reprocess ▸ All
    Photos" is one unconfirmed click into an uncancellable whole-repo
    `run --force` (needs a `.confirmationDialog`, NOT a cancel — m12 stands);
    **F3 = m7 case 3**, the drop target (`MainWindow.swift:50-53`) is the one
    mutating affordance with no re-entrancy guard, so two quick drops unlock
    every busy-gated control mid-ingest; F4/n13 the 8×10 crop is undraggable
    under 5×7 so the mis-grab is what gets approved; **F5 = m9**, needs-review
    counts computed by string-comparing a display label in two copies;
    F6/n21 `lastIngestFailures` renders nowhere.
  - Filed-not-fixed: M1, m6+i5, m8, i11, Task 8 N3, n19, F7 grid a11y, F8
    `.convertFromSnakeCase` on dict keys, F9/F10/F11 nits. Dropped as
    already-fixed or benign: M2, N1, N2/N3, N4, m10, n14/n15/n16, n18, n20, N5.
    I1 confirmed as the wanted behaviour.
- The OLD Codex terminal `term_4d74c3eb…` is idle at 56% context — do NOT send to
  it. Reviewer terminal `term_274c8aef…` is idle and finished; safe to close.
- **THE APP POINTS AT THE SCRATCH REPO** `~/orca/workspaces/rawdog-printworks/
  smoke-repo` (P1036163 there is now published v002 from my QA). CLEANUP AT THE
  END: `defaults delete com.john.rawdog-printworks repoPath` and `… pythonPath`,
  then delete smoke-repo.
- WT = 839d574. Ledger is gitignored; the archive on main is the durable copy.

## Next
1. **USER DECIDES THE MERGE — this is the open question, nothing else blocks.**
   Both the reviewer and I recommend a PR preserving the 25 per-task commits
   (same pattern as Plan 1), then the F1/F2/F4/F6 fix round as a short follow-up.
   The reviewer's argument for merge-then-fix: holding does not make the fixes
   safer, and none of them can publish or approve unapproved pixels.
2. Fix round for all SIX (F1 F2 F3 F4 F5 F6) — dispatch via the Orca loop, brief
   from the review's finding sections; each has file:line and a concrete
   scenario already.
3. Then cleanup: restore the two defaults, delete smoke-repo, re-refresh archive.
