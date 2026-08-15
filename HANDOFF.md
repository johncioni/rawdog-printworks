# HANDOFF

## Goal
RAWdog Printworks. Plan 1 (pipeline `--json`) is MERGED; its golden fixtures are
the binding contract. NOW EXECUTING Plan 2 — the macOS SwiftUI app (RAW-2) in the
Orca worktree. Tasks 1-6/11 implemented; Task 6 is COMMITTED and green, awaiting
only its re-review. main = this checkpoint's own commit, pushed; WT = c4a10d1.

## Done
- Tasks 1-4 clean (0bff85d, 3378ea9, e47ad9c, 3dc7904); Task 5 AppModel 532c311
  + 7e19bee "ship it". Detail in the WT ledger.
- F2-MIRROR GAP CLOSED (3212f6c, TDD). The ledger's one-liner does NOT work — as
  `Int?` that compare is always true when captured idle; `commandGeneration` had
  to become non-optional.
- TASK 6 FIX ROUND COMMITTED as two commits, split for authorship: c36db76 =
  Codex's fix for all 7 findings; c4a10d1 = MY test rewrite. Re-review both.
- Gate round 1 failed 1/25 at loadavg 150. ADJUDICATED A TEST DEFECT, NOT A
  PRODUCT BUG: `pendingChange` stays true and the newest work item holds the
  current generation, so an emission is only LATE (≤2s), never lost; the test
  budgeted 350ms. Rewrote it + mutation-checked (30≠0,30≠1,31≠1). Round 2 25/25.
- CODEX SANDBOX FIXED — supersedes "Codex cannot run xcodebuild". Memory
  `codex-swift-sandbox-fix`. EVERY Swift dispatch carries BOTH flags: `swift
  build/test --disable-sandbox`, `xcodebuild OTHER_SWIFT_FLAGS='-disable-sandbox'`.
- DISPATCH REWRITTEN FOR ORCA (memory `orca-agent-dispatch`): `orca terminal
  create --worktree name:<wt> --command '<agent>'` + `terminal send/wait/read`.
  Briefs go in the LEDGER, never the scratchpad — that killed Task 7's prompt.
- CLEANUP DONE: removed the merged `json-interface` worktree + local/remote branch
  (e7afc61) and merged branches 1bfe1e1, e112c86, efbdbc0; pushed main. Live data
  intact (Input 120M, Output 951M, archive 79M).
- SWIFT-LSP RESOLVED: from spec ab46d02's setup checklist. `sourcekit-lsp` exists
  in the Xcode toolchain, nothing configured. RECOMMENDED TO DROP — the sandbox
  fix gives stronger signal. Awaiting user yes/no.

## Ruled out
- Settled, don't reopen: Task 6's refresh gate (§7), `_state_stamps()` (§4.2).
- Two Task 6 minors (kqueue blind to in-place edits; `Output/photos/<stem>/`
  unwatched) — deferred to whole-branch review.
- Redirecting Xcode caches to /tmp — the manifest cache is not redirectable.
- `danger-full-access` for Codex — would expose the main repo's live photo data.
- Chasing the 1/25 flake by repro — 0/20 in isolation; read the code instead.
- Inline-vs-subagent for the re-review — moot; dispatches via Orca now.
- Pinning main's sha in this file — the writing commit invalidates it instantly.

## In flight
- WT=~/orca/workspaces/rawdog-printworks/plan2-printworks-app (HEAD c4a10d1,
  branch johncioni/…). Ledger: $WT/.superpowers/sdd/2026-08-12-printworks-app/
- Nothing running. Gate logs + re-runnable script: <scratchpad>/under-load-gate*
- `task-6-fix-round-1.md` is a controller RECONSTRUCTION, claims tagged [claimed]
  vs [verified]. It and the brief exist on disk only (`.superpowers/` ignored).

## Next
1. Launch re-review: `orca terminal create --worktree name:plan2-printworks-app
   --command 'claude --model claude-opus-5'`, then send task-6-rereview-dispatch.md
2. Then Task 7 (rewrite its dispatch from task-7-brief.md into the ledger);
   Tasks 8/9/10 dispatches add spec §5-§8, AppModel surface, Task 7's view
   files, sandbox flags. Task 11 pins `-destination`.
3. OPEN FOR USER: swift-lsp drop-or-wire; and whether to finish diagnosing the
   claude-hud statusline flagging context-mode (ctx_doctor is fully green, and
   /mcp showed it had reconnected — likely a stale past-disconnect indicator).
