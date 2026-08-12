# HANDOFF

## Goal
Pipeline COMPLETE on main (9f52ec3). NOW: brainstorming "RAWdog
Printworks" — a SwiftUI macOS app frontend for the pipeline (Sequoia+,
black-primary, amber accent, self-signed personal use). Spec will go to
docs/superpowers/specs/2026-08-12-macos-app-design.md.

## Done
- Decisions LOCKED: app + CLI coexist over shared disk state; in-app
  review (previews, crop overlays w/ drag-nudge, audit checklist);
  in-app edits = warmth+exposure sliders only (write sidecars);
  layout = A+C hybrid (grid browse + translucent sidebar + review
  inspector); name "RAWdog Printworks"; ingest = drag&drop + Input/
  watch; Approve runs approve→render→publish chain.
- Architecture APPROVED: SwiftUI app, PipelineClient actor shells to
  `python -m pipeline` w/ new --json envelopes, status --json, progress
  events, single-style preview cmd; FSEvents watcher; lockfile arbitrates.
- Components APPROVED: compare mode (space), crop overlay (C), ⌘1-4
  styles, debounced 2s slider→sidecar→preview loop, progress HUD,
  minimal settings (repo path + python path).
- Sections 3-5 (data flow, error handling, testing w/ shared golden JSON
  fixtures + visual QA done-criteria) PRESENTED — awaiting user approval.

## Ruled out
- Embedded Python (packaging pain); Electron/Tauri (not native).

## In flight
- Visual companion server port 60219; session dir
  .superpowers/brainstorm/22193-1786559112/ (mockups in content/,
  clicks in state/events). Currently showing waiting screen.

## Next
1. On user approval of sections 3-5: write spec to
   docs/superpowers/specs/2026-08-12-macos-app-design.md
   (use elements-of-style skill), self-review, commit (+ .gitignore
   change adding .superpowers/), then user spec review gate.
2. Then Skill(superpowers:writing-plans) for the implementation plan.
3. Implementation later: Codex Sol 5.6 xhigh implements / Fable reviews
   (per model-usage-preferences memory); enable swift-lsp; Impeccable +
   axiom-macos for UI build; computer-use screenshots for visual QA.
