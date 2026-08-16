# Task 7 fix round 2 — re-review — `c9165c2..87511e8`

Reviewer: Opus 5 (xhigh). Scope: the fix commit only (4 files, +112/−11).
Method: read the full diff against `task-7-fix-round-1-rereview.md` (the
findings) and `task-7-fix-round-2-report.md` (the claims), then verified the
three things the controller could not, by execution rather than by reasoning:

- the LRU's accounting and bounds, fuzzed over 400 k operations against a
  verbatim replication of the store;
- the 256 px ladder, measured on the real 5784×4344 preview at every rung the
  app can produce;
- the `lastFailures` lifecycle, probed with a throwaway XCTest run against
  **both** `87511e8` and `c9165c2` (the probe was deleted; the tree is clean).

## Verdict

**Task 7 does not ship on `87511e8`. One four-line change in
`AppModel.swift`, plus one test, and it does.**

M1 is genuinely fixed — the cache is bounded by construction, the accounting is
exact, the eviction order is real LRU, and the wedge path is unreachable. I
proved all four rather than trusting the report, and the report's
268,435,456-byte figure is the correct ceiling. m2 is correct and introduces no
stale-image path. m3's first half — the clobbering — is fixed. m4 is fixed. The
watcher (M1) and `--force` (M3) were not touched, directly or indirectly.

What blocks is m3's **second** half. `performRefresh`'s new "clear entries disk
truth invalidated" filter keys on `state == "verified"`, and a photo that fails
a **forced** re-render is still `verified` on disk — the pipeline says so in its
own docstring, because the previously published version is still in the tree.
So the terminal refresh at the end of `reprocess`/`reprocessAll` deletes the
failure that the same command recorded three lines earlier. The render-failed
badge and its Retry button never appear, and `PARTIAL_FAILURE` maps to no banner
action, so nothing else in the UI names the photo that failed.

This is a **regression this commit introduced**, not an incomplete fix: the same
probe passes at `c9165c2` and fails at `87511e8`. It sits on Task 7's own
toolbar action (`MainWindow.swift:73-82`, Reprocess ▸ This Photo / All Photos).

Nothing here is a Critical. No repo write, no subprocess change, no pipeline
logic in Swift, no path to data loss — the published version survives a failed
forced render intact, which is precisely why the filter misfires.

### Gates, re-run here

- `swift test --disable-sandbox --package-path app/PrintworksCore` → exit 0,
  **62 tests**, 0 failures. Matches the controller.
- `xcodebuild … OTHER_SWIFT_FLAGS='$(inherited) -disable-sandbox' build` →
  exit 0, `** BUILD SUCCEEDED **`. Matches the controller.
- `git diff --name-only c9165c2..87511e8` → exactly the four reported files.
  `RepoWatcher.swift` diffstat: 0 lines. `"--force"` appears at exactly two call
  sites, `AppModel.swift:628` and `:634`, both unchanged.

---

## Findings

### M1 — Major: the new `verified` filter erases the failure the app's own Reprocess just recorded

`app/PrintworksCore/Sources/PrintworksCore/AppModel.swift:249-251` (the filter),
against `:662-672` (`applyRunResult`), `:626-636` (the two `--force` entry
points), `:744` (`endCommand`'s terminal `refresh()`), `:718-725`
(`bannerAction`), read at `app/RAWdogPrintworks/Sources/GridView.swift:73`.
Pipeline side: `pipeline/driver.py:681-692` and `:830-832`;
`pipeline/__main__.py:173-179`.

The filter assumes `state == "verified"` means "the failure has been resolved".
For a forced re-render that is false, and the pipeline documents why in
`_force_downgrade`'s own words:

```python
# pipeline/driver.py:681-687
def _force_downgrade(data, stem):
    """Reset a stem to `approved` in memory so the normal flow re-renders it.

    Nothing is saved here: the downgrade reaches the manifest only when
    `_finish_verified` persists the new version, so a failed forced run leaves
    the manifest describing the version still in the published tree.
    """
```

The downgrade to `approved` is in-memory only; on failure the `finally` at
`:830-832` calls `_restore_forced`, which writes `verified` back. The manifest
on disk never left `verified`, so the very next `status --json` reports
`verified` — and the app deletes the failure.

**Failure scenario** (deterministic, no race required): a published photo's
sidecar is bad, or RawTherapee errors, or the PDF step throws. The user picks
Reprocess ▸ This Photo.

1. `run --stem P1 --force --json` → `failed: [{stem: P1, code: RENDER_FAILED}]`,
   envelope error `PARTIAL_FAILURE` (`__main__.py:177` — **every** run failure
   gets this code, single-stem included; `RENDER_FAILED` never reaches
   `bannerAction`).
2. `applyRunResult` stores `lastFailures["P1"]`. Correct.
3. `endCommand()` → `refresh()` → snapshot says `P1: verified` → the filter
   drops `lastFailures["P1"]`.
4. The card renders a green **Published** chip, no red badge, no Retry button.
   The banner reads "1 of 1 photos failed" with **no action button** —
   `bannerAction(for: "PARTIAL_FAILURE")` falls to `default: return nil` — and
   no stem name. `lastPublished`/`lastAdvanced` are not rendered anywhere
   (`grep` over `app/RAWdogPrintworks/Sources`: no reads).

Reprocess ▸ All Photos is the same path and worse: "3 of 40 photos failed",
zero badges, forty green chips, and no way to learn which three.

**Proven, not reasoned.** A throwaway XCTest driving `model.reprocess(stem:)`
with a verified snapshot and a failing run:

```
87511e8:  XCTAssertNotNil failed - force-reprocess failure erased by the
          verified filter        (mutateLog == ["run","--stem","P1","--force","--json"] ✓,
                                  bannerAction == nil ✓)
c9165c2:  passed (0.003s)
```

Same test file, same command, only `AppModel.swift`/`AppModelTests.swift`
swapped to the parent commit. Before this commit the badge appeared; after it,
it cannot.

The round-1 prescription — "in `performRefresh` drop entries for any stem whose
state is `verified`" — is what was implemented, faithfully. The prescription is
what is wrong: `verified` is a statement about the tree, not about the run.
The two new tests cannot catch this because both drive a stem whose pre-run
state is `review_required`; neither reaches a stem that is verified *before* and
*after* a failed forced run.

**Fix** — clear on evidence that the stem actually moved, not on a state that
never left. `PublishedInfo.version` (`Contract.swift:114-117`) is already in the
snapshot and is exactly that evidence:

```swift
// AppModel.swift:145 — remember what was published when the failure landed
public var lastFailures: [String: StemFailure] = [:]
@ObservationIgnored private var failureVersions: [String: String?] = [:]

// applyRunResult, alongside the existing merge
for failure in result.failed {
    lastFailures[failure.stem] = failure
    failureVersions[failure.stem] = photo(failure.stem)?.published.version
}

// performRefresh:249-251 — a stem clears only if a NEW version was published
for photo in snapshot.photos where photo.state == "verified" {
    guard lastFailures[photo.stem] != nil else { continue }
    if failureVersions[photo.stem] != photo.published.version {
        lastFailures.removeValue(forKey: photo.stem)
        failureVersions.removeValue(forKey: photo.stem)
    }
}
```

That keeps round-1's m3(b) fixed — the external-Terminal repair publishes a new
version, so `v001 != v002` and the badge clears — while a failed forced render,
which publishes nothing, keeps its badge. It also fixes m2 below for free.

Test to add (it is the probe, verbatim): a verified photo, `reprocess(stem:)`
returning `failed: [P1]`, assert `lastFailures["P1"] != nil` after the terminal
refresh. It is RED on `87511e8` today.

### m2 — Minor: a failure whose stem lands anywhere but `verified` is unclearable, and its Retry is a no-op

`AppModel.swift:249-251` and `:662-672`;
`pipeline/driver.py:768-769`.

The surviving half of round-1's m3(b). Failures clear on exactly two signals:
the stem appearing in `published`/`advanced`, or the stem being `verified` in a
snapshot. A stem that resolves into any other state keeps its badge forever.

**Failure scenario:** `run` fails on P1 at the render stage (P1 was `approved`)
→ badge. The user drags a slider in the app → `adjust` rewrites the sidecar →
P1's approval fingerprint changes → P1 transitions backward to
`review_required`. The card now shows an amber "Needs review" chip **and** a red
"Render failed" badge. Clicking its Retry runs `run --stem P1 --json`, which
hits `driver.py:768-769` — `print(f"{stem}: awaiting visual review + approve")`,
no `collect` append at all — so the envelope is `ok: true` with empty
`published`/`advanced`/`failed`. Nothing clears, nothing surfaces, the busy pill
flashes and the badge stays. It persists until the user re-approves *and* a run
publishes.

Derived from the code, not executed — the driver branch is a bare `print` with
no `collect` write, and both clearing paths are keyed off values that stay
empty.

The M1 fix above resolves this too if the version comparison replaces the state
test rather than being added next to it: a stem sitting at `review_required` has
no new version either, but it also has no *stale* claim to make — if you want it
to clear on backward transition, add `photo.reviewRevision` to the stamp and
clear when the revision moves. That is a one-line extension of the same stamp,
and it is the controller's call whether a backward transition should silently
drop the failure or keep it visible until the photo is re-rendered.

### i3 — Informational: `evict(contentHash:)` is now redundant with the LRU, and it invalidates other live views' entries

`app/RAWdogPrintworks/Sources/PreviewImage.swift:74-82`, called from `:150`.

Not counted against shipping — it predates this commit and this round only
adjusted its bookkeeping (correctly; see below). Flagging because the LRU
changes its cost/benefit.

The cache is global; `evict` is keyed on `contentHash` alone and removes every
rung. The sidebar row and the grid card for the same photo share that hash. When
a grid card's hash changes — `LazyVGrid` recycling, a re-preview, a photo
scrolled away and replaced — `load` evicts the hash globally, taking the
sidebar's 256 px entry with it while the sidebar is still displaying that photo.
Nothing breaks visually (the sidebar's `@State preview` holds its own strong
reference), but the next `.task(id:)` firing for that row re-decodes, and a
decode is a full 25 MP source decode on a single shared actor — 75 ms measured
at the 256 px rung.

Before the LRU, `evict` was the only reclamation path and had to stay. Now the
LRU reclaims by itself, bounded and by recency. Deleting `evict` and its call
site at `:149-151` is strictly better: the stale-hash entries it targets are
unreachable by key anyway (the key contains the hash), so they are simply cold
and the LRU retires them in order. Three lines removed, no behaviour lost.

### i4 — Informational: one 256 MiB pool means a Task-8 canvas entry evicts the entire grid cache

`PreviewImage.swift:11-12`.

Measured on `previews/P1036163_natural_preview.jpg` (5784×4344), replicating
`image(...)` with all four `CGImageSource` options:

```
consumer               raw px -> rung    result       bytes retained    decode
sidebar 42pt @2x           84 ->  256      256x192           196,608     75.0 ms
grid card 260pt @2x       520 ->  768      768x577         1,772,544    132.1 ms
grid card 400pt @2x       800 -> 1024     1024x769         3,149,824     43.1 ms
canvas 900pt  @2x        1800 -> 2048     2048x1538       12,599,296     81.8 ms
canvas 1400pt @2x        2800 -> 2816     2816x2115       23,823,360     95.4 ms
canvas 3000pt @2x        6000 -> 6144    5784x4344      100,502,784    151.3 ms
canvas 5000pt @2x       10000 -> 10240    5784x4344      100,502,784    143.9 ms
```

ImageIO clamps at the source, so one full-window canvas entry on this file is
**100,502,784 bytes**. Two of them are 191 MB of the 256 MiB pool; a third
requires evicting everything else first. Task 8's canvas will therefore
periodically flush all forty grid thumbnails, each of which then costs a
full-source decode to refill. Not a Task 7 defect — the bound is doing exactly
what it says — but if Task 8's canvas lands on this cache, a second pool (or a
per-rung cap) is the cheap fix, and it is easier to decide now than after.

Related and equally informational: the LRU has no `DispatchSource`
memory-pressure hook, so it holds its 256 MiB while RawTherapee is rendering
alongside it. `NSCache` would shed under pressure; this will not. 256 MiB is a
defensible fixed budget on the machines this app targets, so this is a note, not
a request.

### i5 — Informational: two of m4's three sub-items were never in the dispatch and remain open

`GridView.swift:73-93`.

The dispatch scoped m4 to the opacity, and the opacity is fixed
(`Color.red.opacity(0.9)` → `Color.red`, `:88`). The controller's smoke on the
true new binary — 5.88:1 and 6.13:1 — clears the 4.5:1 bar, and if those two
figures are the "Render failed" label and the Retry title, they also settle
round-1's open question about `.buttonStyle(.borderless)` drawing its title in
the accent colour (system blue on that red would have measured 1.13:1, not 6:1).
Worth confirming that reading of the two numbers.

The layout collision at the grid's 260 pt minimum column width is still
unverified by anyone: `.lineLimit(1)` was not added, and the badge still expands
with `.frame(maxWidth: .infinity, alignment: .topTrailing)` (`:90-91`) inside a
ZStack that also holds the state chip. Task 11's visual QA is the right place
for it.

---

## Answers to the dispatch's five questions

### 1. Is the cache actually bounded, and is the bound right?

**Yes, and the report's arithmetic is correct.** I replicated the store and its
eviction loop verbatim, swapped the ImageIO decode for a synthetic cost, and
fuzzed 400 k operations — 200 k in the app's real shape (60 hashes × 6 rungs,
padded-stride RGBA costs, an `evict` every 997 ops) and 200 k adversarial
(countLimit 3, costLimit 1000, costs drawn from
`[0, 1, 333, 500, 999, 1000, 1001, 5000]` so entries straddle the limit
exactly), auditing every 1000 ops:

```
ALL INVARIANTS HELD
```

The audited invariants, one per thing the dispatch asked:

- **Is `cost` computed correctly per entry?** `image.bytesPerRow * image.height`
  (`:58`) is the exact size of the decoded pixel buffer, including row padding —
  and `kCGImageSourceShouldCacheImmediately: true` guarantees the decode has
  happened by then, so `bytesPerRow` is real, not a placeholder. The measured
  bytes column in i4 is that product on real files.
- **Can `totalCost` drift from the real sum?** No. Every mutation is paired:
  insert adds the same `cost` the `Entry` stores, both removal sites subtract
  `evicted.cost` from the value they actually removed. Asserted
  `totalCost == images.values.reduce(0, +)` at every audit point across all
  400 k ops — never diverged. The pre-fix code could not do this; storing the
  cost on the entry rather than recomputing it is what makes it exact.
- **Can an entry exceed the limit and wedge the loop?** No, twice over. The
  `guard cost <= totalCostLimit` at `:59` returns an oversized image to the
  caller uncached (fired 45,340 times in the adversarial run, never wedged), and
  the `guard let oldest = recency.first else { break }` escape hatch at `:62`
  was taken **0 times in 400 k ops** — it is unreachable, because `recency` and
  `images` hold identical key sets (asserted, never diverged, no duplicates) and
  the loop condition is false whenever `images` is empty. On real files the
  oversize guard never fires at all: the largest entry ImageIO can produce from
  a 5784×4344 preview is 95.8 MiB, well under 256.
- **Is eviction genuinely LRU, not insertion order?** LRU. The hit path
  (`:36-40`) does `recency.removeAll { $0 == key }` then `append`, so a touched
  entry moves to the back. The ordered test — fill 3, touch the oldest, insert a
  fourth — evicts the untouched middle entry and keeps the touched one, which
  insertion order would have evicted. The fuzz counted **465** operations in the
  app-shaped run where an insertion-order cache would have evicted a different
  entry than this one did.

**The bound itself.** The loop leaves `images.count ≤ 39` and
`totalCost ≤ limit − cost` before the insert, so post-insert `count ≤ 40` and
`totalCost ≤ 268,435,456` — always, and `totalCostLimit − cost` cannot go
negative because of the `:59` guard. The report's **268,435,456 bytes** is the
correct ceiling. Two practical notes on top of it: with 768 px grid cards the
count limit binds first at **70.9 MB** (40 × 1,772,544), and with real
full-canvas entries the reachable peak is ~201 MB (two × 100,502,784), because a
third cannot fit. The report's figure is an upper bound, not a typical
occupancy, and it is right as stated.

### 2. Did quantization break correctness anywhere?

**No.** `(raw + 255) / 256 * 256` never rounds *down* — checked exhaustively for
every input `0...20000`, zero violations — so no consumer ever receives fewer
pixels than it asked for. There is no rung at which the image is softer than
before; every rung is the old size or larger. `quantize(0) == 0`, so the
zero-sized first layout pass still produces a `nil` request and the placeholder,
with no spurious decode. `quantize(1) == 256`, `quantize(256) == 256`,
`quantize(257) == 512` — the ladder is correct at its boundaries.

**On the 42 pt thumbnail sharing a key with a small card:** it is right, and it
is free. The key `(contentHash, maxPixelSize)` fully determines the pixels
ImageIO produces, so any two consumers landing on the same rung are asking for
byte-identical output; sharing is correct by construction, and the only cost is
that the smaller consumer holds a larger image than it strictly needs. In this
app they never actually collide — the sidebar is 42 pt (rung 256) and grid cards
are ≥ 260 pt (rung 768+) — but if Task 8 adds a ≤ 128 pt consumer, sharing is
the desired outcome, not a hazard.

The sidebar's own promotion, 84 px → 256 px, costs 196,608 bytes instead of
~21 KB per row — 8× the memory, 175 KB in absolute terms, at most 7.7 MB if the
sidebar filled the entire cache. It costs essentially nothing in time, which
round 1 already explained and I re-measured: because
`kCGImageSourceCreateThumbnailFromImageAlways: true` forces a full decode of the
25 MP source regardless of target, the 256 px rung and the 84 px one do the same
work. That is what makes the ladder nearly free.

### 3. m2 — can a stale image from a previous request survive into a new one?

**No.** I traced every path into `load` (`:145-165`).

- Hash changes (including → `nil`): `loadedHash != nextHash` → evict, restamp,
  `preview = nil`. The wrong photo cannot survive.
- Hash identical, size changed: `preview` is deliberately kept — and it is the
  *same content hash*, so it is the correct photo at a different rung, redrawn
  by `.resizable().scaledToFill()` until the better rung arrives. That is the
  intended behaviour and the only pixels it can ever show.
- Load fails: `preview = loaded` at `:164` assigns the `nil`, so a failed reload
  after a resize still falls back to the placeholder rather than freezing the
  old image. Moving `preview = nil` did not create a "sticky on error" path.
- Superseded request: `.task(id:)` cancels the old task before starting the new
  one, and the old task's `guard !Task.isCancelled, loadedHash ==
  request.contentHash` at `:162-163` runs with no suspension point before
  `preview = loaded`, so a late low-res result cannot overwrite a newer high-res
  one.
- Cancelled mid-flight (card scrolled off): the actor's own
  `guard !Task.isCancelled` at `:33` returns `nil`, the caller's guard returns
  before assigning, and `preview` keeps the correct-photo pixels for when the
  card returns.

One incidental note: because `image(...)` is a **synchronous** actor method with
no `await` in its body, it executes atomically. That is load-bearing for the
whole store — it is why two concurrent callers for the same key cannot both miss
and double-insert, and it is why the `recency`/`images` invariant holds without
any explicit guard. Worth not breaking if anyone later makes the decode async.

### 4. m3 — both directions, and does the disk-truth half work?

**Direction (a), clobbering: fixed.** `applyRunResult:666-671` removes only the
stems the run reported as published or advanced, then merges the new failures.
`retryRender` on one stem can no longer erase the others. The controller's
mutation — wholesale `removeAll()` turns
`testRetrySuccessPreservesOtherStemFailures` RED with `nil` vs
`Optional("bad two")` — is the right mutation and it lands on the right
assertion. Confirmed.

**Direction (b), disk truth: works for the scenario round 1 described, and
misfires on a scenario round 1 did not consider.** It clears correctly when the
user repairs a photo in Terminal and the pipeline publishes a new version. It
also fires when the same command's own failure is still on screen — M1 above —
and it never fires for a stem that resolves to anything but `verified` — m2
above. Both have the same root cause: `state == "verified"` is a fact about the
published tree, not about whether *this* failure was resolved, and after a
failed `--force` the tree is unchanged by design. The version stamp in M1's fix
addresses both.

### 5. Did this round break anything previously confirmed?

**No.** Checked directly rather than inferred:

- `git diff --name-only c9165c2..87511e8` returns four files;
  `RepoWatcher.swift` has a zero-line diffstat. M1 (watcher lifetime) is
  untouched, and the controller's smoke — 11 watched-dir FDs still held on a
  binary confirmed newer than the process start — re-confirms it at runtime.
- `--force` appears at exactly two call sites, `AppModel.swift:628` and `:634`,
  both outside every hunk in this diff. My probe asserted the argv reaching the
  client on the Reprocess path and it is exactly
  `["run", "--stem", "P1", "--force", "--json"]` — that assertion **passed** on
  `87511e8`. M3 (`--force` escalation) is intact.
- The new work added to `performRefresh` is one `Set` construction and one
  dictionary filter over the photo list, on MainActor, with no lock, no actor
  hop, and no I/O. It cannot affect the refresh gate, the watcher's coalescing,
  or FD lifetime.
- The one thing this round *did* break is inside its own m3 fix, and it is M1
  above.

---

## On the controller's verification

It was sound, and it was not sufficient — through no fault of method.

The gates, the m3 mutation, and the smoke each verified what they claimed. The
m3 mutation in particular is the right kind of check: it targets the assertion
that would silently pass on a weaker implementation. The stale-instance
discipline on the smoke (build time 16:17:56 vs process start 16:18:45) is
exactly the check that matters for a badge-contrast measurement.

What it could not reach is the interaction, because both new tests drive a stem
whose pre-run state is `review_required`. The defect needs a stem that is
`verified` **before** the run and still `verified` **after** it — a shape that
only a forced re-render produces, and only if you have read
`driver.py:_force_downgrade` to know the manifest never moves. That is a
cross-boundary fact (Swift filter × Python state machine), and the kind of thing
a diff-scoped review is for.

Two smaller gaps worth naming: the smoke measured two contrast figures but the
report does not say which two surfaces they are, which leaves round-1's
`.buttonStyle(.borderless)` accent-colour question technically open (i5); and
nothing has yet rendered a card at the grid's 260 pt minimum with both chips
present.

## What I did not check

- Did not launch the app. The M1 finding is proven at the model layer, which is
  where the defect lives; the badge's absence follows from
  `GridView.swift:73` reading a dictionary that no longer has the key.
- Did not run the pipeline. The `--force`/`verified` behaviour is read from
  `driver.py:681-692`, `:749-751`, `:830-832` and the function's own docstring,
  and from `__main__.py:173-179` for the `PARTIAL_FAILURE` code — not observed
  during a real failed render.
- Did not profile inside the running process. The cache numbers are from a
  verbatim replication of the store and a verbatim replication of
  `image(...)` on the real preview file, both run here.
- Did not re-litigate i5/i6, m6–m10, i11/i12 or any previously deferred item,
  per the dispatch. Did not review `ReviewScreen` (Task 8) or Settings
  (Task 10). i4 above touches Task 8's canvas only as a forward-looking note
  about this cache's sizing, not as a review of Task 8.

## What has to land before Task 7 ships

1. **M1** — stop `performRefresh` (`AppModel.swift:249-251`) from clearing a
   failure unless the stem actually published something new. The version-stamp
   patch above is four lines plus one stored dictionary.
2. **The test** — the probe in M1, verbatim: verified snapshot,
   `reprocess(stem:)` returning `failed: [P1]`, assert the failure survives the
   terminal refresh. It is RED on `87511e8` today, which makes it a real
   regression test rather than a restatement.

m2 is the controller's call — the same stamp resolves it if you extend it to
`reviewRevision`, or it can go to Task 11 with i5, but say which rather than
letting it lapse. i3 and i4 are notes, not requests; i3 in particular is a
three-line deletion that would make the cache strictly better and could ride
along with the M1 fix.

**After that fix, this needs a diff read, not a fourth round.** Everything else
in Task 7 — the bounded cache, the ladder, m2's flash fix, m3's clobbering half,
m4's opacity, and the untouched watcher and `--force` guarantees — is confirmed
done and does not need to be looked at again.

---

## Appendix — the probe, verbatim

Ran as `app/PrintworksCore/Tests/PrintworksCoreTests/ZZRereviewProbeTests.swift`
against both commits, then deleted; the tree is clean. It reuses `FakeClient`
from `AppModelTests.swift`. RED on `87511e8`, GREEN on `c9165c2`.

```swift
import XCTest
@testable import PrintworksCore

@MainActor
final class ZZRereviewProbeTests: XCTestCase {
    private func photo(stem: String, state: String) -> PhotoStatus {
        PhotoStatus(stem: stem, state: state, deliveryId: "d1",
                    ingestedAt: "2026-08-12T00:00:00Z",
                    reviewRevision: "r1", previews: [:], previewHashes: [:],
                    stalePreviews: [], adjustments: [:], crops: [:],
                    expressionAudit: [], published: PublishedInfo(
                        version: "v001", path: "p", artifactCount: 29))
    }

    private func snap(_ photos: [PhotoStatus]) -> Envelope<StatusSnapshot> {
        Envelope(ok: true, result: StatusSnapshot(
            repo: "/r", toolchain: ToolchainStatus(ok: true, failures: []),
            lock: LockStatus(held: false, stale: false, pid: nil),
            styles: ["natural", "filmic", "bw", "vibrant"],
            photos: photos), error: nil)
    }

    /// `run --stem P1 --force` on a published photo: the render fails, the
    /// pipeline restores the manifest to `verified` (driver.py
    /// `_restore_forced`), so the terminal refresh sees `verified` and the
    /// filter deletes the failure the same command just recorded.
    func testForceReprocessFailureOnVerifiedPhotoKeepsBadge() async {
        let fake = FakeClient()
        fake.statusQueue = [snap([photo(stem: "P1", state: "verified")])]
        fake.mutateHandler = { _ in
            Envelope(ok: false, result: RunResult(
                published: [], advanced: [], failed: [StemFailure(
                    stem: "P1", code: "RENDER_FAILED",
                    message: "rawtherapee exited 1")]),
                error: PipelineErrorInfo(code: "PARTIAL_FAILURE",
                                         message: "1 of 1 photos failed")) as Any
        }
        let model = AppModel(client: fake, repo: URL(fileURLWithPath: "/r"),
                             sliderDebounce: .zero)

        await model.reprocess(stem: "P1")

        XCTAssertEqual(fake.mutateLog.first,
                       ["run", "--stem", "P1", "--force", "--json"])
        XCTAssertNotNil(model.lastFailures["P1"],
                        "force-reprocess failure erased by the verified filter")
        XCTAssertNil(model.bannerAction,
                     "PARTIAL_FAILURE maps to no banner action")
    }
}
```
