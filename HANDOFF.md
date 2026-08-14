# HANDOFF

## Goal
RAWdog Printworks. Plan 1 (pipeline `--json` interface) is MERGED; its
golden fixtures in `tests/fixtures/json_contract/` bind Plan 2 — the macOS
SwiftUI app (RAW-2), the next work. Orca + GitHub + Linear (RAW) +
CodeRabbit, CI per PR. main = 0e3749b, CI green, 296 tests pass.

## Done
- PR #3 merged (356115c) as a MERGE COMMIT, keeping all 16 task commits.
  CodeRabbit: 15 findings — 10 fixed, 5 dismissed with citations. Serious
  one: `ingest --from` could overwrite a different photo's RAW (stem check
  case-sensitive, macOS volumes are not); guarded at ingest.py:196.
- PR #4 merged (4f190e4): clamp `failed[].code` to `jsonio.ERROR_CODES`.
  Those dicts are hand-built, so they bypass `CommandError.__init__`'s
  check and could emit an out-of-contract code. Plus an
  `isinstance(code, str)` guard — ERROR_CODES is a frozenset, so an
  unhashable `.code` raised TypeError *inside* the handler, aborting the
  batch the isolation protects. Both verified red before green.
- Post-merge re-audits upheld both major dismissals, reproduced the ingest
  bug twice, and ruled out golden-fixture drift (no adjust *error* fixture
  exists; run_partial_failure's VERIFY_FAILED is appended by
  `_finish_verified`, which returns False rather than raising).
- Linear: RAW-1, RAW-5 Done. Open: RAW-2, RAW-4, RAW-6..RAW-10.

## Ruled out
- Squash-merging PR #3 — the 16 per-task commits are the record.
- Mapping bare RuntimeError to an operational code — driver.py also uses
  it for internal invariants (:557 "audit before approval"), so a blanket
  map mislabels. Typed exceptions at the source instead → RAW-9.
- Requiring `expected_review_revision`, and widening `_state_stamps()` —
  adjudicated design decisions (spec §4.2; spec review rounds 2+3).
- Hardcoding `.venv/bin/python` in tests (breaks CI, which has no `.venv`)
  and adding `-> None` annotations (nothing in this repo is annotated, and
  there is no Ruff config, so ANN/TRY rules are advisory not policy).

## In flight
- PLAN 2 RUN STARTED (subagent-driven). Orca worktree
  ~/orca/workspaces/rawdog-printworks/plan2-printworks-app, branch
  johncioni/plan2-printworks-app from 60facc9, venv provisioned by the setup
  hook (295 pass / 1 skip). Ledger + pre-flight scan:
  <worktree>/.superpowers/sdd/2026-08-12-printworks-app/progress.md.
  RAW-10 implementer dispatched and mid-flight (3 expected files dirty, not
  yet committed). Check: `git -C <worktree> log --oneline -3`.

## Next
1. RAW-2 / Plan 2 (macOS app). Enable swift-lsp; `brew install xcodegen`
   in its Task 1. Gates: `swift test` + `xcodebuild build` + visual QA.
   Do RAW-10 first: `failed[].code` is the whole ERROR_CODES set, but the
   only fixtures showing it pin one value — a decoder built from them
   would be too narrow.
2. RAW-4: branch protection on main (`pytest` is a real check now).
3. RAW-9 (low): typed exceptions for operational RuntimeErrors, starting
   at driver.py:277 — MANUAL_ASSETS_ERROR is matched by string equality in
   the collect handler, so editing that message silently breaks the skip.
4. Low, unscheduled: RAW-7 (`.casefold()` stems; its "colliding Output
   trees" claim is UNVERIFIED), RAW-8 (hoist pp3 parses into
   `gather_material`), RAW-6 (committed face-detection fixture).
5. USER DECISION (non-urgent): json-interface worktree + branch remain at
   e7afc61. `git worktree remove --force .claude/worktrees/json-interface`
   && `git branch -D worktree-json-interface` && `git push origin --delete
   worktree-json-interface` — but its `.superpowers/sdd/` ledger is the
   only record of how Plan 1 ran, so keep it if that matters.
