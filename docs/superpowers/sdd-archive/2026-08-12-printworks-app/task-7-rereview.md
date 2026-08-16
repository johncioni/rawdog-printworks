# Task 7 re-review — `c4a10d1..bffbf56`

Reviewer: Opus 5 (xhigh). Method: read the two commits in full against
`task-7-brief.md`, `task-7-dispatch.md`, `task-7-report.md`, spec §5–§8, and the
consumed surfaces (`AppModel`, `RepoWatcher`, `RepoPaths`, `Theme`, `PhotoStatus`).
Gates were **not** re-run — the controller's runs are taken as settled. Two
findings are backed by measurements I took myself (pixel sampling of the smoke
screenshot; a timing harness against the real repo's previews).

## Verdict

**Task 7 does not ship as-is. It ships once M1 and M2 below are fixed** (both are
in Task 7's own new files, both are small), and M3 should go with them since it
is a one-line change to a path Task 7 just made clickable.

Nothing here is a Critical: no repo write, no subprocess, no pipeline logic in
Swift, and no path that can approve or destroy photo data. The shell is otherwise
a faithful implementation of the brief — the skeleton names, the status-dot
mapping, the sidebar's two levels, the pipeline block, the grid card rules, the
drop target, the empty state, the busy pill and §7's three banner actions are all
present and correct.

The reason I am not waving it through on "it builds and the smoke looked right"
is that Task 7 ships with no tests by design, M1 and M2 are both invisible to a
two-photo idle smoke, and Task 8 will copy M2's image-loading pattern into the
review canvas if it is left standing.

---

## Findings

### M1 — Major: closing a second window kills the watcher for the surviving window; the app then never refreshes again

`app/RAWdogPrintworks/Sources/PrintworksApp.swift:29` (one shared `watcher`),
`:36` (`.task` per window), `:55` (`defer { watcher.stop() }`),
`:57` (`for await _ in changes`) — with
`app/PrintworksCore/Sources/PrintworksCore/RepoWatcher.swift:156-158`
(`stop()` finishes **every** registered continuation, not just the caller's).

`WindowGroup` gives the app File ▸ New Window (⌘N) — nothing in
`.commands { SidebarCommands() }` removes it. The `App` struct is instantiated
once, so `watcher` and `model` are shared by every window, but `.task` is
per-window: two windows means two `observeRepo()` tasks, each with its own
`defer { watcher.stop() }`.

Failure scenario: ⌘N, then ⌘W on either window. The closed window's `.task` is
cancelled → its `for await` ends → its `defer` calls `watcher.stop()` → `stop()`
cancels every kqueue source, cancels polling, and finishes **all** continuations
including the surviving window's. The survivor's `for await` therefore also ends,
runs its own `stop()`, and its `.task` completes. The surviving window is now
live on screen with no FSEvents subscription, no sources, and no poll — and
`.task` does not re-run for a view that never changed identity. Per §6 "No
refresh button exists", so that window is frozen against disk truth until the app
is quit: a CLI `run` publishes photos and the grid keeps showing the old states
forever, and the busy pill can no longer clear by FSEvents or the 5 s fallback
(only a mutating command's own terminal refresh can still clear it). The
single-window close/reopen case recovers correctly; it is specifically
two-windows-then-close-one that strands the survivor.

This is reasoned from the code, not reproduced — 30-second confirmation: ⌘N, ⌘W,
then run any pipeline command in the CLI and watch the remaining window not move.

Fix: the watcher's lifecycle is app-scoped, not window-scoped. Either drop
`defer { watcher.stop() }` and stop only when the last observer detaches
(ref-count the observers, or stop from `deinit` only), or make the scene
single-window (`Window` instead of `WindowGroup`, or
`CommandGroup(replacing: .newItem) {}`).

### M2 — Major: every body pass re-reads and re-decodes 25 MP preview JPEGs on the main thread; `.id(hash)` is a key with no cache behind it

`app/RAWdogPrintworks/Sources/GridView.swift:98-105` (`preview(_:)`), `:60`
(the `.id`), and `app/RAWdogPrintworks/Sources/SidebarView.swift:141-155`, `:120`.

`NSImage(contentsOf:)` is called *while constructing* the view value, so it runs
on every body evaluation. `.id(previewHashes["natural"])` assigns identity to the
already-constructed view; it does not memoize the load. The brief asked for the
hash as a **content-hash cache key** — the key is there, the cache is not.

Measured against the real repo (`previews/P1036163_natural_preview.jpg`,
6.6 MB, **5784×4344**), doing exactly what the view does — fresh
`NSImage(contentsOf:)` then draw at card size:

```
card 260x190: 213, 34, 33, 33, 35 ms   (first = cold page cache)
thumb 42x42 : 34, 32, 33, 33, 34 ms    (same cost for a 42 pt thumbnail)
```

Failure scenario: `GridView.body` reads `model.snapshot` and
`model.renderProgress`. `@Observable` fires on assignment, not on inequality, so
*every* `performRefresh()` reassigns `snapshot` and invalidates the body, and
every progress event mutates `renderProgress` and invalidates it again. Each
invalidation re-loads and re-decodes every **visible** card: 8 visible cards ≈
265 ms of blocked main thread per invalidation. During `run --force` over a real
delivery the pipeline streams a progress event per rendered file (22 files per
photo), so the UI is pinned for the whole render — while the progress overlay
that causes it is the thing the user is watching. Even fully idle with the busy
pill up, the 5 s poll costs a ~265 ms hitch every 5 seconds. The review sidebar
pays the same ~33 ms per row to paint a 42×42 pt thumbnail from a 25 MP JPEG.

Two photos in the smoke repo is ~66 ms, which is why this looked fine.

Fix: a small hash-keyed cache in front of the loads — load off the main actor in
`.task(id: previewHashes[style])`, downsample with
`CGImageSourceCreateThumbnailAtIndex` +
`kCGImageSourceThumbnailMaxPixelSize` (card width and 42 pt respectively), store
by hash, evict on hash change. That is also what Task 8's canvas will need, so it
is worth having before Task 8 copies the current pattern.

### M3 — Major: "Retry" on a failed post-ingest run escalates to `run --force` across the whole repo

`app/PrintworksCore/Sources/PrintworksCore/AppModel.swift:608-610` (Task 5 code —
but Task 7's `ErrorBanner` is what first makes it clickable, and question 5 of the
dispatch asks exactly this).

`ingest()` chains a plain `run --json` (`AppModel.swift:598`) but hands its
failure a retry closure of `reprocessAll()` — i.e. `run --force --json`
(`:629-632`).

Failure scenario: user drops RAWs → `ingest` succeeds → the chained `run` fails
with `RENDER_FAILED` → banner offers **Retry** → the click runs
`run --force --json` over **every photo in the repo**. `_force_downgrade`
(`pipeline/driver.py:681-692`) resets each verified photo to `approved` so it
re-renders; each success publishes a new `vNNN` and `publish.recover()`
(`pipeline/publish.py:258-261`) `rmtree`s every version dir that is not
`current`. So one click of a button labelled "Retry" re-renders and republishes
photos the user never touched (22 files each, hours of RawTherapee time) and
deletes their previous published version directories. Output is reproducible from
the same recipes, so this is churn and lost time rather than lost pixels — but it
is a large, silent escalation from what the user asked for.

Fix: give ingest's run-failure branch a plain-`run` retry (a private
`runAll()` mirroring `runStem(_:)` at `:635-638`), not `reprocessAll()`.

### m4 — Minor: the status badge's legibility depends on the photo behind it (this is dispatch question 4)

`app/RAWdogPrintworks/Sources/GridView.swift:62-69`.

Not a mid-fade capture artifact. I sampled `qa/task-7-shell-smoke.png` directly:
the two badges' glyph pixels are **byte-identical** — `(97, 197, 84)` on both
cards — which rules out a partial-opacity fade (a fade would blend the glyph
toward its own backdrop, and the backdrops differ). What differs is the
`.ultraThinMaterial` chip, which samples the photo underneath it:

| card | chip RGB | contrast vs. glyph |
|---|---|---|
| left (P1036163, blown-out sky under the badge) | `(144, 146, 149)` | **1.45 : 1** |
| right (P1036170, darker sky) | `(123, 127, 144)` | **1.85 : 1** |

So it is a real, deterministic defect, just a cosmetic one — and it is worse than
"the left one looks dim": *both* are far below WCAG's 3:1 floor for large text,
and a fully blown-out highlight under the badge takes it to roughly 1:1. The
badge is the card's primary state signal.

Fix: put the chip on an opaque dark fill (`Theme.panel.opacity(0.85)`) instead of
material, or keep the material and use primary-colored text with the status color
carried only by the dot.

### m5 — Minor: §7's per-card "render failed" badge is missing, and no later task claims it

`app/RAWdogPrintworks/Sources/GridView.swift:55-95`.

§7 requires "a failed render leaves the card in its prior state with a 'render
failed' badge and Retry (`run --stem`)", and §7 notes multi-photo failures are
per-stem in `result.failed`. `AppModel` already collects them
(`lastFailures`/`lastIngestFailures`, `AppModel.swift:649-664`) — **no view reads
either property**. I checked task-8/9/10/11 briefs: none of them claims this, so
it is unowned, and Task 7's card is its natural home.

Failure scenario: `run` over 40 photos, 3 fail → `PARTIAL_FAILURE` banner states
the aggregate → the three failed cards render their prior state with no marker →
the user cannot tell which three failed without going to the CLI.

### m6 — Minor: `firstPendingChangeAt` survives a consumer-less gap, so the next change emits with an already-expired deadline (dispatch question 3, second half)

`app/PrintworksCore/Sources/PrintworksCore/RepoWatcher.swift:336-339` vs `:321-324`.

The no-consumer branch clears `pendingCoalesce` but retains both `pendingChange`
and `firstPendingChangeAt`. A later change therefore skips
`if !pendingChange { firstPendingChangeAt = now }` (`:310-312`) and computes
`maximumDeadline = firstPendingChangeAt + 2.0` from a timestamp minutes old, so
`deadline = min(trailing, maximum)` is in the past and
`queue.asyncAfter` fires immediately — the 500 ms coalesce window is skipped for
the first change after every gap.

Acceptable? Yes, in impact: exactly one uncoalesced `status`, after which
`pendingChange`/`firstPendingChangeAt` reset and coalescing is normal again, and
`AppModel.refresh()`'s re-entry guard (`:222-233`) collapses the storm anyway, so
§7's watcher-storm requirement still holds. But it is an unintended side effect
of the M2 fix, and it silently voids the max-wait cap across gaps.

Concrete fix — one line, and it composes with the existing `?? now`:

```swift
guard !currentContinuations.isEmpty else {
    firstPendingChangeAt = nil      // add: restart the max-wait clock
    pendingCoalesce = nil
    return []
}
```

### m7 — Minor: the drop target is silent in three distinct no-op cases

`app/RAWdogPrintworks/Sources/MainWindow.swift:45-48`.

1. **Pipeline locked.** `ingest` returns `LOCK_HELD` → `surface` sets
   `busyExternally` and shows no banner (correct per §6) — but the pill may
   already be up, so the drop produces zero visible response.
2. **Nothing ingestible.** `_iter_sources` (`pipeline/ingest.py:150-156`) silently
   filters anything that is not a `.rw2` or a directory of them. Drop a folder of
   JPEGs and `result.ingested` is empty → no `run` is chained, `notices` is empty
   → no banner, no notice, nothing.
3. **No re-entry guard.** Two quick drops start two overlapping `ingest` tasks;
   the pipeline lock serializes them safely, but the second `beginCommand` bumps
   `commandGeneration` so the first drop's progress events are discarded
   (`AppModel.swift:740-751`).

The Reprocess menu is correctly disabled on `busyExternally || activeCommand != nil`
(`MainWindow.swift:86`); the drop path has no equivalent.

### m8 — Minor: the toolbar shows an indeterminate spinner where §5.2 asks for a compact progress bar

`app/RAWdogPrintworks/Sources/MainWindow.swift:64-70`. `renderProgress` carries
`index`/`total` — `GridView.progressFraction` (`:124-129`) already derives a
fraction from it — so the determinate `ProgressView(value:)` the spec calls for is
available for free.

### m9 — Minor: counts are computed by string-comparing a display label

`app/RAWdogPrintworks/Sources/MainWindow.swift:131-135` and
`app/RAWdogPrintworks/Sources/SidebarView.swift:193-197` both count photos via
`PhotoStateAppearance(state:).label == "Needs review"`. Renaming that label — a
copy change, the kind that gets made without thinking — silently zeroes the
toolbar count and every sidebar row's "N review". Give `PhotoStateAppearance` a
case enum (or an `isNeedsReview` flag) and count on that.

### m10 — Minor (reuse): the "filter photos by selected delivery" rule exists in three copies

`MainWindow.swift:101-117`, `GridView.swift:116-122`, `SidebarView.swift:172-178`.
Three implementations of one rule, already slightly divergent (MainWindow has two
near-identical review-mode branches at `:104-112` that collapse to one). One
`AppModel` computed property — or one shared view helper — would keep the grid,
the sidebar and the toolbar count from drifting apart.

### i11 — Informational: the sidebar renders warm brown, not §5.1's black primary

`app/RAWdogPrintworks/Sources/MainWindow.swift:11`. §5.1 says the sidebar is
"`.ultraThinMaterial` translucency over the black window", but a macOS sidebar
material blends with what is behind the *window* — the desktop — not with the
window's own base. The smoke screenshot shows exactly that: a warm brown sidebar
next to a `#0A0A0B` content pane. The brief prescribed this modifier, so the
implementer complied; flagging it because Task 11's visual QA will judge the
result, not the modifier. If it should be black: put `Theme.panel` (or
`windowBase`) under the material.

### i12 — Informational: "Open Settings" is a dead button until Task 10

`app/RAWdogPrintworks/Sources/ErrorBanner.swift:5, 62`. There is no `Settings`
scene in `PrintworksApp` yet, so `openSettings()` does nothing (SwiftUI logs a
runtime issue). `TOOLCHAIN_FAILED` is a state the app can reach today. The report
declares this and Task 10 owns the scene — noted, not charged against Task 7.

---

## Answers to the five questions

**1. Spec §5–§8 conformance.** Conforms, with the gaps at m5 (no per-card render-failed
badge), m8 (spinner vs. bar) and m4/i11 (visual). Verified present and correct by
reading: the status-dot mapping matches the brief exactly
(`GridView.swift:9-24`); `LazyVGrid(.adaptive(minimum: 260))`, badge top-left,
`ProgressView(value:)` overlay, double-click → review
(`GridView.swift:31, 42-49, 62-79`); browse sidebar with photo/review counts plus
the toolchain + idle/busy pipeline block (`SidebarView.swift:22-66`); review
sidebar with 42 pt thumbnails and state dots (`:80-90, 116-155`); toolbar's
delivery name, needs-review count, Reprocess menu and Grid/Review toggle
(`MainWindow.swift:53-98`); whole-window `.dropDestination`
(`MainWindow.swift:45`); the "Drop RAW files to start a delivery." empty state
(`GridView.swift:34-39`); the busy pill as a `Capsule`, never a banner
(`MainWindow.swift:29-41`, and `LOCK_HELD` short-circuits in
`AppModel.surface`); §7's three per-code actions with a Show Details disclosure
over `stderrTail` (`ErrorBanner.swift:19-45, 57-68`, mapping at
`AppModel.swift:702-709`), including `INGEST_NOTICE` correctly resolving to no
action button.

**2. Plan 2's binding constraints.** Verified by reading, not just grep. No
`Process`, no `FileManager` mutation, no `write(to:)`, no `removeItem` anywhere in
`app/RAWdogPrintworks/Sources/` — the app target's only filesystem contact is
`NSImage(contentsOf: RepoPaths.resolve(...))` in the two view files. Both image
paths resolve through `RepoPaths.resolve(path, repo: model.repo)` and both key on
`previewHashes["natural"]`. Argv-only invocation is untouched by this diff. Views
add no model logic: `PhotoStateAppearance` and `progressFraction` are
presentation mappings, and Reprocess calls the existing
`model.reprocess(stem:)`/`reprocessAll()`. One caveat, which is M2: the letter of
"key on the content hash" is satisfied and the intent ("never URL/mtime caching"
— i.e. *have a cache*) is not.

**3. Is M2's contract sound, and honoured everywhere?** The ordering contract
itself is honoured today: `PrintworksApp.swift:49` reads `changes` before
`:53` calls `start()`, and that also holds for a second window's task and for any
post-stop restart, since each new `.task` re-reads `changes` first. But the
contract is *unenforced and untested* — nothing in `RepoWatcher` stops a caller
from starting before registering, and the failure mode is silent (the change is
latched, then delivered only when some unrelated later change happens to arrive).
The retain is half a fix: it preserves the change but has no way to deliver it to
a consumer that registers afterwards. If you want it to be genuinely safe rather
than merely correct-by-convention, flush a latched `pendingChange` at
registration time inside the `changes` factory (`RepoWatcher.swift:59-74`) — then
the ordering rule stops being load-bearing. Note that the retain path is close to
unreachable in the app as written: the only window where the watcher is live with
zero consumers is between a continuation's `onTermination` and the `defer`'s
`stop()`. The `firstPendingChangeAt` half of the question is m6 above:
acceptable in impact, worth the one-line fix.

**4. The dimmer "Published" on the left card.** Real, not a capture artifact —
see m4 for the pixel evidence. The glyph color is identical on both cards; the
material chip is not, because it samples the photo.

**5. Can reprocess fire without explicit user intent?** No *automatic* path
exists: `reprocess`/`reprocessAll` are reachable only from the toolbar menu
(`MainWindow.swift:73-86`, correctly disabled while busy or while a command runs)
and from `retryBannerAction()`, which requires `bannerAction == .retry` and a
click. But M3 is the answer that matters: one path fires `run --force` **across
the whole repo** from a button that says "Retry", after a drop-ingest whose run
failed. That is explicit input, but not informed consent — fix M3 before shipping.

---

## On the controller's verification

Nothing you did was wrong. The gate runs, the `coalesce-10x` mutation kill
(RED at `"5.0" is not equal to "0.5"`, then reverted), and the constraint sweep
all check out against what I read. Three places where it was insufficient rather
than incorrect:

- **The smoke covers ~2 of the 8 states §8 lists as done-criteria.** One static
  frame of the idle published grid is real evidence for the grid, the sidebar
  grouping and the status mapping — and it is structurally incapable of reaching
  M1 (needs ⌘N then ⌘W) or M2 (needs many cards *and* a live render). §8's list
  also wants progress, busy pill, stale-draft and error banner shots; those states
  remain unobserved. That is fine as a Task 7 checkpoint, but it is not the visual
  QA that §8 makes a done-criterion.
- **The constraint grep verified the letter and missed the intent.** "Both views
  key images on `previewHashes["natural"]` and resolve via `RepoPaths.resolve`" is
  true and I confirmed it — but the brief's point was a *cache* keyed by content
  hash, and grepping for the key cannot see that there is no cache behind it
  (M2). The same grep style is why "no repo writes / no subprocess" is worth the
  read I gave it — that one held.
- **Question 4's leading hypothesis was wrong**, and cheaply falsifiable: the
  glyph pixels being identical across both cards rules out a fade outright.

---

## What I did not check

- Did not re-run `swift test`, `xcodebuild`, or the mutation check.
- Did not launch the app, so M1 is reasoned from the code and the SwiftUI
  scene/`.task` lifecycle, not reproduced; M2's per-pass cost is measured on the
  real preview files with a standalone harness, but not profiled inside the
  running app.
- Did not re-litigate the out-of-scope items (kqueue vs. in-place edits,
  `Output/photos/<stem>/`, the Task 5 refresh gate, `expected_review_revision`,
  the `ReviewScreen` placeholder, the Settings scene).
- `PipelineClient`'s 50-line stderr cap behind "Show Details" is assumed correct
  from Task 3/4; I read only its consumption here.
