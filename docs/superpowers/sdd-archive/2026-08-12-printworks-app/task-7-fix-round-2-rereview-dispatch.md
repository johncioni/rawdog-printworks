# Task 7 fix round 2 — re-review dispatch

Reviewer: Opus 5 xhigh. Scope: **`c9165c2..87511e8`** — the fix commit only.
Read `task-7-fix-round-1-rereview.md` (the findings) and
`task-7-fix-round-2-report.md` (the claims) first.

The previous review said Task 7 ships once M1 (unbounded cache), m2, m3 land, and
called m4 a judgement call. Decide whether it ships now.

## Controller verification already done — do not just repeat it

- `swift test --disable-sandbox` → exit 0, **62** tests (+2). `xcodebuild` → exit 0.
- **m3 mutation, re-run by me:** replacing the selective removal with a wholesale
  `lastFailures.removeAll()` turns `testRetrySuccessPreservesOtherStemFailures`
  RED (`nil` vs `Optional("bad two")`).
- **Smoke on the true new binary** (I verified build time 16:17:56 vs process
  start 16:18:45 — a stale-instance mistake burned me once this session): badge
  contrast 5.88:1 / 6.13:1, and 11 watched-dir FDs still held.
- m4 is fixed, not deferred: `Color.red.opacity(0.9)` → opaque `Color.red`.

## Your focus — what I could not verify

1. **Is the cache actually bounded now, and is the bound right?** Quantization is
   a 256 px ladder; the store is a cost-limited LRU. Check the accounting: is
   `cost` computed correctly per entry, can `totalCost` drift from the real sum,
   can an entry exceed the limit and wedge the loop, and is the eviction order
   genuinely LRU rather than insertion order? The report states a worst-case
   retained figure — verify the arithmetic rather than trusting it.
2. **Did quantization break correctness anywhere?** A 256 px ladder means a 42 pt
   thumbnail and a small card can share a key. Is that right, and does the
   downsample still look correct at each rung?
3. **m2's move:** `preview = nil` now only fires on hash change. Can a stale image
   from a previous request now survive into a new one?
4. **m3:** does `applyRunResult` now handle the two failure directions the finding
   named, and does the "clear entries disk truth invalidated" half actually work?
5. Anything this round **broke** in previously-confirmed behaviour — M1 (watcher)
   and M3 (`--force`) especially. Neither should have been touched.

## Out of scope

i5, i6, m6-m10, i11, i12 and all previously deferred items. `ReviewScreen` is
Task 8's; Settings is Task 10's.

## Output

Write `task-7-fix-round-2-rereview.md`: severity-ordered findings with file:line
and a concrete failure scenario, and a plain statement of whether Task 7 ships.
If it does, say so unambiguously — this is round three on this task and I want a
clear terminal state, not another maybe. If my verification was insufficient,
say so.
