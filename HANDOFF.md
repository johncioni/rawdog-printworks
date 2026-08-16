# HANDOFF

## Goal
RAWdog Printworks: resumable RAW → print pipeline (Python) plus the macOS SwiftUI
app that drives it. **Both plans and the fix round are MERGED. Cleanup is done.**
main = `0efe335`; one worktree, one branch, no scratch state. This is a finished
resting point — the next session starts new work, not a continuation.

## Done (this session)
- **Whole-branch review** of Plan 2 (Opus 5 xhigh): verdict MERGE AS-IS, six
  fix-now items. **Read F1–F6 off its verdict TABLES**, not its closing
  paragraph, which names only four.
- **PR #5 (Plan 2, 25 commits) merged** as `3919b99` — it was CONFLICTING on
  `HANDOFF.md` alone, and fixing that fired the `tests` CI gate **for the first
  time**: GitHub cannot build a merge ref for a conflicting PR.
- **PR #6 (fix round, 4 commits) merged** as `2a6b97a`: `f93ec85` gating (F1–F6),
  `964d708` weak tests, `852b0e5` concurrency, `1e60c72` CodeRabbit's #6 findings.
- **CodeRabbit: 32 findings on #5** (could NOT post inline — GitHub limit) plus 2
  on #6, reconciled and archived. It found a weak-test cluster the human review
  missed, and missed F1/F2/F6 entirely.
- **Gates re-run by ME per batch**, `xcodebuild` WITHOUT sandbox flags (the
  production path): swift test 92 → 93 → 99 → **100**, all exit 0. Mutations
  re-derived independently — injecting `process.terminate()` into batch 3's
  watchdog fails three assertions, pinning the no-kill rule.
- **Visual QA passed** (`docs/superpowers/sdd-archive/2026-08-16-plan2-fixes/visual-qa-note.md`):
  F1 confirmed live — all three audit boxes ticked on a PUBLISHED photo and
  Approve stayed disabled.
- **Merged main verified locally** (CI could not run): swift test 100, pytest
  **296**, `xcodebuild` Release BUILD SUCCEEDED.
- **Cleanup**: both `defaults` keys deleted, `smoke-repo` deleted (its RAW was
  byte-identical to `archive/`), both worktrees and remote branches removed.

## Ruled out
- Making `runMutating` cancellable (m12), including CodeRabbit's watchdog→SIGKILL.
- `scripts/build-app.sh:5-7` (CR Major) — false positive; that flag is the Codex
  seatbelt workaround and the Release gate passes without it.
- CR Minors/Trivials, m6 coalesce reset, PreviewImageCache cancellation
  propagation — deliberately filed, listed in the archived fix-round README.
- More polish for its own sake: after a whole-branch review, 34 triaged
  CodeRabbit findings and 4 verified fix batches, the next real signal comes
  from running an actual delivery, not another sweep.

## In flight
- **Nothing running.** No agent terminals, no background jobs, no worktrees.
- **GITHUB ACTIONS IS BLOCKED ON BILLING — USER ACTION NEEDED.** Every run since
  ~18:00 fails in 4s: *"recent account payments have failed or your spending
  limit needs to be increased."* NOT a code failure — all three gates pass
  locally on merged main. Check: `gh run list --branch main --limit 3`.

## Next
1. Nothing is required. App: `zsh scripts/build-app.sh`. Gates: `pytest tests/ -q`
   via `.venv/bin/python`, and `swift test --package-path app/PrintworksCore`.
2. Fix billing under GitHub → Billing & plans, then push a trivial commit and
   confirm `tests` goes green on main.
3. **The lab is still unchosen** — verified, not remembered: `config/lab-profiles/`
   holds only `generic-v1.yaml`, so everything published so far used the generic
   profile. Picking a lab means adding a profile YAML per the spec, and it is the
   only open item that changes rendered OUTPUT rather than code quality.
4. New RW2s: drop in `Input/`, `scripts/process.sh ingest`, review in the app.
   Dusk frames need warming sidecars — `sidecars/P1036170_*.pp3` is the template.
