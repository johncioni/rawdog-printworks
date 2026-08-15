### Task 9: CropOverlayView + InspectorView

**Files:**
- Create: `app/RAWdogPrintworks/Sources/CropOverlayView.swift`, `InspectorView.swift`
- Modify: `ReviewView.swift` (overlay + inspector column), `Sources/PrintworksCore/AppModel.swift` (crops fetch + nudge storage — test-first)

**Interfaces:**
- Consumes: `CropMath.nudged`, `AppModel.drafts[...].cropNudges`, `model.crops(stem:)` (new: calls the `crops` command, caches result per stem until revision moves — unit-tested).
- Produces:
  - `CropOverlayView(windows:imageSize:onNudge:)` — draws the 8×10 window solid amber, 5×7 dashed, over the canvas. Coordinate mapping goes through `CropMath.aspectFitRect(image:container:)` — windows are drawn inside, and drag deltas normalized against, the rectangle the image ACTUALLY occupies (letterboxing means the `GeometryReader` frame is wrong for both). `DragGesture` translates via `CropMath.nudged` (aspect/size locked by construction) and reports the final window through `onNudge(cropName, window)` → stored in the draft's `cropNudges`; a small `basis` chip ("centered fallback" / "detection failed — centered") when the crops result's basis ≠ "faces"/"persisted".
  - `InspectorView(model:)` — fixed 260 pt column on `Theme.panel`: ADJUST section (Warmth slider 3000–9000 K showing "As shot" when `Control.source == "camera"` and untouched; Exposure −1.00…+1.00; both call `model.setSlider` on change — the 2 s debounce and `adjust` composition are already model-tested; Reset button → `model.resetAdjust(stem:style:)` issuing `--reset`, test-first); CROPS section (per-crop status line + "nudged" tag); EXPRESSION AUDIT checklist (three `Toggle`s + note `TextField` bound to the draft); stale-draft banner ("This photo changed on disk — re-check before approving" + Re-review button clearing `isStale` after re-confirmation per spec §6.1); Approve button (`Theme.accent`, enabled by `model.canApprove`, running `model.approve`).

- [ ] **Step 1: Model additions test-first** — `AppModelTests`: `setSlider` composes `adjust --stem P1 --style natural --temperature 5600 --json` (only changed control); `resetAdjust` sends `--reset`; `crops(stem:)` sends `["crops", "--stem", "P1", "--json"]` once and caches until `reviewRevision` changes.
- [ ] **Step 2: Implement the views.**
- [ ] **Step 3: Gate** — core tests PASS, app builds.
- [ ] **Step 4: Manual smoke + screenshots** — crop overlay on P1036163 (both windows visible, drag nudges), sliders move and write sidecars through the pipeline (verify `git status` shows only pipeline-owned files changed — i.e., sidecar/recipe/preview changes made by python, none by the app process itself).
- [ ] **Step 5: Commit**

```bash
git add app/
git commit -m "feat(app): crop overlay drag-nudge + inspector (sliders, audit, approve)"
```

---

