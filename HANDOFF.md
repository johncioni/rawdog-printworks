# HANDOFF

## Goal
RAWdog Printworks. Plan 1 (pipeline `--json`) is MERGED. **Plan 2 — the macOS
SwiftUI app (RAW-2) — is COMPLETE: all 11 tasks built, reviewed and shipped, 25
commits on `johncioni/plan2-printworks-app`, UNMERGED.** Remaining: the
whole-branch review, then the user's merge decision, then cleanup.
main = this checkpoint's own commit, pushed; WT = 839d574.

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
- **Nothing running.** The whole-branch review is DISPATCH-READY but NOT started:
  brief written at `<ledger>/whole-branch-review-dispatch.md` (also archived). It
  enumerates the ~20 deferred items with a fix-now/file/drop verdict required for
  each, plus 5 cross-seam questions. Launch per memory `orca-agent-dispatch`.
- **THE APP POINTS AT THE SCRATCH REPO** `~/orca/workspaces/rawdog-printworks/
  smoke-repo` (P1036163 there is now published v002 from my QA). CLEANUP AT THE
  END: `defaults delete com.john.rawdog-printworks repoPath` and `… pythonPath`,
  then delete smoke-repo.
- WT = 839d574. Ledger is gitignored; the archive on main is the durable copy.

## Next
_(This checkpoint was written as a deliberate handoff before a context clear —
it is a clean stopping point, not a mid-flight snapshot. Nothing is running.)_
1. Dispatch the whole-branch review (brief above). Verify the agent UI is up and
   the prompt TOOK (context > 0) before trusting `send`; arm a watcher immediately.
2. Act on its findings — fix round via the Orca loop if it blocks.
3. USER DECIDES THE MERGE. Recommend a PR preserving the 25 per-task commits.
4. Then cleanup: restore the two defaults, delete smoke-repo, re-refresh archive.
