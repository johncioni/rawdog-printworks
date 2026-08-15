# Task 7 fix round 1 — re-review — `bffbf56..c9165c2`

Reviewer: Opus 5 (xhigh). Scope: the fix commit only. Method: read the full diff
against `task-7-rereview.md`, `task-7-fix-round-1-report.md`, and the surfaces it
touches (`AppModel`, `RepoWatcher`, `PrintworksApp`, `MainWindow`, `Theme`,
`pipeline/status.py`, `pipeline/driver.py`). Both gates re-run independently.
Two findings are backed by measurements taken here, not reasoning.

## Verdict

**Task 7 does not ship yet. One more small round — roughly ten lines in
`PreviewImage.swift` and three in `AppModel.applyRunResult`.**

M1 (watcher lifetime) and M3 (`--force` escalation) are **done and confirmed**.
m4 is done and holds across the range the controller did not sample. M2's stated
defect — a 25 MP JPEG re-decoded on the main thread on every body pass — is
genuinely fixed: there is now a real hash-keyed cache, the decode is off
MainActor, and `.task(id:)` does not re-fire on a body invalidation. I verified
that by reading and I believe it.

What blocks is that the cache has **no bound and no reclamation path that can
reach the entries that actually accumulate**. Measured on the real preview file:
one grid card, one ordinary window resize across 140 pt, retains **178.9 MB
permanently**. That is a Major of the same weight as the one it replaced, in the
same file, and it is worth fixing now for the same reason the last round gave
for M2 — `PreviewImage.swift:60-61` advertises itself as the loader for "grid
cards, sidebar thumbnails, **and the review canvas**." Task 8's canvas is a
full-window image that resizes with the window: the single worst consumer of a
cache keyed on exact pixel size with no eviction.

Nothing here is a Critical. No repo write, no subprocess, no pipeline logic in
Swift, no path that can approve or destroy photo data, and — checked
specifically — no path that can reach `--force` (M3 answer below).

### Gates, re-run here

- `swift test --disable-sandbox --package-path app/PrintworksCore` → exit 0,
  **60 tests**, 0 failures. Matches the controller.
- `xcodebuild … OTHER_SWIFT_FLAGS='$(inherited) -disable-sandbox' build` →
  exit 0, `** BUILD SUCCEEDED **`, no errors. Matches the controller.

---

## Findings

### M1 — Major: the preview cache is unbounded and grows permanently on window resize

`app/RAWdogPrintworks/Sources/PreviewImage.swift:17` (the plain `Dictionary`),
`:49-51` (the only reclamation path), `:74` (the key's size component), with
`app/RAWdogPrintworks/Sources/GridView.swift:30`
(`GridItem(.adaptive(minimum: 260))`).

The cache key is `(contentHash, maxPixelSize)`. `maxPixelSize` is
`Int(ceil(max(width, height) * displayScale))` — derived from the live
`GeometryReader` size, so a 1 pt change in card width is a new key at 2×. The
grid's column width varies **continuously** with window width: for content width
W, `n = floor((W + 16) / 276)` columns of `(W - 16(n-1)) / n` points each.

The only reclamation is `evict(contentHash:)`, called from `load()` at `:117-119`
and only when a live view's **content hash** changes. During a resize the hash
does not change, so nothing is ever evicted. There is no count limit, no cost
limit, no LRU, and no memory-pressure purge — it is a bare `Dictionary`, not an
`NSCache`.

Measured against the real preview (`~/Projects/rawdog-printworks/previews/
P1036163_natural_preview.jpg`, 5784×4344, 6.3 MB), replicating
`PreviewImageCache.image(...)` exactly, including all four `CGImageSource`
options:

```
maxPixelSize    84 ->   84x63 ,  0.02 MB retained, decode 69.5/54.2/52.5 ms
maxPixelSize   520 ->  520x391,  0.78 MB retained, decode 55.2/53.5/54.7 ms
maxPixelSize  1200 -> 1200x901,  4.12 MB retained, decode 98.6/44.2/42.3 ms

resize sweep 260 -> 400 pt @2x, ONE card, content hash unchanged:
  141 distinct cache keys, 141 decodes, 7185 ms of decode work
  retained after sweep: 178.9 MB   (evict() never runs)
```

Failure scenario: user drags the window wider by 140 pt, or clicks zoom once.
Each intermediate column width mints a new key. Superseded requests *are*
dropped — `.task(id:)` cancels the previous task and the actor's
`guard !Task.isCancelled` at `:24` sees the caller's cancellation, so queued
intermediates bail without decoding. That caps the rate but not the total: the
actor is serialized across every `PreviewImage` in the app and each decode is
~50 ms, so roughly **20 entries per second complete and are retained forever**.
At the measured 1.27 MB average across that band, a sustained drag grows the
process by **~25 MB/s that is never reclaimed**. 178.9 MB is the upper bound for
one card over one 140 pt sweep; a session with a few resizes and one
maximize/restore is comfortably in the hundreds of MB, and it only ever goes up.

Note the second-order point in the numbers above: because
`kCGImageSourceCreateThumbnailFromImageAlways: true` is set, the 25 MP image is
fully decoded regardless of target — the sidebar's 84 px thumbnail costs
**52 ms**, more than the 33 ms the last round measured for the old
`NSImage(contentsOf:)` path. Per call this is *slower* than what it replaced. It
wins overall only because it is off the main thread and, in the steady state,
cached. That makes the cache's correctness load-bearing rather than incidental.

Fix — one line does most of it: quantize the size before it enters the key.

```swift
// PreviewImage.swift:74
let raw = Int(ceil(maxPointSize * displayScale))
let maxPixelSize = (raw + 255) / 256 * 256   // 256 px ladder
```

That collapses the measured sweep from 141 keys / 178.9 MB to 3 keys / ~6 MB,
and — because the request stops changing for most size deltas — it also removes
most of m2 below for free. Pair it with a bound (`NSCache` with a
`totalCostLimit`, or an LRU capped at ~40 entries) so the cache is bounded by
construction rather than by the eviction path happening to fire.

### m2 — Minor: every size change blanks the card to the grey placeholder

`app/RAWdogPrintworks/Sources/PreviewImage.swift:122` (`preview = nil`,
unconditional), with `:98` (`.task(id: request)`) and `:88-95` (the placeholder).

`load()` clears `preview` before awaiting, on **every** `.task(id:)` firing —
including a pure size change where `loadedHash == nextHash` and the correct
behaviour is to keep showing the current pixels while a better-sized one loads.

Failure scenario: drag the window edge. Every visible card drops to
`Theme.canvas` + the `photo` glyph immediately, then waits on a single
serialized actor at ~50 ms per decode. Eight visible cards is ~400 ms to refill
even when the drag stops; while it continues, the grid stays grey. The same
flash fires on `LazyVGrid` recycling — scroll a card out and back and it blanks
for one actor round-trip even on a cache hit, because the hit still costs a hop
behind whatever is queued ahead of it.

The old code hitched the main thread but never blanked. This is a perceptual
regression, not a correctness one — but it is on an ordinary interaction and it
is two lines:

```swift
// PreviewImage.swift:116-122
if loadedHash != nextHash {
    if let loadedHash { await PreviewImageCache.shared.evict(contentHash: loadedHash) }
    loadedHash = nextHash
    preview = nil            // move inside: only blank when the photo changed
}
guard let request else { preview = nil; return }
```

### m3 — Minor: `lastFailures` is a per-command result rendered as per-photo state, so m5's new badge lies in two directions

`app/PrintworksCore/Sources/PrintworksCore/AppModel.swift:662-664`
(`lastFailures` assigned wholesale), read at
`app/RAWdogPrintworks/Sources/GridView.swift:73`. `performRefresh`
(`AppModel.swift:235-250`) never touches it.

Two facets, one root cause — `lastFailures` is replaced by whatever the *last
run* reported, and the new badge treats it as durable per-photo truth.

**(a) Retrying one failure erases the other failures' badges.** `retryRender(stem:)`
→ `runStem` → `runCycle` → `applyRunResult`, which does
`lastFailures = result.failed.reduce(...)`. `run --stem S --json` reports only S.
Scenario: `run` over 40 photos, A/B/C fail → three badges → user clicks Retry on
A → A succeeds → `result.failed` is empty → `lastFailures = [:]` → **B and C's
badges vanish while B and C are still unrendered.** The user is back in exactly
the state m5 was filed to fix, and worse, because they now believe it is clear.

**(b) The badge never clears from disk truth.** Scenario: `run` fails on P1 →
badge. User fixes it in Terminal and runs `scripts/process.sh run`. FSEvents
fires, the app refreshes, P1's state becomes `verified` — and the card now shows
a green "Published" chip **and** a red "Render failed" badge simultaneously,
permanently, until some in-app `run` happens to overwrite the dictionary.

Fix: merge rather than replace, and clear a stem's entry when the refreshed
snapshot no longer justifies it — e.g. in `applyRunResult` remove the stems in
`result.published`/`result.advanced` and merge the new failures, and in
`performRefresh` drop entries for any stem whose state is `verified`.

### m4 — Minor: the new render-failed badge reintroduces the defect m4 was filed for

`app/RAWdogPrintworks/Sources/GridView.swift:73-93` — `:88`
(`Color.red.opacity(0.9)`), `:85` (`.foregroundStyle(.white)`), `:77-80` (the
`.borderless` Retry button), `:90-92` (the expanding frame).

The commit correctly replaced the photo-sampling `.ultraThinMaterial` on the
state chip with `Theme.panel.opacity(0.85)` — and then added a second badge that
is also translucent over the photo.

Computed the same way the last round measured, white on `Color.red` at 0.9 over
the extremes of what can be underneath:

| photo under the badge | composited chip | contrast vs. white |
|---|---|---|
| blown-out highlight | `(255, 88, 78)` | **3.11 : 1** |
| dark shadow | `(230, 62, 52)` | **4.11 : 1** |

`.caption.weight(.semibold)` is ~10 pt — not "large text", so the bar is 4.5:1
and it misses across the whole range. Far milder than the 1.45:1 it replaces,
but it is the same mistake in a new place. Use an opaque fill.

Two more on the same badge, both cheap and both unverified because nobody has
rendered it:

- **The Retry label may be invisible.** On macOS, `.buttonStyle(.borderless)`
  draws its title in the accent colour, which commonly wins over a
  `.foregroundStyle(.white)` inherited from an ancestor. If it does here, system
  blue `(10, 132, 255)` on that red is **1.13 : 1** — unreadable. If
  `.foregroundStyle` wins, it is the 3.11–4.11:1 above. One screenshot of a card
  with a failure settles which. Setting `.foregroundStyle(.white)` on the
  `Button` itself makes the question moot.
- **It collides with the state chip at minimum column width.** At the grid's
  260 pt minimum the inner ZStack is 240 pt; the left chip runs to roughly
  x≈118 and the right badge starts at roughly x≈86. My glyph-width estimates are
  ±20%, so treat the exact overlap as approximate — but the two badges are
  budgeted at ~250 pt of content in a 240 pt box, and the adaptive grid returns
  to exactly 260 pt at every column-count boundary. Give the badge
  `.lineLimit(1)` and a `layoutPriority`, or drop the word "Render".

### i5 — Informational: the M1 fix promoted m6 from "close to unreachable" to routinely reachable

`app/PrintworksCore/Sources/PrintworksCore/RepoWatcher.swift:336-339`.

**Not counted against shipping** — m6 is out of scope per the dispatch. Flagging
it only so the whole-branch review does not re-triage m6 on a premise that is no
longer true. Last round concluded "the retain path is close to unreachable in the
app as written: the only window where the watcher is live with zero consumers is
between a continuation's `onTermination` and the `defer`'s `stop()`" — i.e.
microseconds. Removing that `defer` is exactly what M1's fix did. The
zero-consumer-with-live-watcher window is now **the entire time the app is
running with no windows open**, which on macOS is an ordinary state.

Impact is unchanged and still negligible: the stale `firstPendingChangeAt` costs
one uncoalesced `status` on the next change, and a newly opened window calls
`await model.refresh()` at `PrintworksApp.swift:50` before anything else, so
nothing is stale on reopen. The one-line fix m6 proposed still applies.

### i6 — Informational: `RepoWatcher.deinit` is dead code in production, and that is fine

`RepoWatcher.swift:82-84`, `PrintworksApp.swift:7, 29`.

Confirming the dispatch's question 2 explicitly. The watcher is a `let` on the
`@main` `App` struct; SwiftUI holds that value for the process, so `deinit` fires
at process teardown if at all. `stop()` is therefore never called in production —
grep confirms no other caller anywhere in `app/`. That is not a leak: the
resource is a fixed 11 file descriptors, one per entry in `watchedDirectories`
(`RepoWatcher.swift:10-22`), bounded by construction, and the OS reclaims them at
exit. The `deinit` path remains live for the test suite.

One consequence worth knowing: if the last window closes while
`busyExternally` is true, nothing calls `stopPolling()` — `updatePolling()` only
runs from a live window (`PrintworksApp.swift:37-39, 54, 61`) — so the 5 s poll
timer runs forever in a windowless app. It emits into zero continuations and
self-corrects when a window reopens. Not worth a change.

---

## Answers to the dispatch's four questions

**1. M2's cache under real load.**

*Correctness: sound.* I chased the one hazard that adding a cache creates and it
does not exist here. `run` writes previews via `os.replace(tmp, final)`
(`pipeline/driver.py:138`) — an atomic rename, so a reader sees a complete old or
complete new file, never a torn one. Without that, a truncated JPEG would be
memoized **permanently** under the new hash (the request would not change again,
so `.task` would never re-fire), where the old re-decode-every-pass code would
have self-healed on the next refresh. It is atomic, so it does not happen.
`preview_hashes` is computed from the file's real bytes
(`pipeline/provenance.py:16`), so a key always describes bytes that existed.

The hash→request→evict→reload sequence on a live re-render is correct: hash
changes, old entries go, the card blanks (correct — the old pixels are stale),
the new file decodes. And the headline win is real: in the steady state
`PreviewRequest` is unchanged across body invalidations, so `.task(id:)` does not
re-fire, and neither `performRefresh` reassigning `snapshot` nor a progress event
mutating `renderProgress` costs a decode. `@State` survives those invalidations
because `ForEach(visiblePhotos, id: \.stem)` (`GridView.swift:42`) gives each card
stable identity. **The 265 ms-per-invalidation main-thread block is gone.**

Also checked and clean: the new `request()` guard requires *both* a path and a
non-empty hash where the old code required only a path. That is not a
regression — `pipeline/status.py:38-39` sets `previews[style]` from
`hashes[style] is not None`, so the two are non-nil together by construction.

*Your (a) — is the per-size churn worth bounding?* Yes, and it is the blocker.
See M1: 178.9 MB measured from one resize of one card, never reclaimed. Your
instinct was right and understated.

*Your (b) — does evicting by `contentHash` alone kill the sidebar's live 42 pt
entry?* No, and the framing is inverted. The grid and the review sidebar never
coexist in one window (`SidebarView.swift:10-14` shows photo rows only when
`showingReview && selectedStem != nil`, which is exactly when `MainWindow`
swaps `GridView` out for `ReviewScreen`). Even across the two windows M1's fix
now supports, both read the same shared `AppModel.snapshot`, so their hashes
change in lockstep and the eviction only ever removes the hash they are both
leaving. Nothing live is lost — it is waste, and trivial waste.

The real problem with `evict(contentHash:)` is not that it evicts too much but
that it is **the wrong axis and the only axis**: it fires only when a live view
changes hash, so it reclaims the one thing that costs nothing to keep (a
superseded hash nobody will request again) and can never reach the two things
that grow — old sizes for a still-live hash, and every entry belonging to a view
that was destroyed by scrolling or a window close.

**2. Is M1's fix complete?** Yes, on both halves.

*Does anything still stop it early?* No. `grep -rn "\.stop()"` across
`app/RAWdogPrintworks/Sources/` and `app/PrintworksCore/Sources/` returns exactly
one production call site: `RepoWatcher.deinit`. `PrintworksApp` touches the
watcher only at `:49` (`changes`), `:53` (`start()`), `:67`/`:69`
(`startPolling`/`stopPolling`). A closing window's `.task` cancellation ends its
`for await`, which fires the stream's `onTermination`
(`RepoWatcher.swift:70-72`) and removes **only that consumer's** continuation via
`removeContinuation(_:)` (`:364-368`); `emitCoalesced` then yields to every
continuation still registered (`:346-348`). The survivor cannot be stranded.

*Does the app leak it instead?* No — see i6. Fixed 11 descriptors, reclaimed at
exit.

*One thing the fix depends on that nobody has stated:* every window's `.task`
calls `watcher.start()`, so `start()` must be idempotent or ⌘N would double the
sources. It is, deliberately — `startWatching` bails on
`guard watches[relativePath] == nil` (`RepoWatcher.swift:237-240`), documented at
`:87-88`. Your lsof measurement actually proves this too, which is worth noticing
because it is not what you were testing for (below).

**3. m5's badge and `retryRender(stem:)` — can it reach `--force`?** No. Traced
every edge:

- `retryRender(stem:)` (`AppModel.swift:635-637`) → `runStem(_:)` (`:644-647`) →
  `runCycle(args: ["run", "--stem", stem, "--json"])`. No `--force`, and
  `runStem`'s own retry closure is `runStem`, so a repeated failure cannot
  escalate on the second click either.
- `ingest`'s run-failure branch (`:608-610`) now retries `runAll()` (`:639-642`)
  → `["run", "--json"]`, whose retry closure is also `runAll`. M3 closed.
- `--force` survives only where it should: `reprocess(stem:)` (`:622-626`) and
  `reprocessAll()` (`:629-632`), both reachable only from the toolbar Reprocess
  menu (`MainWindow.swift:73-86`), correctly disabled on
  `busyExternally || activeCommand != nil`.

*No UI path reaches a mutating command without explicit user action.* The four
entry points are the drop destination (`MainWindow.swift:45-48`), the Reprocess
menu, the banner Retry (`AppModel.retryBannerAction`, gated on
`bannerAction == .retry`), and the new card Retry — which is itself disabled on
`busyExternally || activeCommand != nil` (`GridView.swift:81-82`), matching the
menu's gate. No timer, no watcher path, no `onAppear` reaches any of them.

**4. What the fix broke.** m2 (the resize/scroll blank — a perceptual regression
against the old code, which hitched but never blanked), m3(a) (retrying one
failure erasing the others' badges — a defect inside the new m5 feature), m4 (a
second photo-sampling badge added while fixing the first), and the i5
reachability change. Nothing previously-correct in the *reviewed* behaviour
regressed: the status-dot mapping, sidebar levels, pipeline block, drop target,
empty state, busy pill and §7's banner actions are untouched by this diff, and
the `AppKit` imports dropped from both view files were used only for `NSImage`.

---

## On the controller's verification

Better than last round, and two of the three things you did are stronger than
you claimed. Where it falls short, it falls short in one specific and important
way.

- **The lsof check is the best evidence in the round, and it proved more than you
  were testing for.** 11 FDs is exactly `RepoWatcher.watchedDirectories.count`
  (`:10-22`) — so the count is meaningful, not coincidental. Stable across ⌘N/⌘W
  gives you two results: the close did not cancel the sources (what you were
  after), *and* the second window's `start()` did not duplicate them, which is
  the idempotency the multi-window fix silently depends on.
  **The gap:** open descriptors prove the sources survive; they do not prove the
  surviving window still *receives*. A hypothetical bug where the survivor's
  `for await` had ended would leave all 11 FDs open and the window frozen — your
  measurement cannot distinguish that. I closed it by reading (question 2 above)
  and I am confident, but the direct test is 15 seconds and touches no photo
  data: ⌘N, ⌘W, `touch ~/Projects/rawdog-printworks/run/.probe`, watch the
  survivor refresh. Worth doing precisely because "airtight by reading" is what
  we said about M1 the round before it was found.
- **The 6.13:1 measurement holds outside the range you sampled.** Working back
  from your `(46,47,50)` against `Theme.panel = (20,20,22)` at 0.85, the photo
  under both badges was ~193, not a true blown-out highlight. I extended it: at
  pure white underneath the chip composites to `(55,55,57)`, giving **5.44:1**
  for the green "Published" and **4.25:1** for the dim grey "Ingested" — the
  worst case across all four status colours. m4 is robustly fixed, not just
  fixed at the sample you had.
- **The M3 mutation is exactly the right test**, and restoring `--force` to
  `runAll()` killing both assertions is what makes M3 settled rather than
  claimed.

**Where it was insufficient — and this is the part worth acting on:**

- **"60 tests pass" is evidence for M3 and nothing else.** The Xcode project has
  exactly one target and it is an application — `grep productType
  project.pbxproj` returns a single
  `com.apple.product-type.application`, no test target. `swift test
  --package-path app/PrintworksCore` cannot reach `PreviewImage.swift`,
  `GridView.swift`, `SidebarView.swift`, or `PrintworksApp.swift`. Every line of
  M1's, M2's, m4's and m5's implementation is covered by compilation only. The
  gate is not lying, but it is answering a narrower question than "the fix
  works", and the fix report's "Evidence: app build exited 0" for m4 and m5 is
  an accurate description of that.
- **M2 *was* verifiable without touching irreplaceable photo data — just not by
  the route you were looking down.** You were right that observing the cache
  during a live render needs a real render. But the two defects that actually
  matter need no render at all: open the app on the existing two-photo smoke
  repo, watch RSS in Activity Monitor, and drag the window edge back and forth
  for ten seconds. M1 above shows up as tens to hundreds of MB that never come
  back, and m2 shows up as the grid going grey while you drag. Both are pure
  read-path behaviour against previews that already exist. That is the single
  most useful correction I can give you: the constraint you were respecting
  (don't run the pipeline on irreplaceable data) did not actually block the
  question you needed answered.
- **m5 has never been rendered by anyone.** The smoke repo has no failures, so
  the new badge, its contrast, its Retry button colour and its collision with the
  state chip at 260 pt are all unobserved — which is why m4 above is partly
  arithmetic rather than pixels. A scratch repo with a deliberately broken
  toolchain, or a `FakeClient`-driven preview, would produce the one screenshot
  that settles all three.

---

## What I did not check

- Did not launch the app. M1's completeness and M2's steady-state cache-hit
  behaviour are reasoned from the code and the SwiftUI `.task(id:)` lifecycle;
  the memory and decode-cost numbers are measured on the real preview files with
  a standalone harness that replicates `PreviewImageCache.image(...)` including
  all four `CGImageSource` options, not profiled inside the running process.
- Did not run the pipeline. The atomicity conclusion in answer 1 is read from
  `pipeline/driver.py:102-139`, not observed during a render.
- Did not verify whether `.buttonStyle(.borderless)` overrides an inherited
  `.foregroundStyle(.white)` on this macOS version — flagged in m4 with the
  contrast for both outcomes rather than asserted.
- Did not re-litigate m6–m10, i11/i12, or the earlier deferred items, per the
  dispatch. i5 above reports a change in m6's *reachability* only and is
  explicitly not counted against shipping.
- Did not re-review `ReviewScreen` (Task 8) or the missing Settings scene
  (Task 10).

## What has to land before Task 7 ships

1. **M1** — quantize `maxPixelSize` onto a ladder (`PreviewImage.swift:74`) and
   put a bound on the cache (`:17`).
2. **m2** — move `preview = nil` (`:122`) inside the hash-changed branch.
3. **m3** — stop `applyRunResult` (`AppModel.swift:662`) from clobbering other
   stems' failures, and clear entries that disk truth has invalidated.

m4 is a judgement call — the badge is unobserved and cosmetic, and it would be
reasonable to hand it to Task 11's visual QA along with i11. If it is deferred,
say so explicitly rather than letting it lapse, because it is the same defect
class the round just fixed.
