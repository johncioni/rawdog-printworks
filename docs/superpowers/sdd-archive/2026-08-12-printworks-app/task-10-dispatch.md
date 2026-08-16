# Task 10 dispatch — Ingest banner, Settings, notifications

You are the implementer; a separate Opus reviewer reviews this afterwards.

## Read first

- `.superpowers/sdd/2026-08-12-printworks-app/task-10-brief.md` — **authoritative**.
- `docs/superpowers/specs/2026-08-12-macos-app-design.md` §5.5 (live Settings
  validation) and the ingest/notification sections.
- `task-9-fix-round-1-rereview.md` — the carry-forwards below are from it.
- Tasks 7-9's shipped views for conventions; `PipelineClient` and `AppModel`.

## Order of work — model tests first (brief Step 1)

Red-then-green, recording the mutation you used for each:
1. `pendingInputFiles` — lists `Input/*.rw2|*.RW2` whose stems are absent from the
   snapshot. Test with a temp dir set as repo.
2. `ingestPending` — argv is exactly `ingest --delivery-id <uuid> --json` followed
   by `run --json`.

## Settings — the details that bite

- Keys are `repoPath` / `pythonPath` in `UserDefaults`. **Tilde-expand with
  `NSString.expandingTildeInPath` before any use** — `URL(fileURLWithPath: "~/…")`
  does NOT expand, and both defaults are written with a tilde.
- Validation is **live** per §5.5: debounce field changes ~600 ms into a
  `status --json` probe through a throwaway `PipelineClient`; show ok/error
  inline; Save enables only while the current pair validates; saving rebuilds the
  model's client **and** watcher.
- This also closes **i12** — "Open Settings" in the error banner is a dead button
  until this scene exists.

**Note for your own testing:** the controller currently has these defaults
pointed at a scratch repo (`~/orca/workspaces/rawdog-printworks/smoke-repo`), not
the real one. Do not change them, and do not point anything at
`~/Projects/rawdog-printworks` — it holds irreplaceable photo data.

## Carry-forward — REQUIRED

**m11 (measured) — the "8 concurrent crops" bound counts map entries, not running
subprocesses.** `AppModel.swift:315-330`, `:341-345`. When a stem is re-requested
at a new revision the map entry is *replaced*, so the eviction branch is skipped
(`cropRequests[stem] == nil` is false) and the count never rises — while the
overwritten `Task` and its python subprocess keep running, uncancelled.
`removeCropRequest` then correctly declines to evict the successor, so the orphan
vanishes from the accounting while still executing. Measured peak concurrent
`crops`: 8 → **16** → **24** → **32** across four revision waves. Linear in
revision churn, i.e. unbounded.

Fix it so the bound counts *running work*, and **cancel the superseded task**.
This is the third time this app has declared a bound it did not enforce (the
preview cache, then its "bounded" replacement, now this) — so add a test that
would have caught it: assert peak concurrency across revision churn, not just
map size.

**Nits, fix if cheap:** n14 (the new `.onChange(of: model.selectedStyle)` is dead
weight), n16 (a residual per-revision refetch survives M2), n15 (the LRU test
never exercises recency — it would pass on a FIFO). **n13** (with real geometry
the 8×10-only hit region is a ~5%-of-height sliver) is a UX judgement — say what
you would do rather than silently redesigning the overlay.

## Binding constraints

No pipeline logic in Swift. No repo writes from Swift. Argv-only subprocess.
Views add no model logic. Reuse `PreviewImage`. Notifications: request
authorization once at first use; silently ignore refusal.

## Gates

```
swift test --disable-sandbox --package-path app/PrintworksCore
xcodegen generate            # you are adding two files
xcodebuild -project app/RAWdogPrintworks/RAWdogPrintworks.xcodeproj \
  -scheme RAWdogPrintworks -destination 'platform=macOS' \
  OTHER_SWIFT_FLAGS='$(inherited) -disable-sandbox' build
```

Exit code is the oracle, never a grep (zsh: `$PIPESTATUS[0]` expands to nothing).

## Report + stop

Write `task-10-report.md` **in this ledger directory**. You **cannot commit** —
the worktree's git metadata is outside your writable roots; leave the work
uncommitted and state the intended commit message. Do not open the app; the
controller owns the smoke. Do NOT rewrite `HANDOFF.md`.
