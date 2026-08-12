# RAW → Print-Ready Pipeline — Design Spec

**Date:** 2026-08-11 (rev 2 — incorporates Codex xhigh review findings)
**Status:** Approved pending user review
**Camera:** Panasonic Lumix DC-GH7 (25 MP Micro Four Thirds, native 4:3, RW2 files)

## Goal

Turn family-photoshoot RW2 files into print-and-frame-ready TIF, JPG, and PDF
outputs, edited in a natural, restrained style — explicitly correcting the
original photographer's over-processed, over-saturated look. Inputs are
pre-selected keepers: every RW2 dropped into `Input/` receives the full
output set. The pipeline must be repeatable as more files arrive over the
coming days.

**PDF role:** PDFs are ancillary deliverables (review, sharing, home
printing). Lab print submissions are JPG (or TIF where a lab accepts it).

## Workflow state machine

Processing is a resumable, multi-phase workflow with an explicit review gate —
not a single blind batch run. Per photo, the manifest tracks:

```
ingested → preview_ready → review_required → approved → rendered → verified
```

- `ingested` — preflight passed, RAW archived with SHA-256.
- `preview_ready` — neutral preview exported for the visual review loop.
- `review_required → approved` — Claude iterates sidecar edits and places
  crop windows by eye; a photo is approved only when all three styles hold up
  visually.
- `rendered` — all 22 outputs generated into staging.
- `verified` — all QA checks passed; outputs atomically published to
  `Output/` and completion recorded.

The driver supports resume: re-running advances each photo from its current
state. Only `verified` photos are complete.

## Output matrix (per photo) — 22 files

| Format | Contents | Count |
|--------|----------|-------|
| TIF | 16-bit sRGB archival masters, native ratio, full native pixels — one per style | 3 |
| JPG | 3 styles × 3 crops (native, 8×10, 5×7) | 9 |
| PDF | Wraps of the 9 JPGs via img2pdf (lossless, no re-encode) | 9 |
| PDF | Style-comparison review sheet (natural / filmic / bw side by side) | 1 |

Naming: `<stem>_<style>[_<crop>].<ext>` — e.g. `P1036163_natural.tif`,
`P1036163_bw_8x10.jpg`. Styles: `natural`, `filmic`, `bw`. Crops: none
(native), `8x10`, `5x7`. Duplicate stems across deliveries are rejected at
ingest (files are renamed `<stem>-2` only with explicit user confirmation).

## Output geometry (exact)

Orientation follows the source image; "8×10" means 4:5 portrait or 10×8
landscape as appropriate. Crop windows are placed by eye per photo and their
geometry recorded in the manifest.

| Output | Pixel policy |
|--------|--------------|
| TIF masters | Native pixels, no resampling, 16-bit, Deflate compression |
| JPG native | Native pixels, no resampling |
| JPG 8×10 | Crop to 4:5, resample to exactly lab-profile PPI × 8×10 in (default 300 PPI → 2400×3000) |
| JPG 5×7 | Crop to 5:7, resample to exactly lab-profile PPI × 5×7 in (default 300 PPI → 1500×2100) |
| PDF (per image) | Page box exactly equals print size (8×10 in, 5×7 in); native-crop PDFs sized at image dimensions ÷ lab PPI |
| Comparison sheet | Letter page, three labeled panels |

Output sharpening is applied **after** the final resample, scaled to final
pixel dimensions. All resampling is downsampling (25 MP exceeds every
target); Lanczos.

## Lab profile (versioned, configurable)

Lab requirements differ (format, PPI, ICC embedding, filename rules, color
correction opt-out), so exports are parameterized by a committed, versioned
lab profile file. First implementation ships one `generic` profile:

```
generic-v1: JPEG q92, sRGB, ICC profile embedded, 300 PPI,
            ASCII filenames ≤ 64 chars, no bleed, full EXIF minus private tags
```

Selecting a real lab later means adding a profile file and re-rendering
affected deliverables — the manifest's dependency tracking (below) makes that
re-render automatic and scoped. A lab-profile change never touches TIF
masters or the RAW archive.

## Three styles

All styles share a corrective base: accurate white balance, recovered
highlights, gentle contrast, automatic lens corrections (embedded MFT
profiles + chromatic aberration removal).

- **natural** — faithful color, true skin tones, restrained saturation
- **filmic** — natural base + subtle warm tone curve, light film character
- **bw** — channel-weighted monochrome, tuned per image for portrait tonality

Denoising is **default-off** but available per image (enabled in a photo's
sidecar if a future high-ISO delivery needs it — ingest preflight flags
ISO > 1600). Deliberately excluded: AI upscaling, skin smoothing / heavy
retouching, HDR or tone-mapped effects, and generative AI expression editing
(opening closed eyes, synthesizing smiles) — synthetic facial texture shows
at print resolution and recreates the over-edited look this project undoes.

## Directory layout

```
photo-edits/
├── Input/                  # drop .rw2 files here
├── Output/TIF|JPG|PDF/     # verified deliverables only (gitignored)
├── archive/                # verbatim RW2 copies + SHA-256 manifest (gitignored)
├── staging/                # per-photo render workspace, atomic-published (gitignored)
├── sidecars/               # per-image, per-style edit recipes (committed)
├── previews/               # visual-review working files (gitignored)
├── config/lab-profiles/    # versioned lab profiles (committed)
├── config/darktable/       # isolated darktable config dir (committed)
├── scripts/process.sh      # driver: ingest / review / render / verify / publish
├── .manifest               # per-photo state + dependency hashes
└── docs/superpowers/specs/
```

## Processing flow per photo

1. **Ingest preflight** — validate camera model, dimensions, orientation,
   lens, ISO, raw mode; reject duplicates; flag anomalies (unexpected body,
   high ISO) rather than silently proceeding. Copy RW2 to `archive/` with
   SHA-256 recorded.
2. **Neutral preview** — quick darktable export for review.
3. **Visual review loop** — Claude inspects exposure, white balance, skin
   tones at full size; adjusts that image's sidecars; re-exports until all
   three styles hold up. Crop windows placed by eye (no clipped heads/hands),
   geometry recorded.
4. **Render to staging** — decode via darktable-cli into per-photo staging:
   TIF masters, then crops → exact-pixel resample → output sharpen → JPG →
   img2pdf PDFs → comparison sheet.
5. **Verify** — full QA suite (below) against staging.
6. **Publish** — atomically move verified artifacts into `Output/`, mark
   `verified` with dependency hashes; stale outputs from prior recipe
   versions are removed on republish.

## Reproducibility

- darktable-cli runs with an **isolated `--configdir`** committed to the
  repo; custom GUI presets disabled; TIFF bit depth, compression, and ICC
  export options passed explicitly on every invocation — never inherited
  from GUI state.
- Tool versions (darktable, lensfun, ImageMagick, img2pdf, exiftool) are
  recorded in the manifest at render time.
- **Manifest invalidation:** completion is keyed on the hash set of every
  rendering input — RAW SHA-256, sidecar hashes, crop geometry, sharpening
  recipe, lab profile version, driver script hash, tool versions. Any change
  re-queues exactly the affected photos/outputs. No boolean "done" flags.
- Renders go to staging and publish atomically; a crash mid-render never
  leaves partial files in `Output/`.

## Expression audit & ranking

During review, every face in every photo is audited per person: closed or
mid-blink eyes, squints, grimaces, awkward smiles, subjects looking away.
Findings are recorded as per-photo notes surfaced alongside the comparison
sheet. Since all inputs are pre-selected keepers, this is **ranking, not
culling** — all photos receive full outputs; when multiple frames of the
same grouping exist, the audit recommends the strongest frame for framing.
Corrections are by selection, not synthesis; manual head/eye compositing
between near-identical frames remains a documented case-by-case option —
never scripted, never generative.

## Tooling

**Install (Homebrew):** darktable (RAW engine), exiftool, ImageMagick,
img2pdf, qpdf, poppler (`pdfimages`). Note: the Homebrew darktable cask is
marked for disabling 2026-09-01 — if unavailable, install the official
darktable .dmg directly (documented fallback; CLI path
`/Applications/darktable.app/Contents/MacOS/darktable-cli`).

**Already installed, roles:** Topaz Photo AI (`tpai` CLI) — optional rescue
pass only; Photoshop 2020 / Affinity / Pixelmator Pro — manual one-off
retouching only, not pipeline tools.

**Decoder fallback (calibration-aware):** darktable 5.6 lists GH7 basic
RawSpeed support (no GH7 WB presets / noise profile yet). If darktable fails
Checkpoint 1, RawTherapee (`.pp3`) or rawpy are fallbacks — but recipes do
not transfer between engines; a fallback means recalibrating all three
styles on the new engine, not swapping a command.

## Checkpoint 1 (gate for all other work)

Install tools, then on one RW2 verify: decode succeeds; colors render
correctly; orientation is honored; lens corrections actually apply (compare
corrected/uncorrected); highlight recovery behaves; and the RW2
aspect/photo-style modes present in current files are handled. Repeat cheaply
for each future delivery's first file.

## QA (per photo, against staging)

- **Images:** exact pixel dimensions per geometry table; bit depth (16 TIF /
  8 JPG); RGB mode; sRGB ICC identity; orientation; nonzero file size;
  DPI tags.
- **PDFs:** `qpdf --check` structural validity; `pdfimages -list` confirms a
  single losslessly-embedded JPEG (no re-encode); page box exactly matches
  intended print size.
- **Visual:** 100 %-zoom pass for sensor dust, critical eye sharpness,
  clipped highlights in faces; expression audit; sharpening judged at final
  output pixels (print-size proofs on screen; a physical test print is the
  gold standard once a lab is chosen).

## Metadata & privacy

Archive copies keep complete EXIF untouched. Lab/share deliverables strip
GPS, camera serial, owner/artist, and other personally identifying tags,
keeping benign capture data (exposure, lens, date).

## Success criteria

- Every Input RW2 reaches `verified`: full 22-file set published, all QA
  checks passed.
- Every face expression-audited with findings noted.
- Skin tones read as natural to a human reviewer; no over-saturation.
- Re-running the driver is idempotent: untouched photos are skipped via
  dependency hashes; changed recipes re-render exactly the affected outputs.
- A second machine with the committed repo + same tool versions reproduces
  byte-equivalent renders (modulo JPEG encoder nondeterminism).
