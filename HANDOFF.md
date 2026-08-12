# HANDOFF

## Goal
Turn family-photoshoot RW2 files (Panasonic Lumix DC-GH7) from `Input/` into
print-and-frame-ready outputs in a natural, restrained style: per photo, 3
16-bit sRGB TIF masters (natural/filmic/bw), 9 JPGs (3 styles × native/8x10/5x7
crops), 9 print PDFs, 1 style-comparison PDF — 22 files. Pipeline must be
repeatable for new RW2 drops over the coming days.

## Done
- Brainstorming complete (superpowers:brainstorming); all design decisions
  approved by user: styles, sRGB for print labs, curated 22-file matrix,
  additions 1–5 (output sharpening, lens corrections, comparison sheets,
  100% QA pass, RAW archiving with SHA-256).
- Tool inventory: no CLI raw tools installed yet; brew + python3 present;
  Photoshop 2020 / Affinity / Pixelmator / Topaz Photo AI installed as apps.
- EXIF pulled via mdls: DC-GH7, ISO 200, f/3.1, 1/800s — clean files.
- git repo initialized (branch main); .gitignore excludes Input/, Output/,
  archive/, previews/, .manifest.
- Spec written + committed (06792a5):
  docs/superpowers/specs/2026-08-11-raw-print-pipeline-design.md
- Spec self-review passed (fixed 21→22 file count inline).
- Added per-person expression audit + best-frame culling section to spec at
  user request; generative expression editing added to exclusions (head/eye
  compositing stays a manual case-by-case option only).

## Ruled out
- RawTherapee CLI and Python rawpy as primary decoders — kept only as
  fallbacks if darktable-cli can't decode GH7 RW2 (2024 body, support risk).
- Cropped TIFs (masters stay native 4:3), AI upscaling, denoising, skin
  smoothing, HDR — excluded deliberately; see spec.
- Photoshop/Affinity/Pixelmator as pipeline tools — not scriptable enough.
- Lab soft-proofing — deferred until user picks a print lab (additive later).

## In flight
- Nothing running. Awaiting user review of the spec (user-review gate in the
  brainstorming skill). Two RW2 files present: Input/P1036163.rw2,
  Input/P1036170.rw2 (~40 MB each).

## Next
1. On user approval of spec, invoke Skill(superpowers:writing-plans) to write
   the implementation plan from the spec.
2. Plan's first task = Checkpoint 1: `brew install darktable exiftool
   imagemagick img2pdf`, then test-decode one file, e.g.
   `darktable-cli Input/P1036163.rw2 previews/test.jpg` and visually verify
   GH7 color rendition before building anything else.
