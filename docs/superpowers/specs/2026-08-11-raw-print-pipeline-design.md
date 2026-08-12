# RAW → Print-Ready Pipeline — Design Spec

**Date:** 2026-08-11 (rev 6 — RawTherapee promoted to primary engine:
plain-text .pp3 profiles make per-image tuning by the operator tractable;
darktable's encoded XMP params do not. darktable becomes the fallback.)
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

- `ingested` — preflight passed (contract below), RAW archived with SHA-256.
- `preview_ready` — neutral preview exported for the visual review loop.
- `review_required → approved` — Claude iterates sidecar edits and places
  crop windows by eye. Approval is recorded in the committed recipe as an
  **approval fingerprint**: a hash over every input that can change rendered
  pixels — the RAW SHA-256, style sidecars, crop geometry, denoise/retouch
  settings, the output-sharpening recipe, the base style profiles and
  RawTherapee config-seed hashes, the rendering entries of `toolchain.lock`
  (rawtherapee-cli, output ICC profile), and the lab profile's
  review-invalidating fields. If any fingerprinted
  input later changes, the photo transitions **backward** to
  `review_required` — nothing is ever published that wasn't visually
  approved in its exact current form.
- `rendered` — all 22 outputs generated into staging.
- `verified` — all QA checks passed; outputs atomically published.

The driver supports resume: re-running advances each photo from its current
state, including backward transitions on fingerprint mismatch. Only
`verified` photos are complete.

### Ingest preflight (contract)

Every input file — not just the first of a delivery — is validated at ingest:
camera make/model, pixel dimensions, orientation, lens, ISO (flag > 1600 for
per-image denoise consideration), raw mode/aspect variant, and duplicate
identity (by content hash and by stem). The archive copy is verified by
re-hashing the destination and comparing to the source SHA-256. Anomalies
(unexpected body, unusual mode) are flagged to the user, not silently
processed. A preflight failure halts that photo with a reported reason;
other photos continue.

## Durable state vs. transient state

**Committed (durable, reproducible):**
- `recipes/<stem>.yaml` — per-photo recipe: RAW SHA-256, normalized crop
  geometry per crop, approval record with approval fingerprint,
  expression-audit notes, references to the three style sidecars, per-image
  overrides (e.g. denoise on).
- `sidecars/` — per-image, per-style RawTherapee `.pp3` override profiles
  (plain text), layered at render time over the committed base style
  profiles in `config/styles/`.
- `config/toolchain.lock` — exact tool versions with binary hashes
  (rawtherapee-cli, ImageMagick, img2pdf, exiftool, qpdf, poppler) and
  rendering asset hashes (output sRGB ICC profile, comparison-sheet font).
  Renders refuse to run if the live toolchain doesn't match the lock;
  updating tools is an explicit, committed lock change.
- `config/lab-profiles/`, `config/styles/`, and `config/rawtherapee-seed/`
  (below).

**Gitignored (transient, derivable):**
- `.manifest` — derived state machine position and cached dependency hashes
  only. Deleting it loses no information: it rebuilds from recipes,
  `toolchain.lock`, and each published photo's `provenance.json`.
- Each published photo version carries a non-deliverable `provenance.json`
  recording the exact input hashes and toolchain that produced it — so
  existing outputs remain attributable even with no cache.
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

**Default crop placement is subject-centered (rev 7):** at approval time,
faces are detected in the rendered natural preview via the macOS Vision
framework (pyobjc bridge); the union of face boxes, padded, defines the
group's center, and the aspect-correct maximal window is positioned so the
group center lands as close to the window center as frame bounds allow.
Fallback to geometric center when no faces are detected. If the padded
group box cannot fully fit the crop aspect, the photo is flagged for
operator attention rather than silently clipping people. Operator-recorded
windows in the recipe always take precedence; the operator visually reviews
every crop before approval either way. Detection runs on already-rendered
previews only — it chooses framing; it never edits pixels.

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
# Field classes drive invalidation:
#   [review]  change re-enters review_required (breaks approval fingerprint)
#   [render]  change re-renders affected artifacts, approval stands
#   [order]   change touches no pixels; affects ordering guidance only
submission_format: jpeg        # [render] labs receive JPGs only
jpeg_quality: 92               # [render]
color_space: srgb              # [review] changes rendered color
embed_icc: true                # [render]
ppi: 300                       # [review] changes resampling + sharpening
lab_color_correction: "off"    # [order] surfaced as ordering instruction
                               # ("Do Not Color Correct")
safe_edge_percent: 2           # [review] nothing critical within 2% of
                               # edges (labs oversize/trim ~2%)
checkout_crop_review: required # [order] human confirms lab crop preview
max_file_bytes: 26214400       # [render] 25 MB, under common upload caps.
                               # An output exceeding this FAILS verification
                               # for manual resolution — quality is never
                               # silently lowered
filename_rules: "ASCII, <= 64 chars"   # [render]
bleed: none                    # [review]
strip_metadata_beyond_allowlist: true  # [render]
keep_capture_date: true        # [render] benign for family prints
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
- **vibrant** (rev 8) — natural base + stronger vibrance (muted colors
  lifted, skin tones explicitly protected) + gentle contrast S-curve.
  Vibrance-driven, never global saturation — restraint is the constraint.
  With four styles the per-photo set is 29 files (4 TIF + 12 JPG + 12 PDF
  + 4-panel comparison sheet); every "22" and "3 styles" elsewhere in this
  spec reads 29/4 from rev 8 onward.

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
│   ├── photos/<stem>/vNNN/     # immutable version dirs (+ provenance.json)
│   ├── photos/<stem>/current   # symlink → vNNN, atomically swapped
│   └── TIF/ JPG/ PDF/          # format views: symlinks through current
├── archive/                    # verbatim RW2 + SHA-256 manifest (gitignored)
├── staging/                    # per-photo render workspace (gitignored)
├── run/                        # live config copies + driver lock (gitignored)
├── recipes/                    # per-photo durable recipes (committed)
├── sidecars/                   # per-image, per-style .pp3 overrides (committed)
├── previews/                   # review working files (gitignored)
├── config/lab-profiles/        # versioned lab profiles (committed)
├── config/styles/              # base style .pp3 profiles (committed)
├── config/rawtherapee-seed/    # immutable RT options seed (committed)
├── scripts/process.sh          # driver: ingest/review/render/verify/publish
├── .manifest                   # derived state + cached hashes (gitignored)
└── docs/superpowers/specs/
```

## Atomic publication

Publishes are **immutable version directories plus an atomic pointer swap**.
Staging renders into `staging/<stem>.tmp/`; after verification it is renamed
into place as `Output/photos/<stem>/vNNN/` (a new, never-reused version
number), then the `current` symlink is replaced atomically (create temp
symlink, `rename(2)` over `current`). The canonical path
`photos/<stem>/current/` therefore always resolves to a complete old version
or a complete new version — never a mixture, never absent once first
published. Prior version directories are pruned only after a successful
swap.

**Startup recovery:** on every driver start, orphaned `staging/*.tmp/`
directories and unpruned old versions are detected and resolved from
manifest/provenance state — a crash at any point leaves the pipeline
resumable without manual repair.

The format-view directories (`Output/TIF|JPG|PDF/`) are derived symlinks
through `current`, regenerated idempotently on every run; they are
explicitly outside the atomicity guarantee and self-heal.

## Reproducibility

- `config/rawtherapee-seed/` is an **immutable committed seed** (RawTherapee
  `options` file). At run start it is copied into gitignored
  `run/<run-id>/xdg/RawTherapee/`, and rawtherapee-cli runs with
  `XDG_CONFIG_HOME` pointed at the copy. Committed state is never touched
  by execution or version migrations.
- rawtherapee-cli is invoked with explicit `-p` profile chains only (base
  style + per-image override) — never `-d` default/GUI profiles — with
  output format, bit depth, and compression passed explicitly on every
  invocation. RawTherapee's CLI renders on CPU, avoiding GPU-kernel
  determinism hazards.
- All tool and asset pinning lives in the committed `config/toolchain.lock`
  (exact versions + binary/asset hashes); renders verify the live toolchain
  against the lock before running, and each publish writes the lock snapshot
  into that version's `provenance.json`.
- **Artifact-level dependency tracking:** every one of the 22 artifacts has
  its own dependency record keyed on individual `toolchain.lock` entries,
  not the lock as a whole: rawtherapee/ICC changes invalidate rendered
  pixels; ImageMagick/font changes invalidate crops and the comparison
  sheet; img2pdf changes invalidate PDFs only; qpdf/poppler/exiftool changes
  trigger re-verification only (`verified → rendered`), never a re-render.
  E.g. `natural.tif` ← {RAW, natural base style + override pp3, RT seed,
  rawtherapee + ICC lock entries}; `natural_8x10.jpg` adds {crop geometry,
  sharpening recipe, lab profile render fields, ImageMagick lock entry};
  the comparison sheet ← the three native JPGs. Invalidation scope and review scope are independent: a
  crop-geometry change (review-invalidating) forces re-approval but then
  re-renders only the crop artifacts; a natural-sidecar change
  (review-invalidating) re-renders only natural outputs + the sheet; a
  render-only profile change (e.g. `jpeg_quality`) re-renders JPGs/PDFs with
  approval intact; an order-only change touches nothing. Native TIFs are
  untouched by crop or profile changes.
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

**Install (Homebrew):** RawTherapee (RAW engine; CLI at
`/Applications/RawTherapee.app/Contents/MacOS/rawtherapee-cli`), exiftool,
ImageMagick, img2pdf, qpdf, poppler (`pdfimages`). RawTherapee is primary
because its `.pp3` profiles are plain text — the operator can make precise
per-image adjustments during the review loop, which darktable's
base64-encoded XMP parameters do not permit.

**Already installed, roles:** Topaz Photo AI (`tpai` CLI) — optional rescue
pass only; Photoshop 2020 / Affinity / Pixelmator Pro — manual one-off
retouching only.

**Decoder fallback (calibration-aware):** if RawTherapee fails Checkpoint 1
on GH7 files, darktable (5.6 lists GH7 basic RawSpeed support; Homebrew cask
marked for disabling 2026-09-01, official .dmg is the install path) or rawpy
are fallbacks — recipes do not transfer between engines; a fallback means
recalibrating all three styles and accepting reduced per-image tunability.

## Checkpoint 1 (gate for all other work)

Install tools, then on one RW2 verify: decode succeeds; colors render
correctly; orientation is honored; lens corrections actually apply (compare
corrected/uncorrected); highlight recovery behaves; and the RW2 aspect/mode
variants present are handled. Repeat cheaply for each future delivery's
first file.

## QA (per photo, against staging)

- **Images:** exact pixel dimensions per geometry table; bit depth (16 TIF /
  8 JPG); RGB mode; sRGB ICC identity; orientation; nonzero size; DPI tags.
- **PDFs (image wrappers, 9):** `qpdf --check` (syntactic validity only —
  noted as such); `pdfimages -list` for encoding/dimensions; **losslessness
  proven directly** by extracting the embedded JPEG (`pdfimages -j`) and
  comparing its SHA-256 to the source JPG (decoded-pixel-hash comparison as
  fallback if the container alters bytes); page box exactly matches
  intended size.
- **Comparison sheet:** built as a staged composite JPEG (three labeled
  panels rendered by ImageMagick from the three native-crop JPGs), then
  wrapped by img2pdf like every other PDF — so the same extraction +
  SHA-256 losslessness proof applies to it, plus a Letter page-box check
  and a visual check that panels and labels are present and correct.
- **Metadata allowlist assertion (scoped to descriptive namespaces):**
  enforcement covers embedded descriptive metadata — EXIF, XMP, IPTC,
  MakerNotes, and PDF Info. Within those namespaces, deliverables may
  contain ONLY: orientation, exposure basics (shutter, aperture, ISO, focal
  length, lens model), capture date (per lab profile), and optional
  copyright. GPS, serials, owner/artist, maker notes, face regions, and
  embedded thumbnails are stripped, and QA asserts their absence via an
  exiftool scan restricted to those group families. Structural/container
  tags required by the formats (JFIF/TIFF structure, ICC profile internals,
  compression descriptors, PDF catalog, filesystem-derived fields) are
  expressly out of scope and preserved — the ICC profile and DPI/resolution
  fields are required deliverable properties, not privacy leaks. Archive
  copies keep complete EXIF untouched.
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
  re-render exactly the affected outputs on any recipe/profile change, and
  review-invalidating changes force re-approval before anything publishes.
- **Reproduction criterion (single-machine):** on this machine, with a
  toolchain matching `toolchain.lock` (explicit `-p` chains, no default
  profiles), re-rendering from the RAW archive + committed recipes reproduces
  decoded pixel hashes exactly, with identical ICC profiles, geometry, and
  PDF page boxes. Cross-machine reproduction is explicitly out of scope
  (see Scope boundaries) — the recovery path for any machine is the RAW
  archive plus committed recipes, which regenerate equivalent outputs even
  if not bit-identical ones.

## Scope boundaries (explicit descopes)

This is a single-operator, single-machine personal pipeline. The following
are deliberately out of scope, not oversights:

- **Cross-machine bit-exact reproduction** — one machine exists; recipes +
  RAW archive are the portability story.
- **Concurrent driver runs** — one operator (Claude) runs the driver. As
  cheap insurance, the driver takes an exclusive lockfile at startup and
  refuses to start if one is held; no further concurrency machinery.
- **Manual/Topaz edits in the reproducibility model** — if a manual
  composite or Topaz rescue is ever used for a specific photo, the
  resulting raster is archived alongside the RAWs with its SHA-256 recorded
  in the recipe, and that photo is explicitly marked as outside automated
  re-render (its published outputs are the record). No further modeling.
- **Multi-lab profile automation** — one generic profile now; real lab
  profiles are added by hand when a lab is chosen.
