# RAW → Print-Ready Pipeline — Design Spec

**Date:** 2026-08-11 (rev 3 — resolves Codex second-review findings)
**Status:** Approved pending user review
**Camera:** Panasonic Lumix DC-GH7 (25 MP Micro Four Thirds, native 4:3, RW2 files)

## Goal

Turn family-photoshoot RW2 files into print-and-frame-ready TIF, JPG, and PDF
outputs, edited in a natural, restrained style — explicitly correcting the
original photographer's over-processed, over-saturated look. Inputs are
pre-selected keepers: every RW2 dropped into `Input/` receives the full
output set. The pipeline must be repeatable as more files arrive over the
coming days.

**Deliverable roles:** Lab print submissions are JPG only. TIFs are archival
masters, not lab submissions (a lab-specific TIFF deliverable can be added
later via a lab profile). PDFs are ancillary (review, sharing, home
printing).

## Workflow state machine

Processing is a resumable, multi-phase workflow with an explicit review gate.
Per photo:

```
ingested → preview_ready → review_required → approved → rendered → verified
```

- `ingested` — preflight passed, RAW archived with SHA-256.
- `preview_ready` — neutral preview exported for the visual review loop.
- `review_required → approved` — Claude iterates sidecar edits and places
  crop windows by eye; approval is recorded in the photo's committed recipe.
- `rendered` — all 22 outputs generated into staging.
- `verified` — all QA checks passed; outputs atomically published.

The driver supports resume: re-running advances each photo from its current
state. Only `verified` photos are complete.

## Durable state vs. transient state

**Committed (durable, reproducible):**
- `recipes/<stem>.yaml` — per-photo recipe: RAW SHA-256, normalized crop
  geometry per crop, approval record, expression-audit notes, references to
  the three style sidecars, per-image overrides (e.g. denoise on).
- `sidecars/` — per-image, per-style darktable XMP edit files.
- `config/lab-profiles/` and `config/darktable-seed/` (below).

**Gitignored (transient, derivable):**
- `.manifest` — derived state machine position and cached dependency hashes
  only. Deleting it loses no information; it rebuilds from recipes + outputs.
- `staging/`, `run/`, `previews/`, `Output/`, `archive/`.

## Output matrix (per photo) — 22 files

| Format | Contents | Count |
|--------|----------|-------|
| TIF | 16-bit sRGB archival masters, native ratio, full native pixels — one per style | 3 |
| JPG | 3 styles × 3 crops (native, 8×10, 5×7) | 9 |
| PDF | Wraps of the 9 JPGs via img2pdf (lossless, no re-encode) | 9 |
| PDF | Style-comparison review sheet (natural / filmic / bw side by side) | 1 |

Naming: `<stem>_<style>[_<crop>].<ext>`. Styles: `natural`, `filmic`, `bw`.
Crops: none (native), `8x10`, `5x7`. Duplicate stems across deliveries are
rejected at ingest (renamed `<stem>-2` only with explicit user confirmation).

## Output geometry (exact)

Orientation follows the source image; "8×10" means 4:5 portrait or 10×8
landscape as appropriate. Crop windows are placed by eye per photo; their
normalized geometry lives in the committed recipe.

| Output | Pixel policy |
|--------|--------------|
| TIF masters | Native pixels, no resampling, 16-bit, Deflate compression |
| JPG native | Native pixels, no resampling |
| JPG 8×10 | Crop to 4:5, resample to exactly lab-profile PPI × 8×10 in (default 300 PPI → 2400×3000) |
| JPG 5×7 | Crop to 5:7, resample to exactly lab-profile PPI × 5×7 in (default 300 PPI → 1500×2100) |
| PDF (per image) | Page box exactly equals print size (8×10 in, 5×7 in); native-crop PDFs sized at image dimensions ÷ lab PPI |
| Comparison sheet | Letter page, three labeled panels |

Output sharpening is applied **after** the final resample, scaled to final
pixel dimensions. All resampling is downsampling; Lanczos. Crop framing must
respect the lab profile's safe-edge margin (below) so lab oversizing/trimming
never clips faces.

## Lab profile (versioned, configurable)

Exports are parameterized by a committed, versioned lab profile. First
implementation ships `generic-v1` with every field explicit:

```yaml
# config/lab-profiles/generic-v1.yaml
submission_format: jpeg        # labs receive JPGs only
jpeg_quality: 92
color_space: srgb
embed_icc: true
ppi: 300
lab_color_correction: "off"    # surfaced as an ordering instruction at
                               # order time ("Do Not Color Correct")
safe_edge_percent: 2           # nothing critical within 2% of edges
                               # (labs oversize/trim ~2%)
checkout_crop_review: required # human confirms lab's crop preview at order
max_file_bytes: 26214400       # 25 MB, under common lab upload caps
filename_rules: "ASCII, <= 64 chars"
bleed: none
strip_metadata_beyond_allowlist: true
keep_capture_date: true        # benign for family prints; set false to strip
```

Selecting a real lab later means adding a profile file; artifact-level
dependency tracking re-renders exactly the affected deliverables. A
lab-profile change never touches TIF masters or the RAW archive.

## Three styles

All styles share a corrective base: accurate white balance, recovered
highlights, gentle contrast, automatic lens corrections (embedded MFT
profiles + chromatic aberration removal).

- **natural** — faithful color, true skin tones, restrained saturation
- **filmic** — natural base + subtle warm tone curve, light film character
- **bw** — channel-weighted monochrome, tuned per image for portrait tonality

Denoising is **default-off**, enabled per image in the recipe when needed
(ingest preflight flags ISO > 1600). Deliberately excluded: AI upscaling,
skin smoothing / heavy retouching, HDR effects, and generative AI expression
editing — synthetic facial texture shows at print resolution and recreates
the over-edited look this project undoes.

## Directory layout

```
photo-edits/
├── Input/                      # drop .rw2 files here (gitignored)
├── Output/
│   ├── photos/<stem>/          # canonical: all 22 files, atomic publish unit
│   └── TIF/ JPG/ PDF/          # format views: symlinks into photos/<stem>/
├── archive/                    # verbatim RW2 + SHA-256 manifest (gitignored)
├── staging/                    # per-photo render workspace (gitignored)
├── run/                        # live darktable configdir copies (gitignored)
├── recipes/                    # per-photo durable recipes (committed)
├── sidecars/                   # per-image, per-style XMPs (committed)
├── previews/                   # review working files (gitignored)
├── config/lab-profiles/        # versioned lab profiles (committed)
├── config/darktable-seed/      # immutable config seed (committed)
├── scripts/process.sh          # driver: ingest/review/render/verify/publish
├── .manifest                   # derived state + cached hashes (gitignored)
└── docs/superpowers/specs/
```

## Atomic publication

The atomic unit is the per-photo directory. Staging renders into
`staging/<stem>.tmp/`; after verification it is published with a **single
directory rename** to `Output/photos/<stem>/` (old version renamed aside
first, deleted after success). A crash never exposes a mix of old and new
artifacts in the canonical location.

The format-view directories (`Output/TIF|JPG|PDF/`) are derived symlink
views, regenerated idempotently after every publish and on every driver run;
they are explicitly not covered by the atomicity guarantee, and a stale view
self-heals on the next run.

## Reproducibility

- `config/darktable-seed/` is an **immutable committed seed** (darktablerc
  settings, styles). At run start it is copied into gitignored
  `run/<run-id>/configdir/`; darktable-cli runs against the copy with
  `--library :memory:`. Committed state is never touched by execution or
  version migrations.
- TIFF bit depth, compression, and ICC options are passed explicitly on
  every invocation — never inherited from GUI state.
- Pinned + hash-recorded rendering assets: the sRGB ICC profile used,
  lensfun database version, comparison-sheet font, and tool versions
  (darktable, lensfun, ImageMagick, img2pdf, exiftool) — recorded in the
  manifest at render time.
- **Artifact-level dependency tracking:** every one of the 22 artifacts has
  its own dependency record: e.g. `natural.tif` ← {RAW, natural sidecar,
  darktable seed, tool versions}; `natural_8x10.jpg` adds {crop geometry,
  sharpening recipe, lab profile}; the comparison sheet ← the three native
  JPGs. A crop change re-renders only crops; a natural-sidecar change
  re-renders only natural outputs + the sheet; native TIFs are untouched by
  either.
- Renders go to staging and publish atomically (above).

## Expression audit & ranking

During review, every face in every photo is audited per person: closed or
mid-blink eyes, squints, grimaces, awkward smiles, subjects looking away.
Findings are recorded in the photo's committed recipe and surfaced alongside
the comparison sheet. Since all inputs are pre-selected keepers, this is
**ranking, not culling** — all photos receive full outputs; when multiple
frames of the same grouping exist, the audit recommends the strongest frame
for framing. Corrections are by selection, not synthesis; manual head/eye
compositing between near-identical frames remains a documented case-by-case
option — never scripted, never generative.

## Tooling

**Install (Homebrew):** darktable (RAW engine), exiftool, ImageMagick,
img2pdf, qpdf, poppler (`pdfimages`). The Homebrew darktable cask is marked
for disabling 2026-09-01 — fallback is the official .dmg (CLI at
`/Applications/darktable.app/Contents/MacOS/darktable-cli`).

**Already installed, roles:** Topaz Photo AI (`tpai` CLI) — optional rescue
pass only; Photoshop 2020 / Affinity / Pixelmator Pro — manual one-off
retouching only.

**Decoder fallback (calibration-aware):** darktable 5.6 lists GH7 basic
RawSpeed support (no GH7 WB presets / noise profile yet). If darktable fails
Checkpoint 1, RawTherapee (`.pp3`) or rawpy are fallbacks — recipes do not
transfer between engines; a fallback means recalibrating all three styles.

## Checkpoint 1 (gate for all other work)

Install tools, then on one RW2 verify: decode succeeds; colors render
correctly; orientation is honored; lens corrections actually apply (compare
corrected/uncorrected); highlight recovery behaves; and the RW2 aspect/mode
variants present are handled. Repeat cheaply for each future delivery's
first file.

## QA (per photo, against staging)

- **Images:** exact pixel dimensions per geometry table; bit depth (16 TIF /
  8 JPG); RGB mode; sRGB ICC identity; orientation; nonzero size; DPI tags.
- **PDFs:** `qpdf --check` (syntactic validity only — noted as such);
  `pdfimages -list` for encoding/dimensions; **losslessness proven
  directly** by extracting the embedded JPEG (`pdfimages -j`) and comparing
  its SHA-256 to the source JPG (decoded-pixel-hash comparison as fallback
  if the container alters bytes); page box exactly matches intended size.
- **Metadata allowlist assertion:** deliverables may contain ONLY: ICC
  profile, resolution/DPI, orientation, pixel dimensions, exposure basics
  (shutter, aperture, ISO, focal length, lens model), capture date (per lab
  profile), and optional copyright. Everything else — GPS, serials,
  owner/artist, maker notes, XMP, IPTC, face regions, thumbnails — is
  stripped, and QA asserts its absence (exiftool scan fails on any
  non-allowlisted tag). Archive copies keep complete EXIF untouched.
- **Visual:** 100 %-zoom pass for sensor dust, critical eye sharpness,
  clipped highlights in faces; expression audit; sharpening judged at final
  output pixels (physical test print is the gold standard once a lab is
  chosen).

## Success criteria

- Every Input RW2 reaches `verified`: full 22-file set published, all QA
  checks (including metadata-allowlist assertion and PDF-losslessness proof)
  passed.
- Every face expression-audited with findings recorded in recipes.
- Skin tones read as natural to a human reviewer; no over-saturation.
- Re-running the driver is idempotent; artifact-level dependency hashes
  re-render exactly the affected outputs on any recipe/profile change.
- **Reproduction criterion:** given this repo + the verified RAW archive +
  pinned tool/asset versions, a second machine reproduces renders whose
  decoded pixel hashes match after metadata/timestamp normalization, with
  identical ICC profiles, geometry, and PDF page boxes (semantic
  equivalence — not container-byte equality).
