# Task 8 re-review — ReviewView + CompareView

Reviewer: Opus 5 xhigh. Scope `bf4cbd1..e512205` (one commit, 6 files, +400/−13).

---

## 1. The compare failure — NOT a defect. The toggle path is sound.

**I could not reproduce it. Every one of the four attempts works in the very same
running process you tested** (pid 49204, started 17:22, unchanged binary — I did
not rebuild, so this is your build and your app state, not a fresh one).

| What I drove | Result |
|---|---|
| `AXPress` on the Compare Styles button (accessibility path, not synthetic) | compare opens |
| Coordinate click at **your exact (769,172)**, window-local | opens; second click closes |
| `Space` with focus on `3 list Sidebar` — your attempt 1 | opens |
| `Space` × 8 consecutively, fresh `get-app-state` after each | **8/8 clean toggles**, no misses |
| `⌘1`–`⌘4` *while compare is open* | style switches, amber panel border follows |
| Click the Vibrant panel | style → vibrant **and** compare dismisses (§5.3 "zoom back into that style") |

Screenshot evidence: `qa/task-8-compare.png` — the 4-up grid, labelled, Natural
panel bordered in accent amber. That fills the §8 visual-QA done-criterion for
compare that the smoke could not produce.

### The one reproducible failure mode — and it is macOS, not the app

I deactivated the app (brought Finder forward) and re-ran the same commands:

```
frontmost=Finder   Space          -> compare_open=False   (twice, no effect)
frontmost=Finder   click 769,172  -> compare_open=True    (the click also activates the app)
```

An **unmodified** key equivalent (`space`, `←`, `→`) is only routed to a window
that is *key*; a `⌘`-modified one goes through the main menu and fires whether or
not the window is key. That asymmetry is exactly what you observed — ⌘1–⌘4
working while Space did nothing — and it is correct AppKit behaviour, not a
`showingCompare` bug. My first call used `--restore-window`; I suspect yours did
not, and each CLI round-trip handed focus back to the terminal.

For the two failed clicks, the likely second cause is index/geometry staleness:
**the button carries no accessibility name** (see M1) — it prints as a bare
`25 button`, and the index shifts by one whenever the stale-preview chip appears
or compare opens, so "click Compare Styles by element index" was a guess. Window-
local coordinates also move with window width (the inspector is right-anchored at
a fixed 260 pt, so the button centre is `width − 130`); if the window was not
900 pt wide when you measured, (769,172) landed on empty canvas.

### Reading of the code, independent of the tooling

`showingCompare` is a plain `@State` on `ReviewScreen` (`ReviewView.swift:6`),
read at `:12`, written only at `:14` (CompareView's `onSelect`) and `:107` (the
button). `ReviewScreen`'s structural identity in `MainWindow.swift:14-21` is
stable across model updates, so the state cannot be silently reset. There is no
sheet, no `NavigationLink`, no presentation modifier — nothing that can fail to
present. There is no path by which a delivered press does not flip the branch.

**Not a Major. Not a finding. Task 8's compare deliverable works.**

---

## 2. Does Task 8 ship?

**Yes.** The deliverable meets its brief and §5.3. Everything below is Minor or
polish; none of it blocks, and none of it needs a fix round before Task 9.

---

## 3. Findings, severity-ordered

### M1 (Minor, accessibility) — every control Task 8 adds is nameless in the AX tree

`ReviewView.swift:106-113` (compare toggle), `ReviewView.swift:63-83` (stale
chip), `CompareView.swift:29-61` (four panels).

The accessibility tree the project's own smoke tooling reads shows these as bare
`button` entries, while sibling controls that do expose names print them
(`button Hide Sidebar`, `radio button Natural`). Failure scenario: a VoiceOver
user on the review screen hears "button" four times in compare mode with no way
to tell Natural from Bw; and, as above, it cost this task a smoke round because
index-based clicking became guesswork. Fix is one line each —
`.accessibilityLabel("Compare Styles")`, `.accessibilityLabel(style.capitalized)`.

Caveat on the evidence: I read this through `orca computer get-app-state`. I could
not query `AXTitle`/`AXDescription` directly (the repo venv has no
`pyobjc-framework-ApplicationServices` and I would not install into it for a
review), so I cannot distinguish "no accessible name" from "name present only on
a child element that the tree printer omits". The observable behaviour through the
tooling this project actually uses is the same either way.

Pre-existing in style — Task 7's sidebar row buttons are nameless too — but Task 8
adds six more, and it is the compare panels where a name carries real meaning.

### M2 (Minor, reuse) — "photos in the open delivery" is now derived in four places

`ReviewView.swift:171-176`, `SidebarView.swift:159-165`, `MainWindow.swift:101-117`,
`GridView.swift:126`.

Task 8 added the copy at `ReviewView.swift:171`. All four agree today (I checked:
`←`/`→` traverse in exactly the sidebar's visible order, and clamp correctly at
both ends — Right at the last photo is a no-op). Failure scenario: whoever adds
delivery sorting or a "hide published" filter changes one copy; the toolbar's
needs-review count, the sidebar list, and `←`/`→` traversal then disagree about
what the delivery contains, and arrow navigation skips a photo the sidebar shows.
One `AppModel.photos(inDeliveryOf:)` accessor collapses all four. This is model-
level derivation living in views, which also brushes the "views add no model
logic" constraint.

### N3 (Nit, visual) — compare cells are portrait; landscape previews use ~45% of them

`CompareView.swift:9-21`. The `Grid` splits the canvas region into four equal
cells, which are tall and narrow on a normally-proportioned window; a 4:3
landscape preview letterboxed into one leaves roughly half the cell black
(visible in `qa/task-8-compare.png`). It is not wrong — `.fit` is the correct
content mode, and never cropping a photo the user is judging is the right call —
but the 4-up reads smaller than it needs to. Sizing the grid to the previews'
aspect would recover the space. §8 asks for compare to be reviewed by eye; this
is what my eye says.

### N4 (Nit) — "not rendered yet" and "failed to decode" look identical

`PreviewImage.swift:119-125`. Filmic and Bw have no rendered preview in the
fixture repo and both panels show the generic photo glyph — the same glyph a
corrupt or unreadable JPG produces. Failure scenario: a user in compare after a
partial `run` cannot tell "this style hasn't rendered" from "this preview is
broken", and the two want different actions. A one-word caption under the glyph
when `path == nil` would separate them.

### N5 (Nit) — Escape does not close compare

`ReviewView.swift:114`. Space toggles and clicking a panel dismisses, both per
spec. Escape is the reflex for a full-canvas mode and currently does nothing.

---

## 4. i4 carry-forward — reuse confirmed, numbers correct, one pool still right

`PreviewImage` was **reused, not forked**: the only change is an added
`contentMode` parameter with a `.fill` default (`PreviewImage.swift:93-99`), and
`.scaledToFill()` → `.aspectRatio(contentMode:)` at `:116`, which is the identical
expression for the default. Task 7's grid and sidebar callers are untouched and
keep fill behaviour. `contentMode` is deliberately *not* part of the cache key —
correct, the decoded bitmap is the same for both.

The report's rung costs check out arithmetically (4 bytes/px × 4:3 at each rung:
1280→4.9 MB, 1536→7.1 MB, 2048→12.6 MB, 2560→19.7 MB).

Measured, rather than calculated, on the live app (900×652 window, `ps` RSS):

```
canvas only                48 MB
compare open (4 panels)    59 MB      <- ~11 MB for four panel entries
after cycling all 4 styles 58 MB
compare open again         60 MB      <- stable, no growth across cycles
```

I agree with keeping the single 256 MiB pool, and for a stronger reason than the
report gives: compare loads four *panel*-sized entries (~half-canvas, one or two
rungs down), not four canvas-sized ones, so the worst realistic review working
set is one canvas entry plus four panels — on a large display roughly
24 + 4×7 ≈ 52 MB, comfortably inside the pool with the grid still resident.
Splitting the pool now would be unrequested churn. `countLimit = 40` is the
binding limit only for small sidebar entries; cost eviction governs everything
canvas-sized. Bounded by construction either way.

---

## 5. Constraint and regression audit

- **No pipeline logic in Swift** ✓ — the views hold no pipeline knowledge;
  `rerenderPreview` (`AppModel.swift:488-502`) shells one argv and decodes.
- **No repo writes from Swift** ✓ — `grep` over `app/RAWdogPrintworks/Sources`
  for `FileManager`, `write(to`, `Process(` returns nothing.
- **Argv-only** ✓ — `["preview","--stem",stem,"--style",style,"--json"]`. I
  checked this against the pipeline rather than the prose: `pipeline/__main__.py:25-28`
  accepts both positional and flag forms and `_preview_target` (`:122-124`)
  resolves the flags, so the app's flag form is valid. `adjust.preview_result`
  (`pipeline/adjust.py:91-107`) emits exactly the `AdjustResult` shape the app
  decodes, matching `tests/fixtures/json_contract/adjust_ok.json`.
- **No `--force` / `approve` reachable** ✓ — the only mutation Task 8 can reach is
  `preview`, behind an explicit chip click, and the failure retry closure
  (`AppModel.swift:498-500`) re-issues the *same* stem+style. No scope widening.
- **Opaque chips over photos** (Task 7 carry-forward) ✓ — `Theme.panel` is
  `#141416`, fully opaque; white-on-#141416 clears WCAG comfortably.
- **Content-hash keying, no `AsyncImage`, no URL/mtime cache** ✓ — `.id(previewHash)`
  at `ReviewView.swift:46` and `CompareView.swift:40`, `RepoPaths.resolve` inside
  the loader, `grep` for `AsyncImage` and `NSImage(contentsOf` returns nothing.
- **Task 7 regressions** — none found. `xcodegen` output is correct: both new
  files appear in the Sources build phase (`project.pbxproj:149,155`), so a clean
  checkout builds.

On the shared-rebase test: your mutation settles it. Worth recording that the test
asserts *behavioural* equivalence, so a full duplicate of `rebase`'s logic would
also pass — no behavioural test can do better. The code itself calls the shared
method at `AppModel.swift:494`, which is what the requirement was actually about.

---

## 6. Carry-forwards for later tasks

1. **Task 11 (sliders):** the shimmer trigger is hard-coded to
   `activeCommand == "preview"` (`ReviewView.swift:56`). Spec §5.3 wants the same
   shimmer during the slider's debounced `adjust`. Task 8 built it exactly as its
   brief worded it; whoever adds sliders must widen that condition.
2. **Task 11 (audit note):** the unmodified `space` / `←` / `→` shortcuts live in
   the same screen that will gain a free-text note field. AppKit normally declines
   to match unmodified key equivalents while a text view is first responder, so
   this probably works out — but it must be smoke-tested by actually typing a
   space into that field, not assumed.
3. **Smoke tooling:** drive this app with `--restore-window` and re-read state
   before every index-based click. Both failures in the Task 8 smoke trace to that.

---

## 7. What I did not verify

- I did not re-run the gates; I took your 66-test / `xcodebuild` result and your
  re-run of the shared-rebase mutation as given.
- The stale-preview chip's *action* is untested by me — clicking it issues a real
  `preview` mutation against irreplaceable photo data and can move
  `review_revision` on a Published photo. I read the path instead
  (`ReviewView.swift:65-68` → `AppModel.swift:488`) and confirmed the argv and the
  disabled-while-busy gate (`ReviewView.swift:84`). The chip's *appearance* you
  already verified.
- Memory numbers are RSS on a 900×652 window; I did not resize to a large display
  to observe the 2560 px rung in practice.
- The AX-name caveat in M1.
