# HANDOFF

## Goal
RAWdog Printworks. Plan 1 (pipeline `--json`) is MERGED; its golden fixtures bind
Plan 2 — the macOS SwiftUI app (RAW-2), built in the Orca worktree. **Tasks 1-8
of 11 built**; Task 8's re-review is RUNNING. main = this checkpoint's own
commit, pushed; WT = e512205.

## Done
- Tasks 1-5 clean (0bff85d, 3378ea9, e47ad9c, 3dc7904, 532c311+7e19bee, 3212f6c).
- TASK 6 SHIPS: c36db76 + c4a10d1. (My "bounded by `maxCoalesceWait` 2s" phrasing
  was WRONG — it bounds the scheduled deadline, not delivery; see archive README.)
- TASK 7 COMPLETE after 3 review rounds: 51f6fc6+bffbf56 built; c9165c2 fixed 3
  Majors (⌘N/⌘W killed the shared watcher; `.id(hash)` was a cache key with NO
  cache; ingest-Retry escalated to whole-repo `run --force`); 87511e8 bounded the
  cache that fix introduced; bf4cbd1 fixed the regression 87511e8 introduced.
- TASK 8 BUILT e512205: ReviewView + CompareView, ReviewScreen stub replaced.
  `rerenderPreview` already existed (Task 5) so it added only the 2 required
  tests. Verified: 66 tests exit 0, xcodebuild exit 0, and the shared-rebase test
  goes RED against a parallel-copy rebase (mutation re-run by me).
- TASK 8 SMOKE — passed except one: double-click opens review, ⌘1-⌘3 switch style
  AND the canvas changes (83.7 mean abs pixel diff), the "Preview out of date"
  chip appears, sidebar thumbs correct. FAILED: **CompareView never opened** in 4
  attempts (Space ×2, button by index, button by coordinate). NOT just focus —
  ⌘1-⌘4 worked from that same focus state and the button click also did nothing.
- CODEX SANDBOX FIXED (memory `codex-swift-sandbox-fix`): EVERY Swift dispatch
  carries BOTH `--disable-sandbox` flags (swift + xcodebuild OTHER_SWIFT_FLAGS).
- DISPATCH IS ORCA (memory `orca-agent-dispatch`): `terminal create --worktree
  name:<wt> --command '<agent>'` + `send/wait/read`. Briefs live in the LEDGER.
- VERIFICATION LESSONS: greps confirm the letter, READING the intent (a grep for
  the hash key missed that no cache sat behind it); a green suite proves what is
  TESTED not what is correct (62/62 passed over the bf4cbd1 regression); `open`
  does NOT relaunch a running app — check binary mtime vs process start; Codex
  writes its report to the worktree ROOT; macOS Accessibility re-blocks each new
  binary and the USER must toggle Orca Computer Use before a smoke.
- Stale worktree/branches cleaned; live photo data intact. SWIFT-LSP DROPPED.

## Ruled out
- Settled, don't reopen: Task 6's refresh gate (§7), `_state_stamps()` (§4.2).
- Deferred to whole-branch review: m6-m10, i11, i12, kqueue vs in-place edits,
  `Output/photos/<stem>/`.
- Redirecting Xcode caches to /tmp — the manifest cache is not redirectable.
- `danger-full-access` for Codex — would expose the main repo's live photo data.
- Widening Codex's writable roots so it can commit — the controller committing
  after verifying IS the review gate. Keep it.
- Pinning main's sha here — the commit writing it invalidates it instantly.

## In flight
- TASK 8 RE-REVIEW RUNNING (Opus, `term_d00410dc-…`), scope bf4cbd1..e512205,
  brief `task-8-rereview-dispatch.md`; watcher polls BOTH the ledger and the
  worktree root for `task-8-rereview.md`.
- The built app is open on the real repo (read-only; do NOT click Reprocess or
  the re-render chip — both invoke the pipeline on live photo data).
- WT=~/orca/workspaces/.../plan2-printworks-app (HEAD e512205). Ledger gitignored
  but ARCHIVED through Task 8 incl. `qa/` to docs/superpowers/sdd-archive/ (on
  origin).

## Next
1. On the re-review: if compare is a real defect, fix round via the Orca loop;
   else Task 9 (crop overlay). Briefs 9/10 are 23-25 lines and need spec §5-§8,
   the AppModel surface, Task 7/8's view files, and the sandbox flags.
2. Task 11 pins a `-destination`. Refresh the docs archive when Plan 2 completes.
