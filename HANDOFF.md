# HANDOFF

## Goal
RAWdog Printworks. Plan 1 (pipeline `--json`) is MERGED; its golden fixtures bind
Plan 2 — the macOS SwiftUI app (RAW-2), built in the Orca worktree. **Tasks 1-9
of 11 built**; Task 9's re-review is RUNNING. main = this checkpoint's own
commit, pushed; WT = e9a16e7.

## Done
- Tasks 1-5 clean. TASK 6 SHIPS (c36db76 + c4a10d1). Detail in the docs archive.
- TASK 7 COMPLETE after 3 review rounds: 51f6fc6+bffbf56 built; c9165c2 fixed 3
  Majors (⌘N/⌘W killed the shared watcher; `.id(hash)` was a cache key with NO
  cache; ingest-Retry escalated to whole-repo `run --force`); 87511e8 bounded the
  cache that fix introduced; bf4cbd1 fixed the regression 87511e8 introduced.
- TASK 8 SHIPS e512205 (ReviewView + CompareView). I reported CompareView as
  broken; THE REVIEWER DISPROVED IT in my own process (8/8 clean Space toggles).
  My error: unmodified keys (space, ←, →) only route to a KEY window, ⌘-keys go
  via the main menu — so "⌘1-4 work therefore it isn't focus" was wrong. Always
  pass `--restore-window`. Its real finding: controls were NAMELESS in the AX
  tree, which is what made index-based clicking guesswork.
- TASK 9 BUILT e9a16e7 (CropOverlayView + InspectorView + 3 model behaviours,
  test-first) and CLOSED Task 8's M1 (14 accessibilityLabels) and M2
  (`AppModel.photos(inDeliveryOf:)` replacing 4 drifting copies).
- TASK 9 SMOKE PASSED on the scratch repo (`qa/task-9-*.png`): overlay draws 8×10
  solid + 5×7 dashed inside the letterboxed rect, `c` toggles it; inspector
  complete, Approve correctly disabled. **Full mutate round-trip verified**:
  Warmth slider → `adjust` wrote ONLY `sidecars/*.pp3` + `recipes/*.yaml` (both
  pipeline-owned, none by the app process), photo went verified →
  review_required, toolbar updated to "1 needs review" via the watcher.
- I VERIFY EVERY TASK MYSELF: gates by exit code + a mutation per new test. All
  have gone RED when reverted. Codex implements; I commit (its sandbox can't
  write a linked worktree's .git — that gate is deliberate, see Ruled out).
- CODEX SANDBOX FIXED (memory `codex-swift-sandbox-fix`): every Swift dispatch
  carries BOTH `--disable-sandbox` flags. DISPATCH IS ORCA (memory
  `orca-agent-dispatch`); briefs live in the LEDGER, never a session scratchpad.
- LESSONS: greps confirm the letter, READING the intent; a green suite proves
  what is TESTED not what is correct; `open` does NOT relaunch a running app
  (check binary mtime vs process start); macOS Accessibility intermittently
  blocks a freshly built binary — retry, then ask the user to toggle Orca
  Computer Use; Codex sometimes writes its report to the worktree ROOT.

## Ruled out
- Settled, don't reopen: Task 6's refresh gate (§7), `_state_stamps()` (§4.2).
- Deferred to whole-branch review: m6-m10, i11, i12, kqueue vs in-place edits,
  `Output/photos/<stem>/`, and Task 8's N3/N5 nits.
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
- WT=~/orca/workspaces/.../plan2-printworks-app (HEAD e9a16e7). Ledger gitignored
  but ARCHIVED through Task 8 (+ qa/) to docs/superpowers/sdd-archive/ on origin;
  Task 9's ledger files are NOT yet archived.

## Next
1. On the re-review: fix round via the Orca loop, else Task 10 (Settings scene).
   Brief 10 is 23-25 lines and needs spec §5-§8, the AppModel surface, Tasks
   7-9's view files, the sandbox flags, and i12 ("Open Settings" is dead today).
2. Task 11 pins a `-destination`. Refresh the docs archive at the end.
