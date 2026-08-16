# Task 9 re-review — dispatch

Reviewer: Opus 5 xhigh. Scope: **`e512205..e9a16e7`**.
Read `task-9-brief.md`, `task-9-dispatch.md`, `task-9-report.md`, and
`task-8-rereview.md` §3 (M1/M2, which this commit was told to close).

## Controller verification already done — build on it, don't repeat it

- `swift test --disable-sandbox` → exit 0, **69** tests (+3). `xcodebuild` → exit 0.
- **Crops-cache mutation, re-run by me:** deleting the cache-hit branch makes
  `testCropsUsesCanonicalArgsAndCachesUntilRevisionChanges` RED on both the basis
  assertion and the call-count assertion.
- **M1 closed and observable:** the AX tree now prints `slider Warmth`,
  `slider Exposure`, `text field Expression audit note`,
  `radio group Style, Preview style` — nameless controls were what made the
  previous smoke rely on guessed indexes.
- **M2 closed:** `AppModel.photos(inDeliveryOf:)` exists and the four view copies
  are gone.
- **SMOKE PASSED against a scratch repo** (`qa/task-9-crop-overlay.png`,
  `qa/task-9-inspector.png`): crop overlay draws 8×10 solid + 5×7 dashed inside
  the image's actual letterboxed rect; inspector renders ADJUST (Warmth "As shot"
  → "5750 K"), CROPS (both "persisted"), expression audit, Approve correctly
  DISABLED; `c` toggles the overlay (amber pixels 2975 → 8086).
- **The full mutate round-trip, verified:** moving Warmth fired `adjust`, which
  wrote ONLY `sidecars/P1036163_natural.pp3` and `recipes/P1036163.yaml` — both
  pipeline-owned, nothing written by the app process — and the photo transitioned
  **verified → review_required** as the fingerprint rule requires. The toolbar
  then updated to "1 needs review" via the watcher.

## Your focus

1. **`crops(stem:)` in-flight dedup.** It stores a `CropRequest` (id, revision,
   task) so concurrent callers share one task — more than the brief asked for.
   Check the cancellation/replacement logic: can a superseded request clobber a
   newer cache entry, leak a task, or return a result for a stale revision?
2. **Coordinate mapping.** The brief is explicit that windows must be drawn
   inside, and drag deltas normalized against, `CropMath.aspectFitRect` — the
   GeometryReader frame is wrong under letterboxing. Verify both directions
   (draw AND drag), not just draw; my smoke only proves draw.
3. **Drag-nudge correctness.** I did NOT exercise a drag. Does `onNudge` store
   into the draft's `cropNudges`, is aspect/size locked by construction via
   `CropMath.nudged`, and can a drag escape the image bounds?
4. **`setSlider` composition** — only the changed control is sent. My smoke moved
   Warmth only; check Exposure and the both-touched case.
5. **Approve enablement** (`model.canApprove`) and the stale-draft banner /
   Re-review flow per §6.1 — my smoke saw Approve disabled but never enabled it.
6. Anything Task 9 **broke** in Tasks 7-8's confirmed behaviour, and whether the
   M1/M2 edits touched anything they should not have.

## Out of scope

Previously deferred: m6-m10, i11, i12, kqueue vs in-place edits,
`Output/photos/<stem>/`, the Task 5 refresh gate. Settings is Task 10.

## Output

Write `task-9-rereview.md` **in this ledger directory**. Severity-ordered
findings with file:line and a concrete failure scenario, and a plain statement of
whether Task 9 ships.
