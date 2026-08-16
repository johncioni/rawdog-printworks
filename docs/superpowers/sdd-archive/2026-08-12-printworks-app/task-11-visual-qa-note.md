# Task 11 Step 3 — visual QA gate: completion note

Controller (Opus 5). Captured against the **scratch repo**
(`~/orca/workspaces/rawdog-printworks/smoke-repo`), not the real one, per the
user's decision that mutating smokes must not touch irreplaceable photo data.

**All 11 screenshots in `qa/pass/` are verified distinct** (11 unique hashes of
11 files) and each was saved only after a capture helper confirmed an expected
marker was actually on screen. That guard exists because an earlier, unguarded
batch produced 7 files containing 2 distinct screens — six copies of the grid
saved under names like `qa-03-crop-overlay.png`. Those were deleted.

## Reviewed by eye — PASS

| # | State | What I confirmed |
|---|---|---|
| 02 | Review canvas, Natural | real preview renders; style control; keyboard legend present |
| 03 | Crop overlay | 8×10 solid + 5×7 dashed, drawn inside the letterboxed image rect |
| 04 | Compare (partial renders) | 4-up grid; unrendered styles show the placeholder, not a blank |
| 05 | Styles ⌘2/⌘3/⌘4 | canvas changes per style; selection follows |
| 06 | **Busy pill + stale-draft banner** | 🔒 "Pipeline busy (CLI)" while a CLI render held the lock, and "This photo changed on disk — re-…" simultaneously |
| 07 | Error banner | bogus python path → "could not launch"; recovered after restore |
| 08 | Compare, all 4 rendered | Natural (amber border), Filmic, **Bw genuinely monochrome**, Vibrant visibly more saturated; button flips to "Close Compare" |
| 09 | Slider adjusted | Warmth 5750 K, "As shot" replaced by the value |
| 11 | After approve | published state after the full chain |

Plus, from earlier tasks and equally eye-reviewed: `task-9-inspector`
(ADJUST/CROPS/audit/Approve-disabled), `task-10-settings-invalid` (live
validation + Save disabled), `task-10-ingest-banner` ("1 new RAW file").

## The end-to-end proof this pass produced

Driven entirely through the UI against a real pipeline:

1. Warmth slider → `adjust` wrote **only** `sidecars/*.pp3` + `recipes/*.yaml`
   (pipeline-owned; the app process wrote nothing) → photo transitioned
   **verified → review_required** by the approval-fingerprint rule → toolbar and
   sidebar followed via the watcher.
2. Four preview re-renders → `stale_previews: []`.
3. Three audit boxes checked → **Approve enabled** (validating `canApprove`:
   audit complete AND no stale previews).
4. Approve → approve + `run` → **v002 published, 29 artifacts, v001 pruned**,
   state back to **verified**, lock released.

`git status` on the scratch repo after all of it: only `recipes/` and
`sidecars/`. Nothing written by the app.

## NOT captured — stated plainly

- **Render progress bar.** The post-approve `run` finished faster than my polling
  window because all four previews were already fresh. The helper refused to save
  anything without the marker rather than bank a false capture.
- **"rendering preview…" shimmer.** It only appears while a stale-preview
  re-render is in flight; by then no style was stale. Reachable by making one
  stale and clicking the chip.

## Findings from the eye review

- **N3 confirmed visually** (already logged, deferred): compare cells are
  portrait, so landscape previews occupy roughly 45% of each cell.
- **Release build cannot be driven by the automation** — `window_not_focused`
  on every click, while the identical Debug build accepts them; AX reads and
  screenshots work for both. Reproduced across a fresh relaunch, explicit
  System-Events activation, `--window-id` targeting, and a title-bar click. This
  pass therefore ran against **Debug**. The brief asks for the Release app, so
  this is an open item for the whole-branch review — most likely macOS treating
  the ad-hoc-signed bundle as a distinct identity for synthesized input, but I
  did not prove that.
