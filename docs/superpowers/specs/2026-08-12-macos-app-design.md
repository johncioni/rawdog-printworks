# RAWdog Printworks — macOS App Design

**Date:** 2026-08-12
**Status:** Draft for review (rev 3 — post Codex review round 2)
**Depends on:** `2026-08-11-raw-print-pipeline-design.md` (rev 8) — the pipeline this app fronts.

## 1. Goal

A native macOS app, **RAWdog Printworks**, that puts a contemporary, black-primary UI on the existing RAW print pipeline. The app covers the full workflow — ingest, preview, review, adjust (warmth + exposure), approve, render, publish — while the CLI remains a fully supported, unchanged frontend over the same on-disk state.

Personal, private use only. Self-signed. One user, one machine, one repo.

## 2. Global constraints

- **macOS 15 (Sequoia) minimum.** Built with Xcode 26.3, Swift 6.2.4, SwiftUI. No third-party UI dependencies.
- **Pipeline changes are additive only.** All existing CLI invocations behave byte-for-byte as today when the new flags are absent (the one deliberate exception: mutating commands gain lock acquisition, below). The existing test suite (171 tests) keeps passing unmodified.
- **No pipeline logic in Swift, no repo writes from Swift.** The app never computes state transitions, fingerprints, crops, or pp3 merges, and never writes inside the repo — not even `Input/`. Dropped RAW files are handed to `ingest --from` (§4.2), which copies them under the lock. The only Swift-written file is the temp review-file passed to `approve`, created outside the repo.
- **Every mutating CLI entry point takes the driver lock** — the new commands (`adjust`, targeted `preview`, `ingest --from`) *and* the existing `ingest`, `preview`, `render`, `verify`, `croppreview`, `approve`, `run` — acquired exactly once at dispatch in `__main__.py`. `status` and `crops` are read-only and lock-free. The app never bypasses or deletes the lock.
- **Disk is the single source of truth for pipeline state.** The app holds no pipeline state that isn't reconstructible from `status --json`. (Unsubmitted user input — unchecked audit boxes, un-approved crop nudges — is transient UI draft state, not pipeline state; see §6.1.)
- **Dark-only.** The app forces dark appearance (`.preferredColorScheme(.dark)` at the window root); there is no light mode.

## 3. Out of scope

- Redistribution: no notarization, no App Store, no sandboxing (the app needs plain filesystem access to the repo), no Sparkle updates. Ad-hoc/self-signed Debug and Release builds only.
- Edit controls beyond the two sliders (no curves, crops-from-scratch, spot edits — Claude/CLI own those via hand-written sidecars, which remain fully supported).
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
| `PipelineClient` (actor) | Spawn `python -m pipeline` subprocesses; stream NDJSON progress events; decode the final envelope; serialize mutating commands (FIFO, one at a time). Environment: `currentDirectoryURL` = repo path; python invoked by absolute path from Settings; `PATH` explicitly set to `/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin` (Finder-launched apps don't inherit shell env; the toolchain probes tools via `PATH`); no shell interpolation, argv only. | Foundation `Process` |
| `AppModel` (`@Observable`) | The app's single state tree: decoded `status` snapshot, per-photo review drafts (§6.1), progress of the running command. | `PipelineClient`, `RepoWatcher` |
| `RepoWatcher` | FSEvents on `Input/`, `previews/`, `sidecars/`, `recipes/`, `Output/`, and `run/` (lock transitions); coalesces bursts (500 ms) and triggers a `status --json` refresh. While `lock.held` by an external process, additionally polls `status` every 5 s so a no-op CLI run can't leave the busy pill stuck. | FSEvents |
| Views | `MainWindow` (NavigationSplitView), `GridView`, `ReviewView`, `InspectorView`, `CompareView`, `CropOverlayView`, `ProgressHUD`, `SettingsSheet`, `EmptyDropView`. | `AppModel` |

Each view reads `AppModel`; only `AppModel` talks to `PipelineClient`. Every mutating action follows the same cycle: **spawn → stream progress → final envelope → `status --json` refresh**. The UI is never updated speculatively.

### 4.2 Pipeline additions (Python)

All additive, in `pipeline/__main__.py` plus a small `pipeline/jsonio.py` (envelope/event emission). Exact command grammar (bracketed = optional; all new commands support `--json`; existing invocation forms keep working unchanged except for lock acquisition per §2):

| Command | Semantics |
|---|---|
| `status --json` | Read-only, lock-free, side-effect-free snapshot (§4.3). Reports a crash-stale lock (PID not alive) as `held: false, stale: true` without deleting it. Snapshot coherence: after assembling the result, `status` re-stats the recipe/manifest files it read and retries once (100 ms) if any changed mid-read; residual cross-file staleness is acceptable because every mutation ends in an FSEvents-triggered refresh that converges the UI. |
| `ingest [--from PATH ...] [--delivery-id ID] --json` | Existing ingest of `Input/`, plus: `--from` copies external files/folders into `Input/` itself — content-hash dedup (skip), same-stem-different-hash conflict (reject, copy nothing), temp-copy + atomic rename, all under the lock, so a concurrent CLI ingest can never see a half-copied RAW. `--delivery-id` (app-supplied UUID) and an `ingested_at` (UTC RFC 3339, microseconds) are recorded in the new photos' recipes **only when the flag is passed** — flag-less CLI ingest produces byte-identical legacy recipes. |
| `preview --stem S --style Y --json` | Re-render one preview JPG. Renders to a temp file, atomically replaces the target only on success (failure leaves the previous JPG intact). Records decoded render dimensions in the recipe, same as the batch preview path, so approval's crop generation works for any photo previewed this way. Without `--stem/--style`, `preview` behaves exactly as today. |
| `adjust --stem S --style Y [--temperature K] [--exposure EV] [--reset] --json` | Merges values into `sidecars/S_Y.pp3` — `[White Balance]` `Setting=Custom`, `Temperature`, `Green=1.0` (matching the operator contract); `[Exposure]` `Compensation` — preserving all unrelated sections/keys; atomic write; then re-renders that preview. The recipe records which keys the app manages per style (`app_adjustments`); `--reset` removes exactly those keys (and the file if nothing else remains), so a hand-written sidecar the app never touched is never altered by reset. Only flags actually passed are written. |
| `crops --stem S --json` | Read-only: the crop windows the pipeline would use — persisted windows from the recipe if present, else freshly computed subject-centered suggestions (not persisted). Each window carries `"source": "persisted" \| "suggested"` and the result carries `"basis": "faces" \| "center" \| "detector_error"` — a Vision failure falls back to centered windows and says so, never masquerading as a face-based suggestion. |
| `approve --stem S --review-file P --json` | Reads audit entries + crop windows from the JSON file (§4.3). **Validates both supplied windows** via `geometry.validate_crop` against the recipe's recorded render dimensions *before* persisting anything (audit, crops, fingerprint, manifest). If the review-file carries `expected_review_revision` and it doesn't match the current computed revision (§4.3), fails with `STALE_REVIEW` and changes nothing. |
| `run [--stem S] [--force] --json` | Existing full run (advances every photo as far as the state machine legally allows — ingested photos get previews and stop at `review_required`; approved photos render → verify → publish), plus: `--stem` restricts to one photo; `--force` re-renders even from rendered/verified (the Reprocess menu). Render-time staleness and fingerprint re-verification behave exactly as today — an `adjust` after approval stales the fingerprint and `run` refuses that photo with `INVALID_STATE` until re-approved. |

**Atomic state writes:** recipe and manifest saves switch from in-place writes to write-temp + `os.replace` (additive hardening; behavior otherwise identical).

### 4.3 JSON contract

Stdout in `--json` mode is NDJSON: zero or more *event lines*, then exactly one *final envelope* line (always the last line). Human-readable output moves to stderr. **Exit code is 0 iff the envelope says `ok: true`**; the envelope is authoritative when both are present. Any unhandled exception maps to `{"ok": false, "error": {"code": "INTERNAL", ...}}`.

**Final envelope:**

```json
{"ok": true, "result": { ... }}
{"ok": false, "error": {"code": "LOCK_HELD", "message": "pipeline is busy (pid 4242)"}}
```

Error codes (closed set, growable): `LOCK_HELD`, `TOOLCHAIN_FAILED`, `RENDER_FAILED`, `VERIFY_FAILED`, `INVALID_STATE`, `STALE_REVIEW`, `NOT_FOUND`, `BAD_INPUT`, `INTERNAL`.

**Progress events** (all fields required unless marked; consumers ignore unknown event types and fields):

```json
{"event": "stage",    "stem": "P1036163", "stage": "render"}
{"event": "progress", "stem": "P1036163", "stage": "render", "index": 14, "total": 29, "detail": "filmic 8x10 tif"}
```

`stage` ∈ `ingest | preview | render | verify | publish`. `index`/`total` are 1-based and scoped to the named `stage` of the named `stem` (`progress` for `render` counts artifacts 1–29; a multi-photo `run` emits independent sequences per stem). There is no terminal event — the envelope is the terminus. Per-card UI progress keys off `stem`; the toolbar shows the active stem + stage.

**Per-command `result` payloads** (authoritative schemas live in the pytest golden fixtures; sketches):

- `ingest`: `{"ingested": ["P1036171"], "skipped": [{"file": "P1036163.RW2", "reason": "duplicate content"}], "conflicts": [{"file": "...", "reason": "stem exists with different content"}]}` — partial success is `ok: true` with non-empty `skipped`/`conflicts`; the app surfaces both lists.
- `preview` / `adjust`: `{"stem": "...", "style": "...", "preview": "previews/..._preview.jpg", "temperature": {"value": 5700, "source": "sidecar"}, "exposure": {"value": 0.12, "source": "sidecar"}}` (effective post-merge values).
- `crops`: `{"stem": "...", "basis": "faces", "windows": {"8x10": {"x": 0.09, "y": 0.02, "w": 0.75, "h": 0.96, "source": "suggested"}, "5x7": {...}}}`
- `approve`: `{"stem": "...", "state": "approved", "fingerprint": "sha256:..."}`
- `run`: `{"published": [{"stem": "...", "version": "v004", "artifact_count": 29}], "advanced": [{"stem": "...", "state": "review_required"}], "failed": [{"stem": "...", "code": "VERIFY_FAILED", "message": "..."}]}` — `ok: true` iff `failed` is empty.
- `status`:

```json
{
  "repo": "/Users/john/photo-edits",
  "toolchain": {"ok": true, "failures": []},
  "lock": {"held": false, "stale": false, "pid": null},
  "styles": ["natural", "filmic", "bw", "vibrant"],
  "photos": [
    {
      "stem": "P1036163",
      "state": "review_required",
      "delivery_id": "b3e9…-uuid",               // null for recipes ingested without --delivery-id → grouped as "Earlier"
      "ingested_at": "2026-08-11T13:14:02.123456Z", // null likewise
      "review_revision": "sha256:…",               // hash over recipe content + sidecar/preview mtimes for this stem (§6.1)
      "previews": {"natural": "previews/P1036163_natural_preview.jpg", "...": "..."},
      "adjustments": {"natural": {"temperature": {"value": 5700, "source": "sidecar"},
                                    "exposure":    {"value": 0.12,  "source": "sidecar"}},
                       "filmic":  {"temperature": {"value": 5650, "source": "style"},
                                    "exposure":    {"value": null,  "source": "style"}},
                       "bw":      {"temperature": {"value": null,  "source": "camera"},
                                    "exposure":    {"value": 0.15,  "source": "sidecar"}}},
      "crops": {"8x10": {"x": 0.09, "y": 0.02, "w": 0.75, "h": 0.96}},   // persisted only; {} before approval
      "expression_audit": ["eyes open — all: pass", "..."],
      "published": {"version": "v003", "path": "Output/photos/P1036163/current", "artifact_count": 29}
    }
  ]
}
```

`adjustments` reports the *effective* value and its origin **per control** (temperature and exposure inherit independently — an exposure-only sidecar reports `camera` WB + `sidecar` exposure): `"sidecar"` = per-image override, `"style"` = the style profile's pinned value, `"camera"` = as-shot (no fixed Kelvin — the slider shows "As shot" until touched). Paths repo-relative; crop windows normalized [0,1], matching `pipeline/geometry.py`.

**`--review-file` input** (written by the app to a temp file outside the repo; deleted after the envelope):

```json
{
  "expected_review_revision": "sha256:…",
  "expression_audit": [
    "eyes open — all: pass",
    "expressions natural: pass",
    "no blinks in crops: pass",
    "note: dad mid-laugh in 5x7 — intentional keep"
  ],
  "crops": {"8x10": {"x": 0.10, "y": 0.02, "w": 0.75, "h": 0.96}, "5x7": {"x": 0.02, "y": 0.07, "w": 0.89, "h": 0.86}}
}
```

`expression_audit` is a **list of strings** — the exact format already durable in `recipes/*.yaml` and written by the CLI flow. The app composes the strings from its checklist + note field; existing recipes need no migration and the CLI review loop is unaffected. Both crop windows are required (the app always has them via `crops`/`status`). `expected_review_revision` is optional (the CLI may omit it); the app always sends it.

## 5. UI design

### 5.1 Visual language

- **Black primary.** Window base `#0A0A0B`; review canvas pure black. Panels `#141416`, hairlines `#232326`.
- **Accent: amber `#E8A849`** — selection, "needs review" status, slider thumbs, Approve button, progress fills. Semantic greens/ambers/grays for state dots (published/review/ingested).
- Sidebar uses `.ultraThinMaterial` translucency over the black window.
- SF Pro (system), SF Symbols, 8–10 px card radii, generous spacing. Contemporary and quiet: no toolbars full of buttons, no chrome that competes with photographs.

### 5.2 Window structure (locked: A+C hybrid)

`NavigationSplitView` with translucent sidebar + content area with two states:

- **Sidebar — Browse level:** deliveries (grouped by `delivery_id`; photos without one under "Earlier"), each with photo/review counts; below, a small pipeline block (toolchain OK, idle/busy).
- **Sidebar — Review level:** the open delivery's photos with 42 px thumbnails and state dots.
- **Content, state 1 — Grid:** `LazyVGrid` of photo cards (preview thumb, status badge, render-progress overlay while running). Double-click → Review.
- **Content, state 2 — Review:** large preview; style segmented control; inspector column (fixed 260 pt) on the right.
- **Toolbar:** delivery name, needs-review count, compact progress bar, Reprocess menu (this photo / all photos → `run --stem --force` / `run --force`), Grid/Review toggle.
- **Empty state:** full-window drop target: "Drop RAW files to start a delivery."

### 5.3 Review interactions

| Interaction | Behavior |
|---|---|
| `⌘1`–`⌘4` / segmented control | Switch style (natural, filmic, bw, vibrant — pipeline order). |
| `space` | Compare mode: 2×2 grid of all four style previews; click a panel to zoom back into that style. |
| `C` | Crop overlay: windows from `crops --stem` (suggested, with `basis` shown when not face-based) or `status` (persisted) drawn over the preview — 8×10 solid, 5×7 dashed; drag to nudge (clamped to bounds, aspect locked). Nudges live in the review draft until Approve. |
| `←` / `→` | Previous / next photo in the delivery. |
| Sliders | Warmth: absolute Kelvin 3000–9000, initialized from `status.adjustments` (shows "As shot" for `source: camera` until touched). Exposure: −1.00…+1.00 EV. Per photo × style. On change: 2 s debounce → `adjust --stem --style` with only the changed control(s) (pipeline writes the sidecar and re-renders the preview) → FSEvents refreshes the canvas. "Rendering preview…" shimmer while the command runs; a Reset control issues `adjust --reset`. |
| Audit checklist | Three required checks (eyes open, expressions natural, no blinks in crops) + free-text note; held in the review draft; serialized to audit strings in the review-file on Approve. |
| Approve button | Enabled when all checks are marked **and** the draft isn't stale (§6.1). First flushes any pending slider debounce (issues the outstanding `adjust` and waits — the FIFO guarantees ordering), then runs `approve --review-file` (with `expected_review_revision`) then `run --stem`, one chained action with streamed progress. |

### 5.4 Ingest

Drag RAW files or a folder anywhere onto the window: the app passes the dropped paths to `ingest --from <paths> --delivery-id <fresh UUID> --json` — the pipeline performs the copy, hash dedup, and stem-conflict rejection under the lock (§4.2), then the app chains `run` so new photos get previews and land at `review_required` ready for review. `skipped` and `conflicts` from the result are surfaced ("P1036163.RW2 already exists with different content — nothing copied; resolve via CLI rename"). Files that appear in `Input/` by other means (Finder, CLI) are detected by `RepoWatcher` and surface as a banner: "2 new RAW files — Ingest now?" (which runs plain `ingest --delivery-id <uuid>` + `run`).

### 5.5 Settings

One sheet, two fields: repo path (default `~/photo-edits`), python interpreter path (default `<repo>/.venv/bin/python`). Both validated live by running `status --json` with the candidate values (repo must contain `pipeline/`; the probe uses the same environment rules as §4.1). Nothing else.

## 6. Data flow

1. **Launch:** validate settings → `status --json` → populate `AppModel` → start `RepoWatcher`.
2. **Ingest:** drop → `ingest --from … --delivery-id …` (copy/dedup/conflicts pipeline-side, events stream into per-card progress) → `run` (previews render; photos land at `review_required`) → refresh.
3. **Slider:** UI value → debounce → `adjust` (lock, sidecar merge, preview re-render all pipeline-side) → envelope → watcher event → canvas reloads image (cache-busted by file mtime).
4. **Approve chain:** flush pending `adjust` → review draft (audit + crop windows + `expected_review_revision`) → temp review-file → `approve --json` → on success `run --stem --json` → progress events drive card + toolbar bars → envelope → refresh → native notification "P1036163 published (v4, 29 files)".
5. **External change (CLI ran, file dropped in Input/):** FSEvents → coalesce 500 ms → `status --json` → diff → UI updates. No refresh button exists.

`PipelineClient` serializes mutating commands into a FIFO queue; `status`/`crops` may run concurrently with them. If the lockfile is held externally, mutating actions return `LOCK_HELD` → the app shows a persistent "Pipeline busy (CLI)" pill (not an error banner), disables mutating controls, keeps browsing fully usable, and clears the pill via lock-release FSEvents, the 5 s fallback poll, or `status` reporting the lock stale (dead PID).

### 6.1 Review drafts

A draft (audit checkboxes, note, crop nudges — slider values are *not* drafts; they commit to disk via `adjust` on debounce) is transient UI state keyed to the photo's `review_revision` from the `status` snapshot it was started against. `review_revision` covers recipe content plus sidecar and preview mtimes, so it moves on *any* input change — including a CLI sidecar edit that `recipe_mtime` alone would miss. On every refresh: if it changed externally (not as the result of the app's own queued command), the draft is marked **stale** — contents preserved, banner shown ("This photo changed on disk — re-check before approving"), Approve disabled until the user re-confirms the checklist against the fresh state. `approve` independently enforces the same thing pipeline-side via `expected_review_revision` → `STALE_REVIEW`, so a race that slips past the UI still can't approve unseen pixels. Drafts are dropped on app quit by design.

## 7. Error handling

- **Uniform surface:** any `ok:false` envelope → banner with `message` in plain language, a "Show Details" disclosure (last 50 lines of stderr), and — where the code warrants it — one action button: Retry (`RENDER_FAILED`, `VERIFY_FAILED`, `INTERNAL`), Open Settings (`TOOLCHAIN_FAILED`, launch validation failures), Re-review (`STALE_REVIEW` — refreshes and reopens the draft). After every failure the app re-runs `status --json`; the UI always converges to disk truth.
- **`LOCK_HELD`:** the busy pill (§6), never a banner.
- **Process-level failures** (python not found, no valid final envelope line, crash): mapped to a synthetic `INTERNAL` envelope with captured stderr. Non-zero exit with a valid envelope trusts the envelope.
- **Partial renders:** publish is atomic in the pipeline (vNNN + symlink swap on verified only); a failed render leaves the card in its prior state with a "render failed" badge and Retry (`run --stem`). Multi-photo `run` failures are per-stem in `result.failed`; successes still publish.
- **Preview re-render failure:** the pipeline's temp-file + atomic-replace (§4.2) guarantees the previous JPG survives; the app surfaces the banner. The sidecar retains the user's values (disk truth = what will render) and the stale-preview mismatch is exactly what `review_revision` + `STALE_REVIEW` guard against at approval.
- **Watcher storms** (regeneration touches hundreds of files): 500 ms coalescing; a `status` call already in flight suppresses re-entry; at most one trailing refresh queues.

## 8. Testing

- **Pipeline (pytest, added to the existing suite):** envelope shape + exit-code rule on success/failure for each command; progress-event format and 1-based/stage-scoped counting; `status --json` schema round-tripping real repo states (empty, ingested, review_required, published, legacy recipe without delivery fields, stale lock with dead PID); `adjust` merge preserves unrelated pp3 sections and hand-written keys (fixtures from real sidecars), writes `Green=1.0`, `--reset` removes only app-managed keys; `crops` suggested/persisted sourcing + `basis` incl. detector-failure fallback; `--review-file` parsing: crop validation against recorded dimensions rejects bad windows before any persistence, audit-string passthrough, `STALE_REVIEW` on revision mismatch; `preview --stem --style` atomic replace (failure keeps prior JPG) + dimension recording; `ingest --from` hash dedup / stem-conflict rejection / atomic copy, `--delivery-id` recording, and flag-less ingest producing byte-identical legacy recipes; `run --stem`/`--force` scoping incl. ingested→review_required advancement; lock acquisition on every mutating entry point; atomic recipe/manifest writes; **no-flag regression guard: every existing invocation's output is byte-identical to today** (modulo lock acquisition).
- **Contract golden fixtures:** pytest writes canonical envelopes/events/status for a fixture repo to `tests/fixtures/json_contract/*.json`. An Xcode build phase copies these into the app test bundle; XCTest decodes every fixture with the production `Codable` models. Contract drift breaks one side's tests immediately.
- **Swift (XCTest):** `PipelineClient` NDJSON stream parsing (events + envelope, malformed lines, stderr interleave, missing envelope → synthetic `INTERNAL`); `AppModel` reducers (draft lifecycle incl. staleness on `review_revision` change and flush-before-approve ordering, approve enablement, busy-pill set/clear incl. poll fallback and stale-lock clearing).
- **Smoke test:** a scripted fixture repo (tiny fake previews, no RawTherapee) with a stub `python` that replays fixture envelopes exercises launch → grid → review → slider → approve-flow enablement.
- **Visual QA (done-criteria, per the Predictor lesson):** screenshots of grid, review, compare, crop overlay, progress, busy pill, stale-draft banner, and error banner on the real repo, reviewed by eye before the app is called done. Green tests alone are insufficient.

## 9. Repo layout

```
app/RAWdogPrintworks/            Xcode project (committed)
  RAWdogPrintworks/              sources (Views/, Model/, Pipeline/)
  RAWdogPrintworksTests/         XCTest + copied golden fixtures
pipeline/jsonio.py               envelope + event emission helper
tests/fixtures/json_contract/    canonical JSON fixtures (pytest-generated)
```

Build/run: open in Xcode, ⌘R. Release build ad-hoc signed (`codesign --force --sign -`), copied to /Applications by hand. No CI changes.

## 10. Review-round decisions

**Round 1** (1 Critical, 11 Major, 2 Minor): all applied except finding 8's `captured_at`, simplified to `ingested_at`/`delivery_id` only (EXIF capture dates add contract surface with no consumer).

**Round 2** (9 Major, 4 Minor): all applied — lock on every mutating entry point (1); ingest chains `run` for previews (2); recipe-tracked `app_adjustments` so `--reset` never touches hand-written keys (3); per-control `{value, source}` (4); `review_revision` + flush-before-approve + `STALE_REVIEW` (5, in lighter form than proposed: one revision token per photo rather than per-style preview revisions — the token covers all per-photo inputs, which is what approval needs); `status` re-stat-and-retry for snapshot reads instead of a full seqlock (6, lighter: residual staleness self-heals via the watcher refresh cycle and cannot corrupt state, only briefly mislabel it); supplied-crop validation before persistence (7); `ingest --from` moves copying/hashing under the lock (8); `--delivery-id` keeps flag-less ingest byte-identical (9); UUID + RFC 3339 UTC (10); stale-lock reporting in `status` (11); `crops.basis` (12); `Green=1.0` (13).
