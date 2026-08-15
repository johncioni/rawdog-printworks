# HANDOFF

## Goal
RAWdog Printworks. Plan 1 (pipeline `--json`) is MERGED; its golden fixtures are
the binding contract. NOW EXECUTING Plan 2 — the macOS SwiftUI app (RAW-2) in the
Orca worktree. **Tasks 1-6 of 11 are COMPLETE and re-reviewed; Task 7 is next.**
main = this checkpoint's own commit, pushed; WT = c4a10d1.

## Done
- Tasks 1-4 clean (0bff85d, 3378ea9, e47ad9c, 3dc7904); Task 5 AppModel 532c311
  + 7e19bee "ship it"; F2-mirror gap closed 3212f6c. Detail in the WT ledger.
- TASK 6 SHIPS. Fix round 1 = c36db76 (Codex, all 7 findings) + c4a10d1 (MY test
  rewrite). Re-review `task-6-rereview.md`: SPEC ✅, QUALITY ships, no Critical,
  no Important blocker. It re-derived the mutation matrix from scratch rather
  than inheriting the [claimed] evidence — 20 mutants, 19 killed.
- MY ADJUDICATION UPHELD but MIS-STATED — correct it wherever repeated. Late-not-
  lost is real (reviewer reproduced at load ~300: 0 at 350ms, delivery 11ms
  later). But "bounded by `maxCoalesceWait` 2s" is WRONG: that bounds the
  scheduled deadline, not delivery (`.utility` queue + actor hop slip without
  bound). Honest form: "never lost; late by an unbounded amount". And "never
  lost" covers scheduling only — M2 is a real drop path. c4a10d1's msg repeats it.
- The two `#if DEBUG` seams: ACCEPTED (internal, absent from Release; I3+M6 are
  only testable because of them). Caveat: `swift test -c release` won't compile.
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
- Nothing running. WT=~/orca/workspaces/.../plan2-printworks-app (HEAD c4a10d1);
  ledger $WT/.superpowers/sdd/2026-08-12-printworks-app/ is GITIGNORED, so the
  review, the reconstruction and the briefs exist on disk only.
- Reviewer terminal left open for scrollback: term_403cb16f-3eb6-492e-843f-
  34a2d1ba5b5d (finished, 58m, $7.11). Close with `orca terminal close`.

## Next
1. Write Task 7's dispatch INTO THE LEDGER from task-7-brief.md, folding in the
   re-review's carry-forwards: **P1** (pin the coalesce *window* — expose
   `effectiveCoalesceDelay` and assert 0.5 / injected 0.2; config not timing, so
   it cannot flake; today `coalesce-10x` survives and a 500ms→5s slip keeps all
   58 tests green) plus **M1-M4** (see `task-6-rereview.md` for each).
2. Dispatch it per the Orca method above. Tasks 8/9/10 briefs are 23-25 lines and
   need spec §5-§8, the AppModel surface, Task 7's view files, the sandbox flags.
   Task 11 pins `-destination`.
