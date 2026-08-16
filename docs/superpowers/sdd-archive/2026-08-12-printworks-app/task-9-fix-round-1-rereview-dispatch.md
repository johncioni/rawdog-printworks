# Task 9 fix round 1 — re-review dispatch

Reviewer: Opus 5 xhigh. Scope: **`e9a16e7..5784003`** (the fix commit only).
Read `task-9-rereview.md` (the findings) and `task-9-fix-round-1-report.md`.

## Controller verification done

- `swift test --disable-sandbox` → exit 0, **75** tests (+6). `xcodebuild` → exit 0.
- **Exposure-formatting mutation, re-run by me:** changing
  `Self.number(exposure, decimals: 2)` to `decimals: 1` turns
  `testSetSliderSendsExposureWithTwoDecimalPlaces` RED (`"0.3"` vs `"0.35"`).
  (My first attempt mutated a string that does not exist in the file and passed
  vacuously; I found the real call site rather than count that as evidence.)
- M1's ordering is fixed in source: `.contentShape(Rectangle())` is now line 45,
  `.position(` line 46.

## THE THING I COULD NOT VERIFY — and why my attempts prove nothing

I tried to smoke the drag and **my tooling cannot drive SwiftUI drags at all**:

| attempt | result |
|---|---|
| Drag in the black letterbox (should now be inert) | no change |
| Drag the 8×10 window (should now work) | no change; canvas pixel diff **0.00**, amber pixel count identical |
| **Control: drag the split-view splitter** (known draggable, value readable) | **Value stayed 250** |

The control settles it: synthesized drags are not reaching the app, so **both**
crop results are vacuous — the letterbox "pass" is as meaningless as the 8×10
"failure". Do not read either as evidence in either direction.

**So M1's fix is unverified behaviourally.** You confirmed the *mechanism* last
round with a standalone probe; please confirm the *fix* the same way. Both halves
matter:
1. the 8×10 window is now draggable at all, and
2. a press in the letterbox outside the photo no longer nudges 5×7 into the draft.

If you also cannot drive a real drag, say so plainly and I will ask the user to
drag it by hand — an unverified Major is worth one question, not a guess.

## Also confirm

- **M2** crops no longer refetch per style switch; **M3** the BAD_INPUT
  render-dims case no longer banners and `cropStatus` falls back to
  `photo.crops`; **M5** the stale-style names actually appear under Approve;
  **N6** the live drag preview is clamped; **N11** the cache is bounded (the new
  tests claim an LRU at 40 and ≤8 concurrent queries — check the accounting, as
  the last bounded-cache fix in this app was itself unbounded); **N12** the
  shortcut legend is back.
- Whether the fix **broke** anything in Tasks 7-8, or in Task 9's own
  already-verified parts (overlay draw, crops cache, the mutate round-trip).

## Out of scope

N7-N10 and everything previously deferred. Settings is Task 10.

## Output

Write `task-9-fix-round-1-rereview.md` **in this ledger directory**.
Severity-ordered findings with file:line and a concrete failure scenario, and a
plain statement of whether Task 9 ships now.
