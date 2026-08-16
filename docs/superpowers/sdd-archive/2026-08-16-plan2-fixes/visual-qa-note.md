# Visual QA — Plan 2 fix round

Run by the controller (Opus 5) on 2026-08-16 against the app built from
`1e60c72` (batch 4), pointed at the **scratch repo**
`~/orca/workspaces/rawdog-printworks/smoke-repo` — never the real repo. Both
scratch photos were `verified`/published, which made them the right fixture for
F1. Screenshots in `qa/`, each verified distinct from the prior capture by
SHA-256 before being kept.

## Verified

**F1 — Approve is dead on a published photo.** This is the finding that mattered
most, and the fixture was ideal. Opened published photo P1036163 and ticked all
three expression-audit boxes (`qa/02`). **Approve stayed disabled.** That is
exactly the failure scenario the whole-branch review described: before batch 1,
ticking those three boxes on an already-published photo enabled Approve, and
clicking it demoted the manifest to `approved`, re-staged v001's own artifacts
into v002 and pruned v001. Screenshot evidence: `qa/01` (unchecked, disabled) →
`qa/02` (all three checked, still disabled).

**F2 — Reprocess ▸ All Photos confirms.** `qa/06`: "**Reprocess all 2 photos?**"
— the count is correct for the scratch repo — with the body "This re-renders
every photo and publishes a new version of each.", the destructive action in red,
and **Cancel as the default** (independently confirmed by the AX tree reporting
`The focused UI element is 73 button Cancel`). Cancelled it; `pipeline status`
after showed both photos still `verified` with no new version, so nothing ran.

**F7 — grid cards are real, non-visually operable controls.** The grid renders
its cards as AX `button` elements, and activating one through the accessibility
API opened the review screen. That is the same path VoiceOver uses, so the claim
holds. Under the old `.onTapGesture(count: 2)` there was no AX action to invoke
at all.

**F4 — the crop overlay renders correctly with real geometry** (`qa/08`). The
8×10 is a solid outline inset horizontally and full height; the 5×7 is dashed,
full width and ~95% height — matching the persisted fixture exactly
(8×10 `x=0.0612 w=0.9388 h=1.0`, 5×7 `x=0 w=1.0 h=0.9510`). This is the geometry
that made 8×10 nearly ungrabbable under the old filled-interior hit test.

## NOT verified, and why — read this before trusting the F4 fix end to end

**Synthetic input does not reach this app.** Keyboard events sent via
`orca computer press-key`/`hotkey` return `ok: true` and change nothing:
`c` did not toggle the crop overlay and `⌘2` did not switch style, with the
screenshots byte-identical. Posted `CGEvent` mouse clicks did not land either.
Only AX actions (`click --element-index`, `perform-secondary-action`) work.

Consequences — these remain **unexercised against the running app**:

- the actual **drag** that targets 8×10 rather than 5×7 (F4's core claim),
- **arrow-key crop nudging** (batch 1's new keyboard path),
- every **keyboard shortcut** (`C`, `⌘1–⌘4`, Space, ←/→).

Do **not** read this note as evidence those work. What is established is that
`CropMath.cropTarget` implements stroke-proximity targeting — the controller
mutated `distanceToOutline` to return 0 inside the rect (restoring
filled-interior behaviour) and the test failed with `"5x7" is not equal to
"8x10"`, reproducing the original defect precisely — and that the overlay renders
the geometry the fix operates on. The wiring between a real drag gesture and
`cropTarget` is covered only by unit tests.

The overlay was made visible by temporarily defaulting `showingCrops = true` and
rebuilding, because the `C` shortcut could not be driven. **That change was
reverted and the app rebuilt from committed source**; `git status` is clean and
no `QA-TEMP` marker remains.

## Not attempted

The full ingest → adjust → approve → publish loop. It was driven end to end in
the previous round's QA (`../2026-08-12-printworks-app/task-11-visual-qa-note.md`),
this round changed no pipeline-facing behaviour, and re-running it would have
republished the scratch photos for no added signal.
