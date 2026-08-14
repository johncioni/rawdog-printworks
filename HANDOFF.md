# HANDOFF

## Goal
RAWdog Printworks. Plan 1 (pipeline JSON interface) is MERGED to main —
the pipeline exposes the additive `--json` NDJSON contract and its golden
fixtures. Next substantive work is Plan 2 (macOS SwiftUI app) = RAW-2.
Repo is wired to Orca + GitHub + Linear (team RAW) + CodeRabbit, with a
CI gate on every PR.

## Done
- PR #3 merged as 356115c with a MERGE COMMIT (16 task commits kept).
  CodeRabbit APPROVED, 0 unresolved threads, CI green. main = 37a9b4d,
  gate = 295 passing.
- CodeRabbit review: 15 findings, all answered. Fixed 10 — case-only RAW
  overwrite in ingest (the serious one), shared error adapters for
  `adjust`, collect-mode isolation widened to Exception (keeping legacy
  hard-stop + CommandError codes), jsonio.deactivate() teardown, pp3
  newline='' byte preservation, test_cli scoped to tmp_repo, staged-hash
  dedup decision test, ERROR_CODES + sidecar-deletion coverage,
  AssertionError stubs, E702 splits.
- Dismissed 5 with citations: optional `expected_review_revision` (spec
  §4.2 compatibility scoping), status stamp breadth (spec rounds 2+3 chose
  re-stat-and-retry over a seqlock), `sys.executable` → `.venv/bin/python`
  (breaks CI, no .venv), regen-command scoping (already scoped), bare
  RuntimeError mapping (used for internal invariants too).
- Re-audit A — case-only collision (subagent, read-only): CONFIRMED REAL,
  reproduced twice against the real module. APFS rename keeps the existing
  entry's case, so `Input/P9.RW2` kept its name and got the other photo's
  bytes while the result reported `placed: ["p9.RW2"]`. Archived victim
  survives (archive/ is case-insensitive, render re-hashes); unarchived
  victim is lost. Shipped `destination.exists()` guard at ingest.py:196
  closes the data-loss path.
- Re-audit B — status stamp breadth (subagent, read-only): DISMISSAL
  UPHELD, impact is display-only. The claimed (recipe, sidecar) tear is
  not observable: `adjust` writes only `rec["app_adjustments"]`
  (adjust.py:35,58-63), absent from both `recipe.fingerprint`
  (recipe.py:107-117) and the status result. The real window is
  intra-`_photo` — sidecar hashed in `gather_material` (status.py:29),
  re-read in `_control` (status.py:64-68) — and `review_revision` comes
  wholly from the coherent `material`, so only a slider numeral can tear.
  No destructive path: approve recomputes under the lock and fail-closes
  with STALE_REVIEW; nothing publishes off a snapshot; `_reconcile`
  (adjust.py:38-53) blocks clobbering independently of status.
- Linear: RAW-1 Done (PR attached), RAW-5 Done. Open: RAW-2 (Plan 2),
  RAW-4 (branch protection), RAW-6 (detection fixture).

## Ruled out
- Squash-merging PR #3 — the 16 per-task commits are the record.
- Requiring `expected_review_revision` / widening status stamps — both
  adjudicated design decisions; re-audit B independently upheld the latter.
- Expanding `_state_stamps()` as the fix for re-audit B: it converts a tear
  into a retry only, since `snapshot()` returns unconditionally at
  `attempt == 1` (status.py:98), and statting previews/Output would rebuild
  (re-sha256 every preview JPG) on nearly every poll during a run.

## In flight
- Nothing running. Bots quiet.

## Next
1. RAW-2 / Plan 2 (macOS app). Fixtures in tests/fixtures/json_contract/
   are binding. Enable swift-lsp; `brew install xcodegen` in its Task 1.
   Gates: swift test + xcodebuild build + visual QA.
2. RAW-7 FILED (re-audit A, filesystem divergence, not data loss): stems
   compared case-sensitively at ingest.py:70, :172-173/190/198, :124 and
   render.py:91. Fix = `.casefold()` at all four sites. The "colliding
   Output trees" part is UNVERIFIED (those are distinct dirs on a
   case-sensitive volume) — confirm before implementing.
3. RAW-8 FILED (re-audit B, optional): hoist parsed sidecar/style `Pp3`
   docs into `gather_material` and have `_control` read from `material`.
   Those bytes are already read there by `render._h`, so it removes a
   duplicate read — cheaper per poll than today — and closes the torn-read
   window instead of narrowing it.
4. RAW-4 branch protection — now enforceable, `pytest` is a real check.
5. USER DECISION (cleanup, non-urgent): json-interface worktree + branch
   still exist (both at e7afc61 = merged). `git worktree remove --force
   .claude/worktrees/json-interface` + `git branch -D
   worktree-json-interface` + `git push origin --delete
   worktree-json-interface`, or keep.
6. Known limitation: the 16 Plan 1 commits are unsigned (1Password will
   not sign for agent-launched shells). Merge commit is GitHub-signed.
