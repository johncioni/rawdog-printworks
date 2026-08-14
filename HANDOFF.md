# HANDOFF

## Goal
RAWdog Printworks: BOTH implementation plans COMPLETE at rev 3.2
(b55aec8), Codex review loop CLOSED. AWAITING USER at the execution
gate: subagent-driven (recommended) vs inline; Plan 1 executes first
(its Task 13 fixtures gate Plan 2 Task 2). This session: /init only —
created repo CLAUDE.md.

## Done
- Orca ADE setup: wrote scripts/orca-setup.sh (idempotent worktree
  bootstrap: rebuilds stale/broken .venv, installs requirements-dev,
  collect-only smoke, warn-only tool checks); ran it here — it caught
  and fixed the main .venv's dead shebangs (venv was built at old
  path; 171 tests pass, pytest entry point works again). Also created
  .venv in the json-interface worktree (290 tests collect). Set Orca
  worktreeBaseRef=main (repo id b389b548-...). REMAINING (user, app
  UI): Orca repo settings → hooks → setup = "bash
  scripts/orca-setup.sh" (no CLI for hookSettings; UI drive attempt
  via orca computer didn't open settings, abandoned).
- Repo-move path fixes (~/photo-edits → ~/Projects/rawdog-printworks):
  repaired both git worktree gitdir pointers (worktree list now clean),
  updated python path in config/toolchain.lock (main + worktree;
  informational entry, not fingerprinted — approvals stand), updated
  app-default paths in Plan 2 + macOS app spec, fixed cd paths in
  worktree HANDOFF.md. Left alone: historical provenance.json,
  /Users/x placeholder in plan test example, worktree's committed doc
  copies (merge carries the fix). Verified: 171 tests pass, status OK.
- This session: created /Users/john/Projects/rawdog-printworks/CLAUDE.md
  (commands, state machine + fingerprint invariant, atomic publish,
  committed-vs-gitignored state, pointer to the two plans). Uncommitted.
- Offered /import of ~/.codex/config.toml and ~/.gemini/settings.json
  (user has not responded).
- Prior sessions: Plans docs/superpowers/plans/
  2026-08-12-pipeline-json-interface.md (13 tasks) +
  2026-08-12-printworks-app.md (11 tasks); review loop closed at rev
  3.2 (dispositions logged in Plan 1 "Review-round decisions").

## Ruled out
- Further verify rounds on the plans: remaining defects are covered by
  each task's failing-test cycle + per-task SDD reviewer.

## In flight
- Nothing running this session. Previously noted companion server port
  60219 (spec-ready screen); stop at execution start if unused
  (stop-server.sh .superpowers/brainstorm/22193-1786559112).

## Next
1. USER GATE (unchanged): execution choice — subagent-driven (Codex
   Sol 5.6 xhigh implements via codex-companion task --fresh, Fable
   reviews) vs inline executing-plans.
2. On go: superpowers:subagent-driven-development for Plan 1 —
   worktree via superpowers:using-git-worktrees,
   scripts/sdd-workspace <plan>, ledger, Task 1 dispatch.
3. Plan 2 after Plan 1 Task 13 (fixtures committed); enable swift-lsp
   then; brew install xcodegen happens in its Task 1.
4. Optionally commit CLAUDE.md (+ pending .gitignore/HANDOFF.md
   changes) when the user asks.
5. Quality gates: Plan 1 pytest suite; Plan 2 swift test + xcodebuild
   build + visual QA screenshots (done-criteria).
