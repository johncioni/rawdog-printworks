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
- **CodeRabbit on #5: 32 findings** it could NOT post inline (GitHub limit) —
  they live in the COMMENTED review body. Reconciled and archived; it found a
  weak-test cluster the review missed, and missed F1/F2/F6 entirely.
- **Fix round batches 1–3 done, verified, committed** — `f93ec85` gating,
  `964d708` weak tests, `852b0e5` concurrency. Gates re-run by ME per batch with
  `xcodebuild` WITHOUT sandbox flags (the production path): swift test
  92 → 93 → **99**, always exit 0; pytest 295 throughout.
- **Mutations re-derived independently, not replayed**, and made stronger —
  notably injecting `process.terminate()` into batch 3's new watchdog, which
  fails three assertions. That pins the no-kill property the user chose.
- Ledgers archived under `docs/superpowers/sdd-archive/` for both rounds.

## Ruled out
- Making `runMutating` cancellable (m12), including via CodeRabbit's
  watchdog→SIGKILL. Batch 3 surfaces the stall instead and signals nothing.
- `scripts/build-app.sh:5-7` (CR Major) — **false positive**: that flag is the
  Codex seatbelt workaround, not a build requirement. Confirmed — my
  `xcodebuild` Release gate passes without it.
- CR Minors/Trivials, and PreviewImageCache cancellation propagation — filed.
- Squashing either branch; both preserve per-task commits.

## In flight
- **PR #6 is GREEN and MERGEABLE** (pytest 1m2s, CodeRabbit pass) but CodeRabbit
  posted **2 new findings** on it, so it is NOT ready to merge yet.
- **Batch 4 running** — those 2 findings — in fresh terminal
  `term_ca4695f2-5cca-45d8-84ce-63a9ab09ad8f`; watcher bg `b4fhycjvn`.
  Brief: `batch-4-brief.md`. USER DECIDED item 1 is a **partial** fix on purpose:
  bound the decode concurrency (a regression batch 3 introduced — the actor used
  to serialize decodes), but do NOT build waiter tracking or cancellation
  propagation; that half is deferred, pre-existing, and ImageIO cannot observe
  cancellation anyway. Item 2 is a test asserting only `allowsSave` — a
  cannot-fail test written during THIS round.
- Older terminals idle: `term_64e51b11…` (69%), `term_8f69f5e5…` (70%).
- **APP STILL POINTS AT THE SCRATCH REPO** `smoke-repo`. Cleanup below.

## Next
1. Verify batch 4 as with the others — re-run its mutations yourself; the bound
   test must fail against an unbounded cache. Then all four gates, then commit.
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
