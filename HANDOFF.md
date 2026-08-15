# HANDOFF

## Goal
RAWdog Printworks. Plan 1 (pipeline `--json`) is MERGED; its golden fixtures are
the binding contract. NOW EXECUTING Plan 2 — the macOS SwiftUI app (RAW-2) in the
Orca worktree. **Tasks 1-6 of 11 COMPLETE and re-reviewed; TASK 7 IS RUNNING.**
main = this checkpoint's own commit, pushed; WT = c4a10d1.

## Done
- Tasks 1-4 clean (0bff85d, 3378ea9, e47ad9c, 3dc7904); Task 5 AppModel 532c311
  + 7e19bee "ship it"; F2-mirror gap closed 3212f6c. Detail in the WT ledger.
- TASK 6 SHIPS: c36db76 (Codex, all 7 findings) + c4a10d1 (MY test rewrite);
  re-review SPEC ✅ / ships, 20 mutants re-derived, 19 killed. `#if DEBUG` seams
  ACCEPTED (caveat: `swift test -c release` won't compile the test target).
- MY ADJUDICATION UPHELD but MIS-STATED — correct wherever repeated. Late-not-lost
  is real (reproduced at load ~300). But "bounded by `maxCoalesceWait` 2s" is
  WRONG — that bounds the scheduled deadline, not delivery; and "never lost"
  covers scheduling only (M2 is a real drop path). c4a10d1's msg repeats the error.
- CODEX SANDBOX FIXED (memory `codex-swift-sandbox-fix`). EVERY Swift dispatch
  carries BOTH flags: `swift build/test --disable-sandbox`, `xcodebuild
  OTHER_SWIFT_FLAGS='-disable-sandbox'`.
- DISPATCH IS ORCA NOW (memory `orca-agent-dispatch`): `orca terminal create
  --worktree name:<wt> --command '<agent>'` + `terminal send --text ... --enter`
  / `wait --terminal <h> --for tui-idle` / `read`. Briefs go in the LEDGER, never
  the scratchpad — that is what destroyed Task 7's original prompt.
- CLEANUP DONE: merged `json-interface` worktree + local/remote branch removed
  (e7afc61), merged branches 1bfe1e1/e112c86/efbdbc0 deleted, main pushed. Live
  photo data verified intact. SWIFT-LSP DROPPED by user — do not reintroduce.

## Ruled out
- Settled, don't reopen: Task 6's refresh gate (§7), `_state_stamps()` (§4.2).
- Two original-review minors (kqueue blind to in-place edits; `Output/photos/
  <stem>/` unwatched) — still deferred to the whole-branch review.
- Redirecting Xcode caches to /tmp — the manifest cache is not redirectable.
- `danger-full-access` for Codex — would expose the main repo's live photo data.
- Fix round 2 for Task 6 — reviewer's call and mine: carry P1+M1-M4 into Task 7.
- Pinning main's sha here — the commit writing it invalidates it instantly.

## In flight
- TASK 7 DISPATCHED to Codex (gpt-5.6-sol xhigh) via Orca terminal
  `term_a5d7f539-e1da-4c1e-98c3-8193e8e8aa2c`, brief `task-7-dispatch.md`. Two
  commits expected: A = P1/M1-M4 core cleanup, B = shell UI. A background
  watcher polls for `task-7-report.md` (100min cap).
- WT=~/orca/workspaces/.../plan2-printworks-app (HEAD c4a10d1); ledger
  $WT/.superpowers/sdd/2026-08-12-printworks-app/ is GITIGNORED but now ARCHIVED
  through Task 6 to `docs/superpowers/sdd-archive/2026-08-12-printworks-app/`
  (f8546a4, on origin). Task 7's files are NOT yet archived.
- Finished reviewer terminal left open for scrollback: term_403cb16f-…-34a2d1ba5b5d

## Next
1. When `task-7-report.md` lands: verify BOTH gates myself (exit code, not grep)
   and that commit A really kills the `coalesce-10x` mutant, then REVIEW the diff
   (Opus). Codex implements, I review — user re-confirmed 2026-08-15.
2. Then Step 3 IS MINE, not Codex's: smoke the built app with computer-use —
   grid shows P1036163/P1036170 Published, sidebar has the "Earlier" group.
   Screenshot for Task 11's QA set. A green build is not this claim.
3. Then Task 8. Briefs 8/9/10 are 23-25 lines and need spec §5-§8, the AppModel
   surface, Task 7's view files, the sandbox flags. Task 11 pins `-destination`.
   Refresh the docs/ archive when Plan 2 completes.
