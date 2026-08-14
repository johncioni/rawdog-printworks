# HANDOFF

## Goal
RAWdog Printworks. Plan 1 (pipeline JSON interface) is MERGED to main —
the pipeline exposes the additive `--json` NDJSON contract plus its golden
fixtures. Next substantive work is Plan 2, the macOS SwiftUI app (RAW-2).
Repo is wired to Orca + GitHub + Linear (team RAW) + CodeRabbit, with a CI
gate on every PR. main = 31bb770, tree clean, CI green, gate = 295 passing.

## Done
- PR #3 merged (356115c) as a MERGE COMMIT, keeping the 16 task commits.
  CodeRabbit APPROVED, 0 unresolved threads.
- CodeRabbit: 15 findings, all answered — 10 fixed, 5 dismissed with
  citations. Serious one: `ingest --from` could overwrite a different
  photo's RAW, because the stem check is case-sensitive but macOS volumes
  are not. Guarded at ingest.py:196; test verified red before green.
  Others: shared error adapters for `adjust`, collect-mode isolation
  widened to Exception, jsonio.deactivate() teardown, pp3 newline='',
  test_cli scoped to tmp_repo, staged-hash dedup test, ERROR_CODES +
  sidecar-deletion coverage, AssertionError stubs, E702 splits.
- Two read-only subagent re-audits, both after the merge: (A) confirmed
  the case collision was real, reproduced twice — APFS keeps the existing
  entry's case, so the victim file kept its name and got the other photo's
  bytes; unarchived victims are unrecoverable, archived ones survive.
  (B) upheld the status-stamp dismissal: display-only, no destructive
  path, since approve recomputes under the lock and fail-closes.
- Docs: CLAUDE.md refreshed for the landed interface (295-test gate, new
  subcommands, fixtures-are-authority note); Plan 1's approve-gate
  scoping wording made precise (20f79c2).
- Linear: RAW-1, RAW-5 Done. Open: RAW-2, RAW-4, RAW-6, RAW-7, RAW-8.

## Ruled out
- Squash-merging PR #3 — the 16 per-task commits are the record.
- Requiring `expected_review_revision`, and widening status stamps — both
  are adjudicated design decisions (spec §4.2; spec review rounds 2+3).
  Widening the stamp also only converts a tear into a retry, since
  `snapshot()` returns unconditionally at `attempt == 1` (status.py:98),
  while re-hashing every preview JPG per poll.
- Hardcoding `.venv/bin/python` in tests — would break CI, which has no
  `.venv`; `sys.executable` is already the interpreter under test.

## In flight
- Nothing running. Bots quiet; no background tasks or builds outstanding.

## Next
1. RAW-2 / Plan 2 (macOS app). `tests/fixtures/json_contract/` is the
   binding contract. Enable swift-lsp; `brew install xcodegen` in Task 1.
   Gates: `swift test` + `xcodebuild build` + visual QA screenshots.
2. RAW-4: branch protection on main — now enforceable, `pytest` is a real
   required check.
3. RAW-7 (low): `.casefold()` stems at ingest.py:70, :124, :172-173/190/198
   and render.py:91. The audit's "colliding Output trees" claim is
   UNVERIFIED — confirm before implementing.
4. RAW-8 (low): hoist pp3 parses into `gather_material` so `_control`
   reads from `material` — removes a duplicate read and closes the
   torn-read window. Do it when status.py is next touched.
5. USER DECISION (cleanup, non-urgent): the json-interface worktree and
   branch still exist, both at e7afc61 (merged). To remove:
   `git worktree remove --force .claude/worktrees/json-interface` &&
   `git branch -D worktree-json-interface` &&
   `git push origin --delete worktree-json-interface`. Its
   `.superpowers/sdd/` ledger is the Plan 1 execution record — deleting
   the worktree destroys it, so keep if that history matters.
6. Known limitation: the 16 Plan 1 commits are unsigned (1Password will
   not sign for agent-launched shells). The merge commit is GitHub-signed.
