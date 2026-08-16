# Task 10 re-review — dispatch

Reviewer: Opus 5 xhigh. Scope: **`e9a16e7..de1e774`** (Task 9's fix round is
already reviewed and shipped; the new work is `de1e774`).
Read `task-10-brief.md`, `task-10-dispatch.md`, `task-10-report.md`, and
`task-9-fix-round-1-rereview.md` §3 (m11 and the nits this commit was to close).

## Controller verification already done

- `swift test --disable-sandbox` → exit 0, **80** tests (+5). `xcodebuild` → exit 0.
- **m11 mutation, re-run by me:** removing `pending.task.cancel()` makes
  `testCropsStayAtEightAcrossRevisionChurn` **hang past 8 minutes** where the
  fixed code passes in **0.012 s**.
- **SMOKE PASSED on the scratch repo** (`qa/task-10-settings-invalid.png`,
  `qa/task-10-ingest-banner.png`): ⌘, opens Settings; a bogus repo path shows
  `could not launch: The file "bogus-repo-path" doesn't exist.` inline and
  DISABLES Save; restoring a valid path clears the error and re-enables Save;
  dropping a RAW into scratch `Input/` raised "1 new RAW file — Ingest now?" via
  the watcher, and removing it cleared the banner. I did not click Ingest.

## Your focus

1. **m11's test fails by HANGING, not asserting** (8min+ vs 0.012s). Is that
   inherent to asserting peak concurrency, or fixable? A regression here would
   stall CI rather than fail fast, and a hang is a poor signal for the next
   person. Say whether it should be restructured.
2. **`testCancellingRunTerminatesTheSubprocess` in `PipelineClientTests`** — the
   implementer added this beyond the brief, which implies cancelling a Swift
   `Task` was NOT killing the python subprocess. Verify the fix is real and
   complete: is every spawn path covered, is the process reaped (no zombies), and
   can a cancelled `crops`/`run` leave an orphan holding the driver lock?
   **This one matters most** — an orphaned mutating subprocess against a real repo
   is the worst failure mode this app has.
3. **Settings correctness beyond the happy path**: tilde expansion via
   `NSString.expandingTildeInPath` (both defaults ship with `~`), the 600 ms
   debounce, Save gated on the *current* pair validating, and whether saving
   genuinely rebuilds BOTH client and watcher (a stale watcher on the old repo
   would be silent and nasty).
4. **Notifications**: authorization requested once, refusal ignored silently, and
   nothing fires on a `RunResult` with no `published` entries.
5. **`pendingInputFiles`**: case-sensitivity (`.rw2` vs `.RW2`), and that it does
   not list stems already in the snapshot.
6. Whether Task 10 **broke** anything in Tasks 7-9, and whether n14/n15/n16 were
   actually closed (n13 was a judgement call — the report should say what it chose).

## Out of scope

Everything previously deferred: m6-m10, i11, Task 8's N3/N5, kqueue vs in-place
edits, `Output/photos/<stem>/`, the Task 5 refresh gate. Task 11 is visual QA.

## Environment notes

The app is pointed at the scratch repo `~/orca/workspaces/rawdog-printworks/
smoke-repo` — do NOT point anything at `~/Projects/rawdog-printworks`, which
holds irreplaceable photo data. The screen is now UNLOCKED, so AX reads,
clicks, keys and `set-value` work; **`orca computer drag` still does not drive
SwiftUI drag gestures** (verified: the splitter control does not move even
unlocked), so use your direct-hosting-view technique if you need a drag.

## Output

Write `task-10-rereview.md` **in this ledger directory**. Severity-ordered
findings with file:line and a concrete failure scenario, and a plain statement of
whether Task 10 ships.
