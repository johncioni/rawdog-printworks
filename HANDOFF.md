# HANDOFF

## Goal
RAWdog Printworks. Plan 1 (pipeline `--json` interface) is MERGED; its
golden fixtures in `tests/fixtures/json_contract/` are the binding
contract for Plan 2, the macOS SwiftUI app (RAW-2) — the next work.
Repo is wired to Orca + GitHub + Linear (team RAW) + CodeRabbit with a CI
gate on every PR. main = 6ef71b2, tree clean, CI green, 295 tests pass.

## Done
- PR #3 merged (356115c) as a MERGE COMMIT, keeping all 16 task commits.
  CodeRabbit APPROVED, 0 unresolved threads.
- CodeRabbit: 15 findings, all answered — 10 fixed, 5 dismissed with
  citations. The serious one: `ingest --from` could overwrite a different
  photo's RAW (stem check is case-sensitive, macOS volumes are not);
  guarded at ingest.py:196, test verified red before green. Also: shared
  error adapters for `adjust`, collect isolation widened to Exception,
  jsonio.deactivate() teardown, pp3 `newline=''`, test_cli scoped to
  tmp_repo, staged-hash dedup test, ERROR_CODES + sidecar-deletion tests.
- Post-merge re-audits (read-only subagents) upheld both major
  dismissals; one reproduced the ingest bug twice. Golden-fixture drift
  ruled out for both error-path changes: no adjust *error* fixture
  exists, run_partial_failure's VERIFY_FAILED comes from driver.py:644,
  and `CommandError` (plain Exception) was previously not caught at all.
- Docs: CLAUDE.md refreshed for the landed interface; Plan 1 approve-gate
  wording made precise (20f79c2).
- Linear: RAW-1, RAW-5 Done. Open: RAW-2, RAW-4, RAW-6, RAW-7, RAW-8.

## Ruled out
- Squash-merging PR #3 — the 16 per-task commits are the record.
- Requiring `expected_review_revision`, and widening `_state_stamps()` —
  adjudicated design decisions (spec §4.2; spec review rounds 2+3).
  Widening also only converts a tear into a retry, since `snapshot()`
  returns unconditionally at `attempt == 1` (status.py:98).
- Hardcoding `.venv/bin/python` in tests — breaks CI, which has no
  `.venv`; `sys.executable` is already the interpreter under test.

## In flight
- Nothing running. Bots quiet, no background builds or tasks outstanding.

## Next
1. RAW-2 / Plan 2 (macOS app). Enable swift-lsp; `brew install xcodegen`
   in its Task 1. Gates: `swift test` + `xcodebuild build` + visual QA.
2. RAW-4: branch protection on main — now enforceable, `pytest` is a real
   required check.
3. RAW-7 (low): `.casefold()` stems at ingest.py:70, :124, :172-173/190/
   198 and render.py:91. Its "colliding Output trees" claim is UNVERIFIED
   — confirm before implementing.
4. RAW-8 (low): hoist pp3 parses into `gather_material` so `_control`
   reads from `material`; removes a duplicate read and closes the
   torn-read window. Do it when status.py is next touched.
5. USER DECISION (cleanup, non-urgent): the json-interface worktree and
   branch still exist, both at e7afc61 (merged):
   `git worktree remove --force .claude/worktrees/json-interface` &&
   `git branch -D worktree-json-interface` &&
   `git push origin --delete worktree-json-interface`
   Its `.superpowers/sdd/` ledger is the only record of how Plan 1 was
   executed — removing the worktree destroys it. Keep if that matters.
6. Known limitation: the 16 Plan 1 commits are unsigned (1Password will
   not sign for agent-launched shells); the merge commit is GitHub-signed.
