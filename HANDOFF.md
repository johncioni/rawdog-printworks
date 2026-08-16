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
- TASK 10 BUILT de1e774: IngestBanner, SettingsSheet (live 600ms-debounced
  validation, closes i12), publish notifications, pendingInputFiles/ingestPending
  test-first, and carry-forward m11 — the "8 concurrent crops" bound counted map
  entries, not running subprocesses (measured 8/16/24/32 across revision waves);
  the superseded task is now cancelled. 80 tests.
- TASK 10 SMOKE PASSED on the scratch repo (`qa/task-10-*.png`): ⌘, opens
  Settings; a bogus repo path shows `could not launch: …doesn't exist` inline and
  DISABLES Save; restoring a valid path clears it and re-enables Save; dropping a
  RAW into scratch `Input/` raised "1 new RAW file — Ingest now?" via the watcher,
  and removing it cleared the banner. I did NOT click Ingest (22 renders).
- TASK 9 SMOKE (earlier) verified the **full mutate round-trip**: Warmth →
  `adjust` wrote ONLY pipeline-owned sidecar+recipe (none by the app), photo went
  verified → review_required, toolbar followed via the watcher.
- **CORRECTION — the screen lock was NOT why drags failed.** With the screen
  confirmed unlocked (`locked: False`, `onconsole: True`) the splitter control
  STILL does not move, while clicks/keys/AX/`set-value` all work. So
  `orca computer drag` does not drive SwiftUI drag gestures at all. M1's crop-drag
  fix is therefore verified ONLY by the reviewer's probe (which called
  mouseDown/Dragged/Up directly on the NSHostingView, with a harness control and
  the pre-fix chain reproducing the bug). A 10-second manual check would settle it.
- I VERIFY EVERY TASK MYSELF: gates by exit code + a mutation per new test. NOTE:
  m11's test fails by HANGING (8min+) not asserting — flagged for review.
- CODEX SANDBOX FIXED + DISPATCH IS ORCA (memories `codex-swift-sandbox-fix`,
  `orca-agent-dispatch`): both `--disable-sandbox` flags every time; briefs in the
  LEDGER. Verify the agent UI is up and the prompt TOOK (context>0) before trusting
  `send` — a lost prompt once went to a bare zsh after Codex exited.
- LESSONS: greps confirm the letter, READING the intent; a green suite proves what
  is TESTED not what is correct; `open` does NOT relaunch a running app; a
  mutation whose test can HANG must restore the file independently of the test
  finishing (a timeout once left my mutant in the tree).

## Ruled out
- Settled, don't reopen: Task 6's refresh gate (§7), `_state_stamps()` (§4.2).
- Deferred to whole-branch review: m6-m10, i11, kqueue vs in-place edits,
  `Output/photos/<stem>/`, Task 8's N3/N5, Task 9's n13-n16.
- Widening Codex's writable roots so it can commit — controller-commits-after-
  verifying IS the review gate.
- Smoking mutating features against the real repo — user chose a scratch repo.
- Pinning main's sha here — the commit writing it invalidates it instantly.

## In flight
- Nothing running. Task 10's re-review is NOT yet dispatched.
- **THE APP POINTS AT THE SCRATCH REPO** `~/orca/workspaces/rawdog-printworks/
  smoke-repo`; its 2 dirty files are my slider-test evidence. RESTORE AT THE END:
  `defaults delete com.john.rawdog-printworks repoPath` / `… pythonPath`, then
  delete smoke-repo.
- WT (HEAD de1e774). Ledger gitignored; ARCHIVED through Task 9 + qa/ to
  docs/superpowers/sdd-archive/; Task 10's ledger files not yet archived.

## Next
1. Dispatch Task 10's re-review (scope e9a16e7..de1e774) per the Orca method —
   flag m11's hang-on-failure and the notification/subprocess-cancel additions.
2. Then Task 11: visual QA. It must pin a `-destination`; the screen is unlocked
   now so AX/screenshots work, but drags still are not drivable.
3. At the end: restore defaults, delete smoke-repo, refresh the docs archive.
