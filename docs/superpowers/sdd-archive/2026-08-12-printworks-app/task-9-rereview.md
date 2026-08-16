# Task 9 re-review — CropOverlayView + InspectorView

Reviewer: Opus 5 xhigh. Scope `e512205..e9a16e7` (one commit, 11 files, +738/−62).

I built on your verification rather than repeating it: I did not re-run the gates,
re-do the crops-cache mutation, or re-run the mutate round-trip. I took all of
those as given and spent the round on the five things you could not reach.

---

## 1. Does Task 9 ship?

**Not as it stands — but the blocker is a one-line reordering.** `M1` below means
the 8×10 crop window **cannot be dragged at all**, and a drag anywhere on the
canvas — including the black letterbox outside the photo — silently nudges the
5×7 window into the draft that Approve then persists. The brief's headline
deliverable is "drag nudges"; today half of it is unreachable and the other half
fires from the wrong places.

Move `.contentShape(Rectangle())` up two lines and it ships. Everything else
below is Minor and can ride into Task 10/11.

---

## 2. Findings, severity-ordered

### M1 (Major, CONFIRMED) — the crop windows' drag hit region is the entire canvas, not the window

`app/RAWdogPrintworks/Sources/CropOverlayView.swift:44-51`

```swift
.position(x: ..., y: ...)      // <- makes the view take the FULL parent size
.offset(translation)
.contentShape(Rectangle())     // <- so this Rectangle spans the whole overlay
.gesture(DragGesture()...)
```

`.position(x:y:)` is a layout modifier: the view it returns accepts the parent's
entire proposed size and places its child at the point. `.offset` is purely
visual and does not shrink it back. So when `.contentShape(Rectangle())` runs
*after* them, the rectangle it installs as the hit shape is the whole overlay
area, not the 8×10 / 5×7 window.

**Evidence — I reproduced the exact modifier chain in a standalone SwiftUI probe**
and measured the layout size of the view `.contentShape` is applied to:

| modifier order | hit-shape view size | crop rect |
|---|---|---|
| `frame → position → offset → contentShape` (shipped) | **400×300** (= whole container) | 100×60 |
| `frame → contentShape → position → offset` (fix) | **100×60** ✓ | 100×60 |

Two consequences, and the second is the one with teeth:

**(a) The 8×10 window can never be dragged.** Both outlines get identical
full-canvas hit shapes, and `ForEach(["8x10", "5x7"])` (`:15`) puts 5×7 second in
the `ZStack`, i.e. in front everywhere. Hit testing goes front-to-back, so 5×7
wins at every point on the canvas. Confirmed against the running app: a 40 pt
drag inside the photo produced `5 × 7 … nudged` in the inspector's CROPS list and
never touched 8×10.

**(b) A stray drag edits a crop the user never aimed at.** Any click-drag on the
canvas — the letterbox, the region outside both rectangles, an accidental
2-pixel wobble on a click — lands on 5×7, calls `onNudge`, and writes into
`drafts[stem].cropNudges`. `AppModel.approveCropWindows` (`AppModel.swift:657`)
merges `cropNudges` over the persisted windows into the review file, so that
accidental drag becomes the crop geometry `approve` binds into the recipe.
`CropMath.nudged`'s clamp keeps the value legal and the "nudged" tag does appear
in the inspector, so it is not wholly silent — but nothing the user did was about
the crop.

**Fix:** move `.contentShape(Rectangle())` to immediately after `.frame(...)` at
`:43`, before `.position`. Verified above that this yields the crop rect.

*Verification caveat:* the probe settles the mechanism and (a) is confirmed
live. The specific "drag in the black letterbox and watch 5×7 move" run was cut
off — the machine's screen locked mid-test and Orca Computer Use's Accessibility
grant dropped to `not-granted`, so I stopped driving the UI rather than touch
System Settings. The 20-second manual confirmation: turn the overlay on, drag in
the black bar well below the photo, and watch the CROPS list gain "nudged".

---

### M2 (Minor) — `crops` is fetched eagerly per selection *and* per style switch, and cannot be cancelled

`InspectorView.swift:33-48`, `AppModel.swift:300-330`, `AppModel.swift:32-34`

`InspectorView`'s `.task(id: selectionKey)` calls `model.crops(stem:)`
**unconditionally**, and `selectionKey` is `stem|style|reviewRevision` (`:263-266`).
So it fires on every photo selection and again on every ⌘1–⌘4. Three properties
compound:

- `crops` goes through `PipelineClient.run`, not `runMutating` (`AppModel.swift:33`),
  so there is no FIFO — these run concurrently by design.
- the `Task { await client.crops(...) }` at `:311` is unstructured, so cancelling
  the view's `.task` does **not** cancel the subprocess.
- `crops(stem:)` never checks `Task.isCancelled` before its recursive retry at
  `:324`, so a long-abandoned caller keeps issuing new subprocesses.

Measured on the smoke repo: `crops --stem` costs **0.46 s and 1.19 s** wall on the
*cheap* fully-persisted path — it never even reaches Vision. The suggested path
adds `subject.group_bbox_detail` face detection on top.

Failure scenario: arrowing through a 60-photo delivery spawns ~60 concurrent
python subprocesses that no longer have a consumer. Worse, during a `run --stem`
on the selected photo every preview write moves `review_revision`, which both
re-fires the `.task` *and* trips the recursive retry — one more `crops` subprocess
per revision change, competing with RawTherapee for the machine.

Cheap fix: gate the fetch on `showingCrops || photo.crops.isEmpty` (a photo with
persisted crops already has both windows in `photo.crops` from `status`), and
`guard !Task.isCancelled` before the recursion at `:324`.

---

### M3 (Minor) — selecting a not-yet-previewed photo pops a red error banner

`pipeline/driver.py:441-445` → `AppModel.swift:318-323` → `InspectorView.swift:275-285`

`crop_windows` raises `BAD_INPUT "render dims not recorded; generate previews
first"` when the recipe carries no `render_width/height` and the crops are not
*fully* persisted — exactly the state of a freshly-ingested photo before `run`
finishes. `--json` turns that into an `ok:false` envelope with a code
(`__main__.py:86-87`), and `AppModel.crops` surfaces every non-`LOCK_HELD` error
as a banner. Because the failure is never cached, it re-fires on every
re-selection and every style switch (M2's trigger).

Second half of the same bug: `cropStatus` (`InspectorView.swift:275-285`) only
ever consults `cropResult`, so both crop rows read **"unavailable"** — even for a
photo whose persisted windows are already sitting in `photo.crops` from `status`.
Fall back to `photo.crops`, and treat this particular error as "no suggestion
yet" rather than a banner.

*Traced through the code, not executed — both smoke-repo photos are past ingest
and I would not ingest into it to manufacture the state.*

---

### M4 (Minor, test coverage) — the `--exposure` half of `setSlider` is not tested anywhere

`AppModelTests.swift` — **every** `setSlider` call site in the suite passes
`exposure: nil` (`:223, :388, :501-505, :563, :643, :666, :685`). Task 9's new
`testSetSliderSendsOnlyChangedTemperatureControl` proves the "only the changed
control" rule for temperature; `applyAdjust`'s exposure branch
(`AppModel.swift:535-537`, `%.2f` formatting) and the both-touched composition
(both flags in one argv, which is what `pendingAdjustments` accumulation exists
for) have never executed under test.

The brief's Step 1 asked for the rule, not for half of it. Two more asserts
against `mutateLog` close it. Note the gap predates Task 9 — Task 5's suite has
the same hole — but Task 9 is the task that shipped the Exposure slider.

---

### M5 (Minor, UX) — Approve can be permanently disabled with no reason visible on screen

`AppModel.swift:443-449`, `ReviewView.swift:95-96`

`canApprove` requires `photo.stalePreviews.isEmpty` — **all** styles — which is
right per spec §6.3. But the canvas only shows the "preview out of date" chip for
the *currently selected* style. In the smoke repo, P1036163 has
`stale_previews = [bw, filmic, vibrant]`; with Natural selected there is no chip
anywhere on screen, and Approve stays greyed out even once all three audit boxes
are ticked. The user has no way to learn what is blocking them.

One line under the Approve button naming the stale styles fixes it. (Screenshot
state confirmed live.)

---

### N6 — the drag's live preview is unclamped

`CropOverlayView.swift:50, 54`. `translation` offsets the outline freely while the
drag is in progress, so the rectangle visibly leaves the photo and snaps back on
release. Run the preview through the same `CropMath.nudged` so what the user
drags is what they get.

### N7 — `.allowsHitTesting(true)` (`CropOverlayView.swift:27`) is the default; it reads as if it were load-bearing.

### N8 — the M1 accessibility carry-forward is only half-observable

Your evidence is correct for the four controls you listed. Reading the live AX
tree, these Task 9 additions surface a name: `slider Warmth`, `slider Exposure`,
`text field (settable) Expression audit note`, `radio group Style, Preview style`.
These do **not**, despite each carrying an `.accessibilityLabel` in the source:
Reset (`35 button`), Approve (`46 button (disabled)`), the three audit checkboxes
(`42/43/44 checkbox`), Compare Styles (`17 button`), and both crop-window
outlines — absent from the tree entirely.

Same caveat Task 8's reviewer recorded: I read this through
`orca computer get-app-state` and could not query `AXTitle`/`AXDescription`
directly, so I cannot separate "no accessible name" from "the tree printer omits
names for SwiftUI `Button`/`Toggle`". The pattern (every `Slider`/`TextField`/
`Picker` label lands, every `Button`/`Toggle` label does not) points at the
printer — but "M1 closed and observable" holds for four controls and not for the
other seven.

### N9 — Task 8's carry-forward #2 is still untested, and Task 9 made it bigger

The note `TextField` now shares a screen with four unmodified key equivalents:
`space` (compare, `ReviewView.swift:160`), `←`/`→` (photo navigation, `:188, :192`)
and the **new** `c` (crop overlay, `:196`). Task 8's re-review said explicitly
this "must be smoke-tested by actually typing a space into that field, not
assumed". Task 9 added both the field and the `c` shortcut, and nobody has typed
into it — I could not either, the screen locked first. 30-second check: click the
Note field, type `a c b<space>d`, read the field back.

### N10 — `approveCropWindows` falls back only when `photo.crops` is *entirely* empty

`AppModel.swift:653-656`. `status.py:40` filters out null windows, so a recipe
with one crop persisted and one not yields a 1-entry dict, the `crops` fallback is
skipped, and `approve` rejects the review file with `crops missing windows`
(`driver.py:500-502`). I could not find a pipeline path that persists exactly one
window — `driver.py:536` and `:592` both write both — so this is unreachable
today. Pre-existing, not Task 9; noted because it is one `.count < 2` away from
being load-bearing.

### N11 — `cropCache` / `cropRequests` are never pruned

`AppModel.swift:158-159`. One small entry per stem for the process lifetime.
Bounded in practice by library size; flagged only because Tasks 7-8 were held to
bounded-by-construction for the image cache.

### N12 — Task 9 deleted Task 8's shortcut legend and put nothing back

The `⌘1–⌘4 Switch style / Space Compare / ← / → Previous / next photo` block was
dropped when `inspector` became `inspectorColumn`. `grep` finds no legend
anywhere in `Sources/` now, and the live window confirms it. The shortcuts still
work; their only discoverability surface is gone — including for the new `c`,
which is otherwise undiscoverable.

---

## 3. `crops(stem:)` in-flight dedup — the three questions you asked

**Can a superseded request clobber a newer cache entry? No.** The revision guard
at `:323` runs *before* the cache write at `:327`, and both sit on the MainActor
with no suspension between them, so the cache is only ever written under a
revision that equals the live one at write time. A superseded response falls into
the recursive retry instead. I walked the interleavings: (i) request A finishes
after request B already cached — A's guard fails, A recurses and picks up B's
cache entry; (ii) revision r1→r2→r1 with two requests in flight — A's guard
passes and its result *is* correct for the live r1; (iii) two callers sharing one
request — the second one re-writes an identical value.

**Can it return a stale-revision result? No.** A caller only joins a pending
request whose recorded `revision` equals its own captured revision (`:307`), and
the post-await guard re-checks against live state.

**Does it leak a task? Not in the strict sense.** Every request is awaited by its
creator, and the id-compare at `:315` correctly declines to evict a *successor's*
map entry — I specifically checked the case where A is superseded by B and then
by C, and no entry is lost. What the tasks are is **un-cancellable**, which is M2.

Two things worth recording as correct: `crops` is genuinely non-mutating
pipeline-side (`__main__.py:36-39` — "Read-only: it reports what approve would
bind and persists nothing, so it must not contend for the driver lock"), and the
app correctly reaches it via `run` rather than `runMutating`, so it can never
deadlock behind a multi-minute render.

---

## 4. Coordinate mapping — both directions, verified live

**Draw ✓.** `CropOverlayView.swift:42-49` scales by `imageRect.width/height` and
offsets by `imageRect.minX/minY`. Measured on the running app by sampling amber
pixels: at x=700 px the 8×10 outline spans rows 314→686, matching the photo's
actual top and bottom; at y=500 px its left edge sits at 415 px against a photo
left edge of 386 px (`x ≈ 0.06`). The `GeometryReader` frame is much taller than
this — the canvas letterboxes roughly 190 px above and below — so the windows are
demonstrably placed against the image rect, not the container.

**Drag ✓.** `:62-63` divides the translation by `imageRect.width/height`, the
matching inverse. Confirmed live: a 40 pt downward drag moved 5×7 down and it
clamped **exactly** at the photo's bottom edge — the dashed 5×7 line merged with
the solid 8×10 bottom at rows 685-686, i.e. `y = 1 − h`. Normalization and
`CropMath.nudged`'s clamp both behave. **A drag cannot escape the image bounds.**

**Nudge storage ✓.** `onNudge` → `AppModel.setCropNudge` (`:393-397`) →
`drafts[stem].cropNudges[cropName]`; confirmed live by the "nudged" tag appearing
in the CROPS list. Draft-only — no repo write from Swift on a drag.

**Aspect/size locked by construction ✓.** `CropMath.swift:7-9` copies `w`/`h`
through untouched and clamps only the origin, so a drag can never trip the
pipeline's aspect check (`geometry.py:48`, 0.5 % tolerance).

**`imageSize` ✓.** `PreviewImage.swift:176-179` reports the *downsampled*
`CGImage`'s pixel size. `aspectFitRect` only consumes the ratio and the thumbnail
preserves it to within a rounding pixel, so this is correct — and it reuses the
already-decoded image rather than adding the second loader the constraints forbid.
The staleness guards (`ReviewView.swift:49-51` clearing on preview identity
change, plus the stem/style/hash check inside the callback) are sound.

---

## 5. Approve / stale-draft / Re-review against §6.1

Correct as built, apart from M5:

- `reReview` (`AppModel.swift:374-380`) adopts the current revision, clears all
  three checks, clears `isStale`, keeps note and nudges. Since `baseRevision`
  becomes the live revision, `reconcileDrafts` cannot immediately re-stale it.
  Clearing the checks is what enforces §6.1's "Approve disabled until the user
  re-confirms the checklist" — the banner goes away but `canApprove` stays false
  until all three are re-ticked.
- The banner renders only when a draft exists and is stale
  (`InspectorView.swift:23-25`); `InspectorView` guarantees a draft exists for the
  selected photo (`:38-40`), and re-running the `.task` on a revision change does
  *not* recreate it, so a stale draft survives to be shown. ✓
- `approve` flushes pending slider edits *before* sampling `draft.baseRevision`
  (`:609-610`) with the right comment about why. A flush whose `adjust` stales the
  draft is not re-checked in Swift, but that is deliberate — §6.1 says `approve`
  enforces it pipeline-side via `expected_review_revision` → `STALE_REVIEW`, and
  `:639-640` maps that back onto `isStale`. Correct.
- `canApprove` / `isStale` / `reReview` are covered by Task 5's tests
  (`AppModelTests.swift:204-327, 588-737`); Task 9 consumes them rather than
  reimplementing.

---

## 6. Regression audit — what Task 9 touched in Tasks 7-8

- **M2 (delivery derivation) closed correctly.** All five call sites —
  `ReviewView:221`, `SidebarView:162`, `MainWindow:106`, `MainWindow:111`,
  `GridView:126` — now go through `AppModel.photos(inDeliveryOf:)` (`:294-295`),
  and no `deliveryId ==` filter survives in any view.
- **Task 8 carry-forward #1 done early and correctly:** the shimmer condition was
  widened from `== "preview"` to `["preview", "adjust"].contains(command)`
  (`ReviewView.swift:95-96`), which task-8-rereview §6 had deferred to Task 11.
- **N4 and N5 done** (distinct "Not rendered" vs "Preview unavailable" glyphs and
  captions; Escape closes compare). N3 correctly left alone — out of scope.
- **`PreviewImage` change is additive** — `onImageSize` defaults to `nil`, so
  Task 7's grid/sidebar callers and Task 8's compare panels are behaviourally
  untouched. No second image loader was introduced.
- **No repo writes from Swift** — the drag path writes only to the in-memory
  draft; the review file (`AppModel.swift:663-680`) still goes to the temp
  directory.
- Only regression found is **N12**, the deleted shortcut legend.

---

## 7. What I did not verify

- The gates, the crops-cache mutation, and the mutate round-trip — taken from
  your report as agreed.
- **M1's letterbox-drag confirmation and N9's typing test.** The machine's screen
  locked partway through my UI run and Orca Computer Use's Accessibility grant
  went to `not-granted`; I stopped rather than change System Settings. M1's
  mechanism is confirmed by the standalone probe and by the live 5×7 capture;
  what is missing is only the direct demonstration of the out-of-bounds hit.
- **M3** is traced through the code, not executed — producing the state needs an
  ingest into the smoke repo.
- The AX-name question in N8, for the reason stated there.
- Anything behind Settings (Task 10) and the previously deferred set: m6-m10,
  i11, i12, kqueue vs in-place edits, `Output/photos/<stem>/`, the Task 5 refresh
  gate.

Live UI work was done against the smoke repo (`~/orca/workspaces/rawdog-printworks/smoke-repo`),
which the running app was already pointed at. Everything I drove was draft-only or
read-only: no `adjust`, `approve`, `run`, or `preview` was issued. The smoke
repo's only two dirty files (`recipes/P1036163.yaml`, `sidecars/P1036163_natural.pp3`)
are both stamped 19:18, i.e. your mutate round-trip — nothing changed during my
run. The one UI state I altered, the split-view width, I dragged back to 250.
