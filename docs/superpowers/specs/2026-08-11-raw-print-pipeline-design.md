# RAW → Print-Ready Pipeline — Design Spec

**Date:** 2026-08-11
**Status:** Approved pending user review
**Camera:** Panasonic Lumix DC-GH7 (25 MP Micro Four Thirds, native 4:3, RW2 files)

## Goal

Turn family-photoshoot RW2 files into print-and-frame-ready TIF, JPG, and PDF
outputs, edited in a natural, restrained style — explicitly correcting the
original photographer's over-processed, over-saturated look. The pipeline must
be repeatable: more RW2 files arrive over the coming days and are processed by
dropping them into `Input/` and re-running.

## Output matrix (per photo) — "curated set", 22 files

| Format | Contents | Count |
|--------|----------|-------|
| TIF | 16-bit sRGB archival masters, native 4:3 only — one per style | 3 |
| JPG | 3 styles × 3 crops (native 4:3, 8×10, 5×7), sRGB, ~q92, 300 DPI | 9 |
| PDF | Lossless img2pdf wraps of the 9 JPGs | 9 |
| PDF | Style-comparison review sheet (natural / filmic / bw side by side) | 1 |

Naming: `<stem>_<style>[_<crop>].<ext>` — e.g. `P1036163_natural.tif`,
`P1036163_bw_8x10.jpg`. Styles: `natural`, `filmic`, `bw`. Crops: none
(native), `8x10`, `5x7`.

## Three styles

All styles start from a shared corrective base: accurate white balance,
recovered highlights, gentle contrast, automatic lens corrections
(distortion/vignetting from embedded MFT profiles + chromatic aberration
removal).

- **natural** — faithful color, true skin tones, restrained saturation
- **filmic** — natural base + subtle warm tone curve, light film character
- **bw** — channel-weighted monochrome, tuned per image for portrait tonality

Deliberately excluded: AI upscaling (25 MP exceeds all print needs), denoising
(ISO 200 base is clean), skin smoothing / heavy retouching, HDR or tone-mapped
effects.

## Directory layout

```
photo-edits/
├── Input/                  # drop .rw2 files here
├── Output/
│   ├── TIF/  JPG/  PDF/    # deliverables (gitignored)
├── archive/                # verbatim RW2 copies + SHA-256 manifest (gitignored)
├── sidecars/               # per-image, per-style edit recipes (committed)
├── previews/               # visual-review working files (gitignored)
├── scripts/process.sh      # repeatable driver (committed)
├── .manifest               # processed-file state; re-runs skip finished work
└── docs/superpowers/specs/ # this spec
```

## Processing flow per photo

1. **Archive** — copy RW2 to `archive/`, record SHA-256 checksum.
2. **Decode** — darktable-cli with the style's sidecar → 16-bit TIF master.
3. **Visual review loop** — export preview JPG; Claude visually inspects
   exposure, white balance, and skin tones; adjusts that image's sidecar;
   re-exports until it holds up. Per-image iteration, not blind batch.
4. **Crop placement by eye** — 8×10 and 5×7 windows chosen visually per photo
   so heads/hands are never clipped. Crop geometry recorded per image so
   re-runs are reproducible.
5. **Output sharpening** — three-stage model: capture sharpen at decode, then
   per-crop output sharpening scaled to final print dimensions (a 5×7 and an
   8×10 from the same pixels need different amounts).
6. **Export** — JPGs (sRGB embedded, ~q92, 300 DPI tags); img2pdf wraps each
   JPG into its PDF with zero re-encoding; style-comparison sheet generated.
7. **QA** — exiftool verifies sRGB profile, dimensions, and DPI on every file;
   100 %-zoom inspection for sensor dust, critical eye sharpness, and clipped
   highlights in faces; final visual pass over all JPGs.

## Tooling

**To install (Homebrew):** darktable (RAW engine), exiftool
(metadata/verification), ImageMagick (crops, conversions, comparison sheets),
img2pdf (lossless PDF wrapping).

**Already installed, roles:** `sips` (built-in, limited — not used for RAW);
Topaz Photo AI (`tpai` CLI) — *optional* rescue pass only, not a dependency;
Photoshop 2020 / Affinity / Pixelmator Pro — not scriptable enough for a
repeatable pipeline; available for one-off manual retouching if ever needed.

**Fallback chain for RAW decode:** darktable-cli → RawTherapee CLI (`.pp3`
profiles) → Python rawpy/libraw. The GH7 is a 2024 body; decoder support is
the pipeline's single biggest risk.

## Checkpoint 1 (gate for all other work)

Install tools, decode one RW2, and visually confirm correct color rendition.
If darktable fails or renders GH7 colors wrongly, fall through the chain
before building anything else.

## Repeatability & error handling

- `.manifest` records completed photos; re-runs process only new files.
- Sidecars + recorded crop geometry are committed, so every edit is
  revisitable and every output regenerable.
- Driver fails loudly per file (no silent skips); a failed decode or
  verification stops that photo and reports it, continuing with others.

## Future option (deferred)

**Lab soft-proofing** — once a print lab is chosen, fetch its ICC profile and
gamut-check each image. Additive; requires no rework.

## Success criteria

- Every Input RW2 yields the full 22-file curated set, all passing exiftool QA.
- Skin tones read as natural to a human reviewer; no over-saturation.
- New RW2 drops process with a single script run, untouched files skipped.
