# HANDOFF

## Goal
RAWdog Printworks. Plan 1 (pipeline `--json` interface) is MERGED to main and
its golden fixtures are the binding contract. NOW EXECUTING Plan 2 — the macOS
SwiftUI app (RAW-2) — subagent-driven in an Orca worktree. Orca + GitHub +
Linear (RAW) + CodeRabbit, CI per PR. main = d0e6c49, clean, CI green.

## Done
- Plan 1 merged (PR #3, merge commit, 16 task commits kept) + PR #4 clamping
  `failed[].code` to `jsonio.ERROR_CODES` with an `isinstance` guard.
  CodeRabbit: 17 findings across both, all answered; the serious one was
  `ingest --from` overwriting a different photo's RAW on case-insensitive
  volumes.
- Plan 2 run set up: the Orca worktree provisioned itself via the setup hook
  (295 pass / 1 skip, no manual steps). Ledger + pre-flight scan written.
- PRE-FLIGHT RULING (carried into every dispatch from Task 4 on): the plan
  mixes two path conventions with no stated rule — bare `Sources/…` and
  `Tests/…` are relative to `app/PrintworksCore/`; app-target files live under
  `app/RAWdogPrintworks/Sources/`. Without it an implementer would have created
  package files at the repo root and broken the build.
- RAW-10 complete (a3e8363, review clean): the canonical run_partial_failure
  fixture now shows RENDER_FAILED alongside VERIFY_FAILED, so Plan 2's decoder
  cannot be modelled from a fixture implying one value. No production change.
- Linear: RAW-1, RAW-5, RAW-10 Done. Open: RAW-2 (running), RAW-4, RAW-6..9.

## Ruled out
- Squash-merging Plan 1 — the 16 per-task commits are the record.
- Mapping bare RuntimeError to an operational code — driver.py also uses it for
  internal invariants (:557), so a blanket map mislabels → RAW-9 instead.
- Requiring `expected_review_revision`; widening `_state_stamps()` — both are
  adjudicated design decisions (spec §4.2; spec review rounds 2+3).
- Hardcoding `.venv/bin/python` in tests (breaks CI, no `.venv` there) and
  `-> None` annotations (nothing in this repo is annotated; no Ruff config).

## In flight
- WT=~/orca/workspaces/rawdog-printworks/plan2-printworks-app, branch
  johncioni/plan2-printworks-app. Ledger:
  $WT/.superpowers/sdd/2026-08-12-printworks-app/progress.md (task log +
  pre-flight table). All 11 briefs pre-generated alongside it.
- Task 1 COMPLETE (0bff85d, review clean); xcodegen 2.46.0 installed via brew.
  Plan 2 TASK 2 implementer RUNNING (contract models + fixture decoding).
  Check: `git -C $WT status --porcelain` and `git -C $WT log --oneline -3`.
- Carried rules (also in the ledger): any task editing `project.yml` must
  regenerate + commit the `.xcodeproj` in the SAME commit; Task 11's release
  script should pin an xcodebuild `-destination`; Tasks 8/9/10 have 23-25 line
  briefs, so their dispatches need spec §5-§8 pointers from me.
- NOTE: this hook fires every turn while a background implementer writes into
  that worktree — same repo, so HANDOFF is never the newest change.

## Next
1. Review Task 1 when its report lands, then Tasks 2-11 through the same loop
   (implementer → review-package → task reviewer → fix rounds → ledger line).
   Briefs come from the skill's `scripts/task-brief PLAN_FILE N`.
2. USER: enable swift-lsp — Tasks 2+ are all Swift and I cannot enable it.
3. RAW-4: branch protection on main (`pytest` is a real check now).
4. Low, unscheduled: RAW-9 (typed exceptions, start driver.py:277), RAW-7
   (`.casefold()` stems; "colliding Output trees" claim UNVERIFIED), RAW-8
   (hoist pp3 parses into `gather_material`), RAW-6 (face-detection fixture).
5. USER DECISION (non-urgent): the OLD json-interface worktree + branch remain
   at e7afc61; its `.superpowers/sdd/` ledger is the only record of how Plan 1
   ran, so keep it if that matters.
