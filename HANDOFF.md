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
- **Unblocked and merged PR #5** — it was CONFLICTING on `HANDOFF.md` alone.
  Resolving it also fired the `tests` CI gate **for the first time**: GitHub
  cannot build a merge ref for a conflicting PR, so it had never run.
- **CodeRabbit on #5: 32 findings** it could NOT post inline (GitHub limit) —
  they live in the COMMENTED review body. Reconciled and archived; it found a
  weak-test cluster the review missed, and missed F1/F2/F6 entirely.
- **Fix round batches 1–4 committed** — `f93ec85` gating, `964d708` weak tests,
  `852b0e5` concurrency, `1e60c72` CodeRabbit's 2 findings on #6. Gates re-run by
  ME per batch with `xcodebuild` WITHOUT sandbox flags (the production path):
  swift test 92 → 93 → 99 → **100**, all exit 0; pytest 295 throughout.
- **Mutations re-derived independently, not replayed**, and made stronger —
  notably injecting `process.terminate()` into batch 3's watchdog, which fails
  three assertions. That pins the no-kill property the user chose.

## Ruled out
- Making `runMutating` cancellable (m12), including via CodeRabbit's
  watchdog→SIGKILL. Batch 3 surfaces the stall instead and signals nothing.
- `scripts/build-app.sh:5-7` (CR Major) — **false positive**: that flag is the
  Codex seatbelt workaround, not a build requirement; my Release gate passes
  without it. CR Minors/Trivials and the PreviewImageCache cancellation half are
  filed, not dropped. Squashing either branch — both keep per-batch commits.

## In flight
- **VISUAL QA IS BLOCKED: THE SCREEN IS LOCKED.** `orca computer get-app-state`
  returns `permission_denied` "visible windows but no accessibility window" even
  though both permissions are granted — `CGSSessionScreenIsLocked = True` is the
  real cause, the same thing that produced vacuous smokes last round. **Ask the
  user to unlock; do not fabricate screenshots.** The app is BUILT (from
  `1e60c72`), LAUNCHED (pid was 20456), and already pointed at `smoke-repo`,
  whose two photos are both `verified` — an ideal fixture for F1.
- PR #6 has batch 4 pushed; pytest passed again (1m12s), CodeRabbit re-reviewing.
- **APP STILL POINTS AT THE SCRATCH REPO** `smoke-repo`. Cleanup below.

## Next
1. **Ask the user to unlock the screen**, then run the QA in step 2. Verify with
   `CGSessionCopyCurrentDictionary()['CGSSessionScreenIsLocked']` before trusting
   any AX read — a locked screen fails as a permission error, not a lock error.
2. **VISUAL QA before the merge — the user asked for this.** Batch 1 changed the
   crop-grab interaction (no undo) and batch 3 made grid cards Buttons; tests
   pass while an interaction can still be wrong. Drive the app on the SCRATCH
   repo, never the real one: an 8×10 grab must target 8×10, arrow-key nudge must
   work, cards must be keyboard/VoiceOver operable. Keep the last pass's
   discipline (`task-11-visual-qa-note.md`): save a shot only after a marker is
   confirmed on screen AND the image differs from every prior one.
3. **USER MERGES https://github.com/johncioni/rawdog-printworks/pull/6** —
   `gh pr merge 6 --merge`. Not on their behalf.
4. Cleanup after merge: `defaults delete com.john.rawdog-printworks repoPath`
   and `… pythonPath`, delete `smoke-repo`, remove both worktrees, archive
   `batch-4-*`.
