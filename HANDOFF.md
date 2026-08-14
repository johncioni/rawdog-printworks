# HANDOFF

## Goal
RAWdog Printworks. Plan 1 (pipeline `--json` interface) is MERGED to main and
its golden fixtures are the binding contract. NOW EXECUTING Plan 2 — the macOS
SwiftUI app (RAW-2) — subagent-driven in an Orca worktree. Orca + GitHub +
Linear (RAW) + CodeRabbit, CI per PR. main = fba61d4, clean, CI green.

## Done
- Plan 1 merged (PR #3, merge commit) + PR #4 clamping `failed[].code` to
  ERROR_CODES. CodeRabbit: 17 findings, all answered; the serious one was
  `ingest --from` overwriting a different photo's RAW on case-insensitive vols.
- Plan 2 set up: the Orca worktree self-provisioned via the setup hook.
- PRE-FLIGHT RULING (in every dispatch from Task 4 on): bare `Sources/…`/
  `Tests/…` are relative to `app/PrintworksCore/`; app-target files live under
  `app/RAWdogPrintworks/Sources/`. Else package files land at the repo root.
- RAW-10 complete (a3e8363): run_partial_failure shows RENDER_FAILED beside
  VERIFY_FAILED, so the decoder can't be built from a one-value fixture.
- Task 1 (0bff85d): package + XcodeGen app target; the committed `.xcodeproj`
  is spec-mandated (spec §9), not a slip.
- Task 2 (3378ea9): contract models decoding the real fixtures. RULING: error
  `code` fields stay `String`, never a closed enum — tests fail to COMPILE if
  narrowed.

## Ruled out
- Squash-merging Plan 1 — the 16 per-task commits are the record.
- Mapping bare RuntimeError to an operational code — driver.py also uses it for
  internal invariants (:557), so a blanket map mislabels → RAW-9 instead.
- Requiring `expected_review_revision`; widening `_state_stamps()` — both are
  adjudicated design decisions (spec §4.2; spec review rounds 2+3).
- Hardcoding `.venv/bin/python` in tests (breaks CI, no `.venv` there) and
  `-> None` annotations (nothing in this repo is annotated; no Ruff config).

## In flight
- WT=~/orca/workspaces/rawdog-printworks/plan2-printworks-app (branch
  johncioni/plan2-printworks-app). Ledger + all 11 briefs:
  $WT/.superpowers/sdd/2026-08-12-printworks-app/
- Tasks 1-4 COMPLETE, reviews clean (0bff85d, 3378ea9, e47ad9c, 3dc7904).
  TASK 5 implementer RUNNING (AppModel — the state tree Tasks 7/9/10 extend
  and Task 11 drives; dispatched on opus). `git -C $WT log --oneline -3`.
- Task 3 needed 1 fix round: a CRITICAL silent progress-event loss lived in the
  brief's OWN mandated code (concurrent readabilityHandler read outside the
  lock → out-of-order appends → spliced JSON → events dropped, 112-263 of 400).
  Ruled to fix despite being plan-mandated; readabilityHandler replaced by a
  dedicated blocking-read loop per pipe. Re-reviewer reproduced the bug against
  pre-fix source, then 0/150 after.
  Deferred minor from Task 2 in the ledger: optional contract fields are not
  drift-tested — the final whole-branch review must triage it.
- Carried rules (in ledger): editing `project.yml` requires regenerating +
  committing the `.xcodeproj` in the SAME commit; Task 11 should pin an
  xcodebuild `-destination`; Tasks 8/9/10 briefs are thin — dispatches need
  spec §5-§8 pointers.

## Next
1. Continue the loop for Tasks 3-11: implementer → review-package → task
   reviewer → fix rounds → ledger line. All 11 briefs already generated.
2. USER: enable swift-lsp — Tasks 3+ are all Swift and I cannot enable it.
3. RAW-4 branch protection; then low/unscheduled RAW-9 (typed exceptions,
   start driver.py:277), RAW-7 (`.casefold()` stems, claim UNVERIFIED), RAW-8,
   RAW-6.
