# HANDOFF

## Goal
RAWdog Printworks. Plan 1 (pipeline `--json`) is MERGED; its golden fixtures bind
Plan 2 — the macOS SwiftUI app (RAW-2), built in the Orca worktree. **Tasks 1-10
of 11 built; 1-9 SHIPPED through review.** main = this checkpoint's own commit,
pushed; WT = de1e774.

## Done
- TASKS 1-9 SHIP. Detail in the docs archive; the load-bearing bits: Task 7 took
  3 rounds (⌘N/⌘W killed the watcher; `.id(hash)` was a cache key with NO cache;
  ingest-Retry escalated to `run --force`; then its own cache fix was unbounded,
  then that fix regressed failure-clearing). Task 8: I called CompareView broken,
  the reviewer disproved it in my own process. Task 9: the crop hit region was the
  whole canvas — 8×10 undraggable, letterbox drags nudged 5×7 into the draft.
- TASK 10 BUILT de1e774: IngestBanner, SettingsSheet (live validation, closes
  i12), publish notifications, pendingInputFiles/ingestPending test-first, and
  carry-forward m11 (the "8 concurrent crops" bound counted map entries, not
  running subprocesses — measured 8/16/24/32 across revision waves). 80 tests.
- TASK 9 SMOKE PASSED on scratch: overlay draws correctly; **full mutate
  round-trip** — Warmth → `adjust` wrote ONLY pipeline-owned sidecar+recipe (none
  by the app), photo went verified → review_required, toolbar followed.
- **THE SCREEN IS LOCKED** (`CGSSessionScreenIsLocked`), so WindowServer delivers
  no synthesized mouse events — that is why EVERY drag/AX smoke came back vacuous
  (my splitter control stayed at 250). The reviewer verified M1 anyway by calling
  `mouseDown/Dragged/Up` directly on the NSHostingView. UNLOCK BEFORE TASK 11 QA.
- I VERIFY EVERY TASK MYSELF: gates by exit code + a mutation per new test.
  Codex implements; I commit. NOTE: m11's test fails by HANGING (8min+) rather
  than asserting — flagged for review; a CI regression there would stall.
- CODEX SANDBOX FIXED + DISPATCH IS ORCA (memories `codex-swift-sandbox-fix`,
  `orca-agent-dispatch`): both `--disable-sandbox` flags every time; briefs in the
  LEDGER. Verify the agent UI is up and the prompt TOOK (context>0) before trusting
  `send` — a lost prompt once went to a bare zsh after Codex exited.
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
