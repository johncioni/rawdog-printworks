# HANDOFF

## Goal
RAWdog Printworks. Plan 1 (pipeline `--json`) is MERGED; its golden fixtures bind
Plan 2 — the macOS SwiftUI app (RAW-2), built in the Orca worktree. **Tasks 1-9
of 11 built**; Task 9's re-review is RUNNING. main = this checkpoint's own
commit, pushed; WT = e9a16e7.

## Done
- Tasks 1-5 clean. TASK 6 SHIPS (c36db76 + c4a10d1). Detail in the docs archive.
- TASK 7 COMPLETE after 3 rounds: 51f6fc6+bffbf56 built; c9165c2 fixed 3 Majors
  (⌘N/⌘W killed the watcher; `.id(hash)` was a cache key with NO cache;
  ingest-Retry escalated to `run --force`); 87511e8 bounded the cache that fix
  introduced; bf4cbd1 fixed the regression 87511e8 introduced.
- TASK 8 SHIPS e512205. I reported CompareView broken; the reviewer DISPROVED it
  in my own process (8/8 Space toggles). My error: unmodified keys route only to a
  KEY window while ⌘-keys go via the main menu — always pass `--restore-window`.
- TASK 9 BUILT e9a16e7 (CropOverlayView + InspectorView + 3 model behaviours,
  test-first) and CLOSED Task 8's M1 (14 accessibilityLabels) and M2
  (`AppModel.photos(inDeliveryOf:)` replacing 4 drifting copies).
- TASK 9 SMOKE PASSED on scratch (`qa/task-9-*.png`): overlay draws 8×10 solid +
  5×7 dashed inside the letterboxed rect, `c` toggles it; Approve correctly
  disabled. **Full mutate round-trip**: Warmth → `adjust` wrote ONLY pipeline-owned
  sidecar+recipe (none by the app), photo went verified → review_required, toolbar
  followed via the watcher.
- I VERIFY EVERY TASK MYSELF: gates by exit code + a mutation per new test (all
  went RED when reverted). Codex implements; I commit.
- CODEX SANDBOX FIXED (memory `codex-swift-sandbox-fix`): every Swift dispatch
  carries BOTH `--disable-sandbox` flags. DISPATCH IS ORCA (memory
  `orca-agent-dispatch`); briefs live in the LEDGER, never a session scratchpad.
- LESSONS: greps confirm the letter, READING the intent; a green suite proves
  what is TESTED not what is correct; `open` does NOT relaunch a running app;
  macOS AX intermittently blocks a fresh binary (retry, then ask for a toggle);
  Codex sometimes writes its report to the worktree ROOT.

## Ruled out
- Settled, don't reopen: Task 6's refresh gate (§7), `_state_stamps()` (§4.2).
- Deferred to whole-branch review: m6-m10, i11, i12, kqueue vs in-place edits,
  `Output/photos/<stem>/`, Task 8's N3/N5.
- Widening Codex's writable roots so it can commit — the controller committing
  AFTER verifying is the review gate. Keep it.
- Smoking mutating features against the real repo — user chose a scratch repo.
- Pinning main's sha here — the commit writing it invalidates it instantly.

## In flight
- TASK 9 RE-REVIEW RUNNING (Opus, `term_c901f413-…`), scope e512205..e9a16e7,
  brief `task-9-rereview-dispatch.md`. Watcher polls the ledger AND worktree root.
- **THE APP POINTS AT A SCRATCH REPO** `~/orca/workspaces/rawdog-printworks/
  smoke-repo` (clone + one photo's live data, 510M; python points at the real
  repo's .venv). Its dirty sidecar/recipe is my slider-test evidence. RESTORE
  WHEN PLAN 2 ENDS: `defaults delete com.john.rawdog-printworks repoPath` and
  `… pythonPath`, then delete smoke-repo.
- WT=~/orca/workspaces/.../plan2-printworks-app (HEAD e9a16e7). Ledger gitignored,
  ARCHIVED through Task 8 (+qa/) to docs/superpowers/sdd-archive/; Task 9 not yet.

## Next
1. On the re-review: fix round via the Orca loop, else Task 10 (Settings scene).
   Brief 10 is 23-25 lines and needs spec §5-§8, the AppModel surface, Tasks
   7-9's view files, the sandbox flags, and i12 ("Open Settings" is dead today).
2. Task 11 pins a `-destination`. Refresh the docs archive at the end.
