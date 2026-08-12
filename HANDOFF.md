# HANDOFF

## Goal
Turn family-photoshoot RW2 files (Panasonic Lumix DC-GH7) from `Input/` into
print-ready outputs, natural restrained style: per photo, 3 16-bit sRGB TIF
masters (natural/filmic/bw), 9 JPGs (3 styles × native/8x10/5x7), 9 ancillary
PDFs, 1 comparison sheet — 22 files. All inputs are pre-selected keepers.
Repeatable for new RW2 drops over the coming days.

## Done
- Brainstorming complete; all design decisions user-approved.
- Spec v1 committed (06792a5); expression audit added (549fa17).
- Codex xhigh review of spec ran (thread 019ff375-4b22-7243-a69b-49a3ab21bf7f,
  agent af949dc0a2bc217a9): 9 findings (5 P1, 4 P2).
- User decided: PDFs ancillary (not lab submissions); all inputs keepers →
  all get 22 outputs (ranking, not culling); generic configurable lab
  profile first.
- Spec rev 2 committed (c97db28) addressing all 9 findings: workflow state
  machine (ingested→…→verified), exact output geometry table, versioned lab
  profile, darktable --configdir isolation + explicit export opts, manifest
  keyed on dependency hashes + staging/atomic publish, ranking terminology,
  calibration-aware decoder fallbacks + darktable cask disable note
  (2026-09-01, .dmg fallback), qpdf/pdfimages PDF QA, ingest preflight +
  EXIF privacy stripping (GPS/serial/owner) on deliverables.

## Ruled out
- RawTherapee/rawpy as primary decoders — fallbacks only; recipes don't
  transfer between engines (fallback = recalibrate all styles).
- Cropped TIFs, AI upscaling, skin smoothing, HDR, generative expression
  editing — see spec exclusions. Denoise now default-off per-image, not
  globally excluded.
- Boolean "done" manifest flags — replaced by dependency-hash keying.
- Lab soft-proofing — deferred until a real lab profile is added.

## In flight
- Nothing running. Awaiting user review of spec rev 2 (user-review gate).
- Input/P1036163.rw2, Input/P1036170.rw2 present (~40 MB each).

## Next
1. On user approval of rev 2, invoke Skill(superpowers:writing-plans).
2. Plan's first task = Checkpoint 1: `brew install darktable exiftool
   imagemagick img2pdf qpdf poppler` (darktable via .dmg if cask disabled),
   then test-decode Input/P1036163.rw2 and verify color, orientation, lens
   corrections, highlight recovery per spec Checkpoint 1 section.
