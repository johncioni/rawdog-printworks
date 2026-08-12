# RAWdog Printworks — macOS App Design

**Date:** 2026-08-12
**Status:** Draft for review
**Depends on:** `2026-08-11-raw-print-pipeline-design.md` (rev 8) — the pipeline this app fronts.

## 1. Goal

A native macOS app, **RAWdog Printworks**, that puts a contemporary, black-primary UI on the existing RAW print pipeline. The app covers the full workflow — ingest, preview, review, adjust (warmth + exposure), approve, render, publish — while the CLI remains a fully supported, unchanged frontend over the same on-disk state.

Personal, private use only. Self-signed. One user, one machine, one repo.

## 2. Global constraints

- **macOS 15 (Sequoia) minimum.** Built with Xcode 26.3, Swift 6.2.4, SwiftUI. No third-party UI dependencies.
- **Pipeline changes are additive only.** All existing CLI invocations behave byte-for-byte as today when `--json` is absent. The existing test suite (171 tests) keeps passing unmodified.
- **No pipeline logic in Swift.** The app never computes state transitions, fingerprints, crops, or file layouts. It shells out to `python -m pipeline` and renders what the pipeline reports.
- **Disk is the single source of truth.** Sliders write the same `sidecars/<stem>_<style>.pp3` files a human would; approvals, audits, and crops persist via `pipeline approve`; the app holds no state that isn't reconstructible from `status --json`.
- **Concurrency between frontends** is arbitrated by the pipeline's existing `run/` lockfile. The app never bypasses or deletes it.
- **Dark-only.** The app forces dark appearance (`.preferredColorScheme(.dark)` at the window root); there is no light mode.

## 3. Out of scope

- Redistribution: no notarization, no App Store, no sandboxing (the app needs plain filesystem access to the repo), no Sparkle updates. Ad-hoc/self-signed Debug and Release builds only.
- Edit controls beyond the two sliders (no curves, crops-from-scratch, spot edits — Claude/CLI own those via sidecars).
- In-app RAW decoding or color management beyond displaying the pipeline's sRGB preview JPGs.
- Multi-repo / multi-library support. The repo path is a Settings field, singular.
- Localization (English only), light mode, iPad/Catalyst.
- Print-lab integration (still deferred at the pipeline level).

## 4. Architecture

```
┌────────────────────────────┐   ┌──────────────────────────┐
│ RAWdog Printworks.app      │   │ CLI (unchanged)          │
│  SwiftUI views             │   │ scripts/process.sh       │
│  AppModel (@Observable)    │   │ python -m pipeline ...   │
│  PipelineClient (actor)    │   └────────────┬─────────────┘
│  RepoWatcher (FSEvents)    │                │
└──────────────┬─────────────┘                │
               │ spawns `python -m pipeline <cmd> --json`
               ▼                              ▼
┌─────────────────────────────────────────────────────────────┐
│ Pipeline engine (existing Python; additive JSON interface)  │
│ state machine · locking · fingerprints · render · publish   │
└──────────────┬──────────────────────────────────────────────┘
               ▼
   Input/  previews/  sidecars/  recipes/  Output/  run/
```

### 4.1 Components (Swift)

| Unit | Responsibility | Depends on |
|---|---|---|
| `PipelineClient` (actor) | Spawn `python -m pipeline` subprocesses; stream NDJSON progress events; decode the final envelope; serialize actions (one mutating command at a time). | Foundation `Process` |
| `AppModel` (`@Observable`) | The app's single state tree: decoded `status` snapshot, per-photo draft review state (audit checkboxes, crop nudges, unsaved slider values), progress of the running command. | `PipelineClient`, `RepoWatcher` |
| `RepoWatcher` | FSEvents on `Input/`, `previews/`, `sidecars/`, `recipes/`, `Output/`; coalesces bursts (500 ms) and triggers a `status --json` refresh. | FSEvents |
| `SidecarWriter` | Merge warmth/exposure values into `sidecars/<stem>_<style>.pp3`, preserving unrelated sections; identical format to hand-written sidecars. | none |
| Views | `MainWindow` (NavigationSplitView), `GridView`, `ReviewView`, `InspectorView`, `CompareView`, `CropOverlayView`, `ProgressHUD`, `SettingsSheet`, `EmptyDropView`. | `AppModel` |

Each view reads `AppModel`; only `AppModel` talks to `PipelineClient`. Every mutating action follows the same cycle: **spawn → stream progress → final envelope → `status --json` refresh**. The UI is never updated speculatively.

### 4.2 Pipeline additions (Python)

New flags/commands in `pipeline/__main__.py` (plus a small `pipeline/jsonio.py` helper). All additive:

1. **`--json` output mode** on `ingest`, `preview`, `approve`, `run`, `status`. Stdout becomes NDJSON: zero or more *event lines*, then exactly one *final envelope* line. Human-readable output moves to stderr in this mode.
2. **`status` command** (new): full machine-readable state; no side effects; does not take the lock.
3. **`preview --stem <stem> --style <style>`**: re-render one preview JPG (the slider loop). Without the new flags, `preview` behaves as today.
4. **`approve --stem <stem> --review-file <path>`**: reads audit entries and optional crop overrides from a JSON file (below) instead of interactive/args input. Existing invocation forms keep working.

### 4.3 JSON contract

**Final envelope** (exactly one line, last line of stdout):

```json
{"ok": true, "result": { ... }}
{"ok": false, "error": {"code": "LOCK_HELD", "message": "pipeline is busy (pid 4242)"}}
```

Error codes (closed set, growable): `LOCK_HELD`, `TOOLCHAIN_FAILED`, `RENDER_FAILED`, `VERIFY_FAILED`, `INVALID_STATE`, `NOT_FOUND`, `BAD_INPUT`, `INTERNAL`.

**Progress event lines** (zero or more, before the envelope):

```json
{"event": "progress", "stem": "P1036163", "stage": "render", "style": "filmic", "artifact": "8x10_tif", "index": 14, "total": 29}
{"event": "stage", "stem": "P1036163", "stage": "verify"}
```

Consumers must ignore unknown event types and unknown fields (forward compatibility).

**`status --json` result** (sketch; authoritative schema lives in the pytest golden fixtures):

```json
{
  "repo": "/Users/john/photo-edits",
  "toolchain": {"ok": true, "failures": []},
  "lock": {"held": false, "pid": null},
  "styles": ["natural", "filmic", "bw", "vibrant"],
  "photos": [
    {
      "stem": "P1036163",
      "state": "review_required",
      "captured_at": "2026-08-09T18:42:07-04:00",
      "previews": {"natural": "previews/P1036163_natural_preview.jpg", "...": "..."},
      "sidecars": {"natural": null, "...": "..."},
      "crops": {"8x10": {"x": 0.09, "y": 0.02, "w": 0.75, "h": 0.96}, "5x7": {"...": "..."}},
      "expression_audit": [],
      "published": {"version": null, "path": null, "artifact_count": null}
    }
  ]
}
```

Paths are repo-relative. Crop windows are normalized [0,1] floats, matching `pipeline/geometry.py`.

**`--review-file` input** (written by the app to a temp file):

```json
{
  "expression_audit": [
    {"check": "eyes_open_all", "result": "pass", "note": ""},
    {"check": "expressions_natural", "result": "pass", "note": ""},
    {"check": "no_blinks_in_crops", "result": "pass", "note": ""}
  ],
  "crops": {"8x10": {"x": 0.10, "y": 0.02, "w": 0.75, "h": 0.96}}
}
```

`crops` is optional; omitted crops keep the pipeline's subject-centered defaults. Validation (aspect, bounds, min resolution) stays in `pipeline/geometry.validate_crop` — the app only nudges positions.

## 5. UI design

### 5.1 Visual language

- **Black primary.** Window base `#0A0A0B`; review canvas pure black. Panels `#141416`, hairlines `#232326`.
- **Accent: amber `#E8A849`** — used for selection, status "needs review", slider thumbs, the Approve button, progress fills. Semantic greens/ambers/grays for state dots (published/review/ingested).
- Sidebar uses `.ultraThinMaterial` translucency over the black window.
- SF Pro (system), SF Symbols, 8–10 px card radii, generous spacing. Contemporary and quiet: no toolbars full of buttons, no chrome that competes with photographs.

### 5.2 Window structure (locked: A+C hybrid)

`NavigationSplitView` with translucent sidebar + content area with two states:

- **Sidebar — Browse level:** deliveries (a delivery = an ingest batch, labeled by ingest date), each with photo/review counts; below, a small pipeline block (toolchain OK, idle/busy).
- **Sidebar — Review level:** the open delivery's photos with 42 px thumbnails and state dots.
- **Content, state 1 — Grid:** `LazyVGrid` of photo cards (preview thumb, status badge, render-progress overlay while running). Double-click → Review.
- **Content, state 2 — Review:** large preview; style segmented control; inspector column (fixed 260 pt) on the right.
- **Toolbar:** delivery name, needs-review count, compact progress bar, Reprocess menu (this photo / all photos — mirrors CLI re-render), Grid/Review toggle.
- **Empty state:** full-window drop target: "Drop RAW files to start a delivery."

### 5.3 Review interactions

| Interaction | Behavior |
|---|---|
| `⌘1`–`⌘4` / segmented control | Switch style (natural, filmic, bw, vibrant — pipeline order). |
| `space` | Compare mode: 2×2 grid of all four style previews; click a panel to zoom back into that style. |
| `C` | Crop overlay: draw the 8×10 (solid) and 5×7 (dashed) windows from `status` over the preview; drag a window to nudge it (clamped to bounds, aspect locked). Nudges live in the app's draft until Approve. |
| `←` / `→` | Previous / next photo in the delivery. |
| Sliders | Warmth: absolute Kelvin, 3000–9000 K; initial position = the sidecar's `Temperature` if one exists, else marked "As shot" (untouched = no sidecar WB section written). Exposure: −1.00…+1.00 EV, written as absolute `Compensation`. Both per photo × style; `SidecarWriter` produces the same `[White Balance]`/`[Exposure]` sections as the hand-written sidecars. On change: 2 s debounce → sidecar merge → `preview --stem --style --json` → FSEvents refreshes the canvas. A subtle "rendering preview…" shimmer overlays the canvas while the re-render runs. |
| Audit checklist | Three required checks (eyes open, expressions natural, no blinks in crops) + free-text note field; stored in the draft; written via `--review-file` on Approve. |
| Approve button | Enabled only when all audit checks are marked. Runs `approve --review-file` then `run --stem` (render → verify → publish) as one chained action with streamed progress. |

### 5.4 Ingest

Drag RAW files or a folder anywhere onto the window: the app copies `.rw2`/`.RW2` files into `Input/` (skip-with-notice on duplicate stems), then runs `ingest --json` followed by preview generation. Files that appear in `Input/` by other means (Finder, CLI) are detected by `RepoWatcher` and surface as a banner: "2 new RAW files — Ingest now?"

### 5.5 Settings

One sheet, two fields: repo path (default `~/photo-edits`), python interpreter path (default `<repo>/.venv/bin/python`). Both validated live (repo must contain `pipeline/`; python must import the pipeline). Nothing else.

## 6. Data flow

1. **Launch:** validate settings → `status --json` → populate `AppModel` → start `RepoWatcher`.
2. **Ingest:** drop → copy to `Input/` → `ingest --json` (events stream into per-card progress) → refresh.
3. **Slider:** UI value → debounce → sidecar write → `preview` → JPG replaced on disk → watcher event → canvas reloads image (cache-busted by file mtime).
4. **Approve chain:** draft (audit + crop nudges) → temp review-file → `approve --json` → on success `run --stem --json` → progress events drive card + toolbar bars → envelope → refresh → native notification "P1036163 published (v4, 29 files)".
5. **External change (CLI ran, file dropped in Input/):** FSEvents → coalesce 500 ms → `status --json` → diff → UI updates. No refresh button exists.

The `PipelineClient` actor serializes mutating commands (ingest/preview/approve/run) into a FIFO queue; `status` may run concurrently. If the pipeline lockfile is held externally, actions return `LOCK_HELD` and the app shows a persistent "Pipeline busy (CLI)" pill until a later `status` shows the lock released.

## 7. Error handling

- **Uniform surface:** any `ok:false` envelope → banner with `message` in plain language, a "Show Details" disclosure (last 50 lines of stderr), and — where the code warrants it — one action button: Retry (`RENDER_FAILED`, `VERIFY_FAILED`, `INTERNAL`), Open Settings (`TOOLCHAIN_FAILED`, launch validation failures). After every failure the app re-runs `status --json`; the UI always converges to disk truth.
- **`LOCK_HELD`:** not an error banner — the busy pill (§6). Mutating controls disable; browsing stays fully usable.
- **Process-level failures** (python not found, non-JSON final line, crash): mapped to a synthetic `INTERNAL` envelope with captured stderr. Non-zero exit with a valid envelope trusts the envelope.
- **Partial renders:** publish is atomic in the pipeline (vNNN + symlink swap on verified only), so a failed render leaves the card in its prior state with a "render failed" badge and Retry. No cleanup logic in the app.
- **Watcher storms** (regeneration touches hundreds of files): 500 ms coalescing + a `status` call already in flight suppresses re-entry; at most one trailing refresh queues.
- **Stale preview during slider loop:** preview re-render failures restore the previous JPG display and surface the banner; the sidecar keeps the user's values (disk truth = what will render).

## 8. Testing

- **Pipeline (pytest, added to the existing suite):** envelope shape on success/failure for each command; progress-event line format; `status --json` schema (round-trips real repo states: empty, ingested, review_required, published); `--review-file` parsing incl. crop validation rejects; `preview --stem --style` renders exactly one JPG; `--json` absent ⇒ output identical to today (regression guard).
- **Contract golden fixtures:** pytest writes canonical outputs for a fixture repo to `tests/fixtures/json_contract/*.json`. An Xcode build phase copies these into the app test bundle; XCTest decodes every fixture with the production `Codable` models. Contract drift breaks one side's tests immediately.
- **Swift (XCTest):** `PipelineClient` NDJSON stream parsing (events + envelope, malformed lines, interleaved stderr); `SidecarWriter` merge preserves unrelated pp3 sections (fixtures copied from real sidecars); `AppModel` reducers (draft state, approve enablement, busy pill logic).
- **Smoke test:** a scripted fixture repo (tiny fake previews, no RawTherapee) exercises launch → grid → review → slider write → approve-disabled/enabled logic with a stub `python` that replays fixture envelopes.
- **Visual QA (done-criteria, per the Predictor lesson):** screenshots of grid, review, compare, crop overlay, progress, and error banner states on the real repo, reviewed by eye before the app is called done. Green tests alone are insufficient.

## 9. Repo layout

```
app/RAWdogPrintworks/            Xcode project (committed)
  RAWdogPrintworks/              sources (Views/, Model/, Pipeline/)
  RAWdogPrintworksTests/         XCTest + copied golden fixtures
pipeline/jsonio.py               envelope + event emission helper
tests/fixtures/json_contract/    canonical JSON fixtures (pytest-generated)
```

Build/run: open in Xcode, ⌘R. Release build ad-hoc signed (`codesign --force --sign -`), copied to /Applications by hand. No CI changes.
