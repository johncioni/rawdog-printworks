# Task 7 fix round 1 — dispatch

Read `task-7-rereview.md` first. It is the authority; the summaries below are
orientation, not a substitute. Fix these five, then stop.

Land as ONE commit (`fix(app): Task 7 review findings — …`) unless a finding
genuinely needs its own; do not squash them into Task 7's originals.

## In scope

**M1 (Major) — the watcher dies when a second window closes.**
`PrintworksApp.swift:29/:36/:55/:57`. One shared `watcher`, but `.task` is
per-window and each has `defer { watcher.stop() }`; `stop()` finishes EVERY
continuation, so ⌘N then ⌘W strands the surviving window with no sources, no
poll, and no way to recover (§6: "No refresh button exists"). The watcher's
lifetime is app-scoped, not window-scoped. The re-review offers two fixes —
ref-count observers / stop only from `deinit`, or make the scene single-window.
**Pick one and say why in your report.** Verify by reasoning AND by doing it:
⌘N, ⌘W, then touch a watched dir and confirm the survivor still refreshes.

**M2 (Major) — no cache behind the content-hash key.**
`GridView.swift:98-105/:60`, `SidebarView.swift:141-155/:120`.
`NSImage(contentsOf:)` runs while constructing the view value, so every body pass
re-decodes 25 MP JPEGs on the main thread (~33 ms each, measured; ~265 ms per
invalidation with 8 cards; the 42 pt thumbnail pays the same). The brief asked
for the hash as a *cache key*; the key is present, the cache is not. Load off the
main actor keyed on the hash, downsample with `CGImageSourceCreateThumbnailAtIndex`
+ `kCGImageSourceThumbnailMaxPixelSize` (card width; 42 pt for thumbs), store by
hash, evict on hash change. **Task 8's canvas will copy whatever you leave here**,
so make it reusable.

**M3 (Major) — "Retry" escalates to a whole-repo `run --force`.**
`AppModel.swift:598` chains a plain `run`, but its failure hands the banner
`reprocessAll()` (`:629-632`) — one click re-renders and republishes photos the
user never touched and `rmtree`s their previous version dirs. Give that branch a
plain-`run` retry (a private `runAll()` mirroring `runStem(_:)` at `:635-638`).
**This one touches irreplaceable photo data; be precise, and add a unit test in
`AppModelTests` asserting the ingest-failure retry issues `run --json` WITHOUT
`--force`.** Red-then-green it.

**m4 (Minor, but the card's primary state signal) — badge contrast.**
`GridView.swift:62-69`. The `.ultraThinMaterial` chip samples the photo beneath:
measured 1.45:1 and 1.85:1 against the glyph, both under WCAG's 3:1 floor for
large text, and ~1:1 over a blown highlight. Use an opaque dark fill
(`Theme.panel.opacity(0.85)`), or keep material with primary-colored text and let
the dot carry the status color.

**m5 (Minor) — §7's per-card "render failed" badge is missing** and no later task
claims it. It belongs in `GridView`, which is yours. Add it.

## Out of scope — leave alone, they are logged for the whole-branch review

m6 (`firstPendingChangeAt` across a consumer-less gap), m7 (silent drop no-ops),
m8 (indeterminate spinner vs §5.2's progress bar), m9 (counts via display-label
string compare), m10 (the delivery-filter rule in three copies), i11 (sidebar
warm brown vs §5.1 black), i12 ("Open Settings" dead until Task 10). Do not
"while I'm here" them.

## Gates — BOTH `--disable-sandbox` flags are MANDATORY

```
swift test --disable-sandbox --package-path app/PrintworksCore
xcodebuild -project app/RAWdogPrintworks/RAWdogPrintworks.xcodeproj \
  -scheme RAWdogPrintworks -destination 'platform=macOS' \
  OTHER_SWIFT_FLAGS='$(inherited) -disable-sandbox' build
```

Exit code is the oracle, never a grep (zsh: `$PIPESTATUS[0]` expands to nothing).
`xcodegen generate` if you add files. `CoreSimulator`/`DVTFilePathFSEvents` noise
is benign — read the tail.

## Report + stop

Write `task-7-fix-round-1-report.md`: per finding, what you changed and the
evidence; for M3 the red-then-green; for M1 which of the two fixes you chose and
why; for M2 what the cache does on hash change and where it lives. State what you
could not verify. **The controller re-runs the gates and re-does the smoke —
including the states the first smoke missed (⌘N/⌘W, a live render, the error
banner). Do not open the app to claim UI correctness, and do not report the task
shipped.** That report is your checkpoint; do NOT rewrite `HANDOFF.md`.
