# Task 9 fix round 1 — re-review

Reviewer: Opus 5 xhigh. Scope **`e9a16e7..5784003`** (the fix commit only, 6 files,
+370/−78).

---

## 1. Does Task 9 ship?

**Yes.** M1 is genuinely fixed, and I confirmed it behaviourally — both halves —
with a standalone probe that drives real SwiftUI drags. The 8×10 window is
draggable, and a press in the letterbox no longer nudges anything.

Everything below M1 is Minor or Nit and can ride into Task 10/11. The one that
matters most is **m11**: N11's cache half is correctly bounded, but its
*eight-concurrent-query* half is not — I measured 32 concurrent `crops`
subprocesses against a declared limit of 8. That is the exact failure pattern you
warned me to look for, and the fix's own test does not catch it.

---

## 2. M1 — CONFIRMED FIXED, behaviourally

### Why your runs were vacuous, and mine were too at first

`CGSSessionScreenIsLocked = True`. **The machine's screen is locked.** With the
screen locked WindowServer will not activate an app or deliver mouse events to
any window, so *no* synthesized-event path that goes through it can work — which
is why your splitter control stayed at 250, and why my first two attempts
(`NSApp.postEvent` and `NSWindow.sendEvent`) also recorded nothing. This is the
same condition that cut off the previous round ("the machine's screen locked
mid-test"). Your reading was right: neither of your crop results was evidence.

### The path that does work

SwiftUI recognises `DragGesture` inside `NSHostingView`'s own responder methods,
not in an `NSGestureRecognizer` that needs window dispatch. So calling
`mouseDown(with:)` / `mouseDragged(with:)` / `mouseUp(with:)` **directly on the
hosting view** drives the real gesture pipeline and never touches WindowServer.
That works with the screen locked.

Two guards make the result non-vacuous:

- **Harness control** — a plain full-canvas `DragGesture` with no `.position`
  at all. It reports `translation=(30, 15)` for a synthesized (30, 15) drag. If
  events were not landing, this would be silent, as it was under `post`/`send`.
- **Old-chain arm** — the pre-fix modifier chain from `e9a16e7`, verbatim, run
  in the same harness. It reproduces the reported bug exactly. A fix arm that
  differs from a bug arm in the same harness cannot be a null result.

I also tried `NSHostingView.hitTest(_:)` as a shortcut and **threw it out**: its
method control returns non-nil at a point with nothing interactive under it, so
it does not discriminate. Ignore that approach if you see it elsewhere.

### Results

Canvas 400×300, image 400×200 → `imageRect = (0, 50, 400, 200)`, so y < 50 and
y > 250 are black letterbox. 8×10 occupies x 0–0.40, 5×7 occupies x 0.60–1.00 —
disjoint, so each press point has exactly one correct owner. Drag +20 px in x.

| press point | OLD (`e9a16e7`) | NEW (`5784003`) | expected |
|---|---|---|---|
| A (80,150) inside 8×10 only | **5×7** | **8×10** ✓ | 8×10 |
| B (200,20) letterbox above | **5×7** | **—** ✓ | nothing |
| C (320,150) inside 5×7 only | 5×7 | 5×7 ✓ | 5×7 |
| D (200,150) photo, between windows | **5×7** | **—** ✓ | nothing |
| E (80,285) letterbox below | **5×7** | **—** ✓ | nothing |

The OLD column is M1 verbatim: every press on the canvas nudges 5×7, and 8×10 is
unreachable. The NEW column is the fix, and **both halves you asked about hold** —
8×10 is draggable (A), and letterbox presses are inert (B, E).

Measuring the hit shape directly agrees: OLD installs `(0,0) 400×300` for *both*
outlines; NEW installs `(0,50) 160×200` for 8×10 and `(240,50) 160×200` for 5×7 —
the crop windows, letterbox excluded.

I re-ran the fix arm against the **real** geometry from
`smoke-repo/recipes/P1036163.yaml` (5×7 `x0 w1.0 h0.951`, 8×10 `x0.061 w0.939
h1.0`), canvas 400×400: 8×10-only sliver → **8×10**; overlap → 5×7; 5×7-only left
strip → 5×7; both letterbox bands → nothing. All correct. See **n13** for what
that geometry costs in practice.

Not observable in this harness: the *mid-drag redraw*. With the window occluded
SwiftUI skips body re-evaluation, so `onChange` never fires and I could not
sample the live outline (forcing `layoutSubtreeIfNeeded`/`displayIfNeeded`/
`CATransaction.flush()` did not change that). The commit path is unaffected and
was measured. See **N6** below.

---

## 3. Findings, severity-ordered

### m11 (Minor, CONFIRMED by measurement) — the "eight concurrent queries" bound counts map entries, not running subprocesses

`AppModel.swift:314-334`, `:359-363`

The limit is enforced against `cropRequests.count`, and the entry for a stem is
*replaced* — not added to — when that stem is re-requested at a new revision:

```swift
if let pending = cropRequests[stem], pending.revision == revision {
    request = pending                         // join
} else {
    if cropRequests[stem] == nil,             // <- eviction is SKIPPED when a
       cropRequests.count >= Self.cropRequestLimit,   //   stale-revision entry
       ...                                    //   already exists for this stem
    { ...evict and retry... }
    ...
    cropRequests[stem] = request              // overwrites; count unchanged
}
```

The overwritten request's `Task` — and the python subprocess it is running — is
never cancelled. Its creator later calls `removeCropRequest(stem:id:)`, whose
`guard cropRequests[stem]?.id == id` correctly declines to evict the successor's
entry, so the orphan simply disappears from the accounting while still running.

**Measured.** Eight stems held in flight, then each stem's `review_revision`
moved and re-requested, repeatedly (temporary test, since deleted; peak read off
`FakeClient.maxConcurrentCrops`, which counts real `crops` invocations):

| revision waves | peak concurrent `crops` |
|---|---|
| 1 (baseline) | 8 |
| 2 | **16** |
| 3 | **24** |
| 4 | **32** |

Linear in revision churn — unbounded, not a fixed 2×.

**Failure scenario:** select a freshly-ingested photo (`photo.crops` empty, so
`InspectorView.swift:51`'s gate lets the fetch through even with the overlay
closed) and `run` it. Every preview write moves `review_revision`, the `.task`
re-fires, and each new request orphans the previous still-running subprocess.
These are the 0.46–1.19 s queries the last round measured, on the suggested path
they add Vision face detection, and they compete with RawTherapee for the machine
during the render — precisely the M2 scenario the bound was added to stop.

Nothing is *incorrect*: orphaned results are discarded by the revision guard, and
in the app the orphaned callers are cancelled so they do not recurse. The cost is
purely resources.

`testCropsRequestsAllowAtMostEightConcurrentQueries` misses this because all nine
of its stems sit at one revision, so the replace-in-place path never executes.

**Fix sketch:** hold the count against in-flight *tasks* rather than dict entries
— keep the superseded `CropRequest` in a side list until its task completes, or
cancel it (`crops` is read-only pipeline-side, so cancelling loses nothing).

---

### n13 (Nit, UX) — with real crop geometry the 8×10-only hit region is a ~5 %-of-height sliver

`CropOverlayView.swift:15` (`ForEach(["8x10", "5x7"])` — 5×7 is second, so it is
in front everywhere the two overlap)

The fix makes 8×10 reachable, which is what M1 asked for. But for the geometry
the pipeline actually produces, 5×7 is `x 0 → 1.0` — the **full image width** —
and `h 0.951`. 8×10 is `h 1.0`. So the two overlap everywhere except the band
`y ∈ (0.951, 1.0]`, and that band is the *only* place 8×10 can be grabbed:
**4.9 % of the photo's height**, at its very bottom edge. Against the photo
height the last round measured in the running app (rows 314→686, 372 px), that is
an **≈18 px strip**.

Confirmed in the probe: press at the sliver → 8×10; press anywhere else inside
the photo → 5×7.

Nothing on screen indicates this, and there is no way to choose which window you
are dragging. Worth a Task 10/11 affordance (click-to-select the active crop, or
hit-test the outline stroke rather than the filled rectangle). Not a blocker —
the headline deliverable does work.

---

### n14 (Nit) — the new `.onChange(of: model.selectedStyle)` is dead weight

`InspectorView.swift:59-62` calls `configureControls(from: photo)` on a style
change, but `controlSelectionKey` (`:296-299`) already interpolates
`model.selectedStyle`, so the `.task(id:)` at `:36` re-fires and calls
`configureControls` for the same event. Both run on every ⌘1–⌘4. Idempotent, so
harmless — but one of the two should go.

---

### n15 (Nit, test coverage) — the LRU test never exercises recency

`AppModelTests.swift`, `testCropsCacheEvictsLeastRecentlyUsedEntryAtForty`

The test walks P0…P40 once in order and asserts P0 was evicted — that is
*insertion-order* eviction. The cache-hit branch that makes it an LRU
(`AppModel.swift:308-311`, `removeAll`/`append` on `cropCacheRecency`) never
runs, because no stem is read twice before the eviction. Re-reading P0 midway
and asserting P1 is evicted instead would close it.

The accounting itself is correct — see §4.

---

### n16 (Nit) — a residual per-revision refetch survives M2

`InspectorView.swift:301-304`, `ReviewView.swift:244-247`

Both crop keys are now `stem|reviewRevision|showingCrops`. Style is gone (M2's
headline), but `reviewRevision` remains, so a photo without persisted crops still
refetches on every revision bump during a `run`. Much smaller than M2's
`× styles`, and correct for cache freshness — noted because it is the trigger
that makes **m11** reachable.

Minor asymmetry alongside it: `InspectorView` gained a `!Task.isCancelled` guard
(`:52`) but `ReviewView`'s equivalent task (`:42-46`) did not. Its stem+revision
guard covers the meaningful cases, so this is cosmetic.

---

## 4. The bounded-cache accounting — checked line by line

You were right to ask. The **cache half is correct**; the **query half is not**
(m11). On the cache:

`storeCrops` (`AppModel.swift:365-376`) removes the stem from both structures
first, *then* evicts while `count >= 40`, *then* inserts:

- at 39 entries → no eviction → 40. At 40 → evict one → 39 → insert → **40**.
  The ceiling is exactly 40, and re-storing an existing stem cannot double-count
  because of the leading `removeValue`/`removeAll`.
- `cropCacheRecency` cannot drift from `cropCache`: every insertion appends and
  every removal pairs both. If it somehow did drift, the `while` loop is still
  safe — it exits on `cropCacheRecency.first == nil` rather than spinning.
- keying is by **stem**, so revision churn replaces rather than grows. m11's
  churn does not inflate the cache.
- all writes go through `storeCrops`; no direct `cropCache[...] =` survives.

On the request map: `cropRequestOrder` holds at most one entry per stem and is
removed in lockstep with the dict, and the count check and the insert are
adjacent MainActor statements with no suspension between them — so
`cropRequests.count` genuinely never exceeds 8. The bound is real; it is just
bounding the wrong thing.

---

## 5. The rest of the checklist

- **M2 — confirmed.** Neither crop key contains the style any more:
  `InspectorView.cropSelectionKey` (`:301-304`) and `ReviewView.cropLoadKey`
  (`:244-247`) are both `stem|reviewRevision|showingCrops`, while style moved to
  the separate `controlSelectionKey` (`:296-299`) that only configures sliders.
  The gate at `:51` skips the fetch entirely when the overlay is hidden and the
  photo already has persisted crops — so arrowing a 60-photo delivery with the
  overlay closed now issues **zero** `crops` queries. The cancelled-caller
  recursion is closed at `AppModel.swift:351-354`, and
  `testCancelledCropsLoadDoesNotRetryAfterRevisionChanges` fails without it.
  Residuals: n16, and the subprocess itself is still un-cancellable (m11).
- **M3 — confirmed, both halves.** `AppModel.swift:343-347` intercepts exactly
  `BAD_INPUT` + `render dims not recorded`, caches it as a nil result, and
  returns without `surface(...)`, so no banner and no refetch at that revision.
  `cropStatus` (`InspectorView.swift:319-333`) now falls through draft nudges →
  `cropResult` → **`photo.crops`** → `"unavailable"`, so a photo whose windows
  came from `status` reads its real source instead of "unavailable".
  `ReviewView.cropWindows` (`:224-232`) already fell back to `photo.crops` when
  `cropResult` is nil, so the overlay stays correct on that path too.
- **M5 — confirmed.** `staleStylesText` (`:306-310`) renders inside
  `approveSection` directly under the Approve button (`:195-199`), so it sits
  with the disabled control rather than off in the canvas. `bw` → `B&W`,
  everything else capitalised: P1036163's `[bw, filmic, vibrant]` reads
  "Re-render stale previews: B&W, Filmic, Vibrant".
- **N6 — correct by construction; the live redraw was not observable.** The
  drawn origin is now `translatedWindow` (`CropOverlayView.swift:73-80`), which
  is the *same* `CropMath.nudged` call with the same normalisation as the commit
  path at `:60-64`; `.frame` still uses `window.w/h`, which `nudged` preserves,
  so draw and commit cannot disagree. `.offset(translation)` — the unclamped
  part — is gone. I measured the commit for a −120 px drag off the left edge:
  `x = 0.000`, clamped. I could not sample the intermediate frames, for the
  occlusion reason in §2; that is the one N6 claim resting on construction
  rather than measurement.
- **N11 — half.** Cache bounded at 40 (§4). Query bound does not hold (m11).
- **N12 — confirmed.** `shortcutLegend` (`:203-211`) is back in the inspector
  after a `Divider` (`:28-29`), and its four lines match the live key
  equivalents in `ReviewView` — ⌘1–⌘4 (`:181`), Space (`:160`), ←/→
  (`:188, :192`), and the new C (`:196`). Escape-closes-compare (`:200`) is
  still unlisted, as it was in Task 8's version.

---

## 6. Regression audit

No regressions found. The blast radius is small and I checked each edge:

- `CropOverlayView` at rest is pixel-identical — `drawnWindow == window` when
  `translation` is `.zero`, and `.contentShape` does not affect drawing, so last
  round's verified **draw** mapping is untouched.
- Once a drag begins SwiftUI tracks it to mouse-up even though the hit shape now
  moves with the outline; the −120 px probe drag committed correctly after the
  clamp pinned the rectangle, i.e. the cursor leaving the shape does not drop
  the gesture.
- `ReviewView` changed by one line (`:167`, passing `showingCrops`), and
  `showingCrops` is the same `@State` that gates the overlay (`:76`) and the `c`
  shortcut (`:195`). `InspectorView` has exactly one call site.
- `cropResult = nil` on deselection moved from the control task to the crop task
  (`:46-48`); `cropSelectionKey` degrades to `"none|<showingCrops>"` when no
  photo is selected, so the task still re-fires and still clears it.
- Task 9's already-verified parts — overlay draw, the crops in-flight dedup, the
  mutate round-trip — are untouched by this commit except as described.
- Task 7/8 surfaces (`PreviewImage`, compare, grid, sidebar, delivery
  derivation) are not in the diff at all.

**Gates, re-run by me** (not taken from your report):

- `swift test --disable-sandbox --package-path app/PrintworksCore` → exit 0,
  **75 tests, 0 failures**.
- `xcodebuild … -scheme RAWdogPrintworks -destination 'platform=macOS'
  OTHER_SWIFT_FLAGS='$(inherited) -disable-sandbox' build` → exit 0.
- Working tree clean after I removed my temporary probe test.

I took M4 from your report — you found the real call site
(`AppModel.swift:579`, `decimals: 2`) and the mutation went RED.

---

## 7. What I did not verify

- **The live app.** Everything here is a standalone probe reproducing the
  shipped modifier chains verbatim, plus source reading and the package tests. I
  never opened RAWdogPrintworks, issued no pipeline command, and wrote nothing to
  the smoke repo.
- **The mid-drag visual** (N6) — occluded window, see §2.
- **N9's typing test** (space/`c`/arrows into the Note field) — same screen-lock
  reason; still open from last round, and my direct-responder trick does not
  transfer, since key equivalents are resolved by the window/menu system that the
  lock takes out.
- **N8's accessibility-name question** — unchanged and still open.
- N7, N10 and everything previously deferred; Settings is Task 10.

If you want the two screen-lock-blocked items closed, they are both quick by
hand once the machine is unlocked: drag in the black bar below the photo and
confirm the CROPS list gains nothing (M1's letterbox half, ~20 s), and type
`a c b<space>d` into the Note field (N9, ~30 s).
