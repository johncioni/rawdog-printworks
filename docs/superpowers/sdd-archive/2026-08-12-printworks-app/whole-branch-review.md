# Whole-branch review — `johncioni/plan2-printworks-app`

Reviewer: Opus 5 xhigh. Scope: the branch as a whole against `main`, per
`whole-branch-review-dispatch.md`. Tasks were **not** re-reviewed individually;
m12 was **not** reopened.

## Verdict

**Yes — this branch should merge to `main` as-is.**

The reasoning is at the bottom, after the evidence.

---

## Ground truth, re-derived rather than taken on faith

**The branch's real change set is the three-dot diff.** `git diff main..HEAD`
shows ~14k deleted lines under `docs/superpowers/sdd-archive/` and looks
alarming; that is main moving forward (`f8546a4`, `afcaadc`, `e901e9e` archived
the ledgers) while the branch predates it. `git diff main...HEAD` from the merge
base `60facc9` is the truth: **38 files, +7153 / −58** — the whole of `app/`,
`scripts/build-app.sh`, three `.gitignore` lines, HANDOFF churn (out of scope),
and one widened golden fixture. Nothing on this branch deletes anything from
main. A merge (not a rebase onto an older tip) is safe.

**Gates, re-run by me just now, in this checkout:**

| gate | result |
|---|---|
| `swift test` (`app/PrintworksCore`) | **exit 0** — `Executed 85 tests, with 0 failures` |
| `.venv/bin/python -m pytest tests/ -q` | **exit 0** — `295 passed, 1 skipped` |

**The one pipeline-side change is safe and is an improvement.** `a3e8363` widens
`run_partial_failure.json` / `run_stream.ndjson` to carry a second failed stem
with a *different* code (`RENDER_FAILED` beside `VERIFY_FAILED`) and drives it
from a real `render.RenderError` in `tests/test_json_contract.py:315-365`. It
adds a case to the golden fixtures; it changes no existing field, shape or
spelling. `ContractTests.swift:126-140` pins the same property from the Swift
side. This is the fixture getting *stricter*, not drifting.

---

## Findings, severity-ordered

### F1 (Major) — Approve is live on an already-published photo, and a second approval republishes it and deletes the previous version

`AppModel.swift:524-530` (`canApprove`), `InspectorView.swift:182-190`.

`canApprove` gates on draft freshness, `stalePreviews.isEmpty`, no active
command, and the three audit checks. It never looks at `photo.state`. Nothing
downstream re-imposes that gate: `driver.approve_review` (`pipeline/driver.py:492-551`)
validates the audit, the crop windows and `expected_review_revision`, then writes
`state = "approved"` unconditionally.

**Failure scenario.** P1 is `verified`, published as v001, crops persisted,
previews fresh. The user opens P1 in Review to look at it. `InspectorView`'s
`.task` (`:36-44`) creates a fresh draft with all three checks false — and
nothing on the review screen says this photo is already published. The user ticks
the three boxes and clicks Approve:

1. `approve_review` succeeds — the fingerprint is unchanged (crops unchanged;
   `recipe.fingerprint` covers `crops` but not `approval`/`expression_audit`,
   `pipeline/recipe.py:107-124`), so `expected_review_revision` matches — and
   **demotes the manifest from `verified` to `approved`** (`driver.py:547-550`).
2. The app chains `run --stem P1` (`AppModel.swift:711-718`). `process_all` takes
   the `approved` branch (`driver.py:770-786`), finds no stale artifacts, so
   renders nothing and calls `_finish_verified`.
3. `verify_photo` finds no staging dir and re-stages **from the published tree**
   (`driver.py:415-419` → `_stage_published`, `:239-252`); `_publish_photo` then
   renames those same bytes into **v002**, swaps `current`, and
   `shutil.rmtree`s v001 (`publish.py:150-152` prunes every older version).
4. `onPublished` fires: *"P1 published (v002, 29 files)"*.

Content is byte-identical, so no pixels are lost — this is not the
"publish something unapproved" catastrophe. The costs are real but bounded: the
published tree is rewritten and version-bumped for no reason, a spurious publish
notification fires, and if `_stage_published` raises (a missing artifact), the
photo is left **demoted to `approved` in the manifest while v001 is still the
live symlink** — the grid then shows "Rendering" for a photo that is published,
until a later `run` repairs it.

**Verdict: fix now.** It is a one-line gate in `canApprove` (`state` must be
`preview_ready` or `review_required`) plus a test. It closes the only path where
the app rewrites published output without the user intending to.

### F2 (Major) — "Reprocess ▸ All Photos" is one unconfirmed click into an uncancellable whole-repo `run --force`

`MainWindow.swift:85-87` → `AppModel.swift:871-874` → `run --force --json`.

The menu item sits directly under "This Photo", has no confirmation, no summary
of what it will do, and — per m12, correctly — no cancel. Once dispatched, every
photo at `rendered`/`verified` is force-downgraded (`driver.py:749-751`), fully
re-rendered through RawTherapee, and republished as a new version with the
previous version `rmtree`d. On a real delivery that is hours of work with no exit
but quitting the app, which orphans the subprocess mid-render.

**What the sweep found in `--force`'s favour** (this was cross-seam question 2,
and the answer is good): `--force` **cannot** bypass the approval gate.
`_force_downgrade` only touches `("rendered", "verified")`; `ingested`,
`preview_ready` and `review_required` fall through to their normal branches
(`driver.py:753-769`). And `process_all` refuses the whole batch on render-tool
drift *before* any render (`driver.py:715-722`), so a forced re-render always
reproduces the approved pixels rather than silently producing new ones. The
Reprocess menu is also correctly disabled on `busyExternally || activeCommand != nil`
(`MainWindow.swift:91`).

**Verdict: fix now** — a `.confirmationDialog` naming the photo count. The
cancel question stays closed per m12.

### F3 (Minor) — the drop target is the one mutating affordance with no re-entrancy guard

`MainWindow.swift:50-53`. Every other path is gated on
`busyExternally || activeCommand != nil`; `dropDestination` fires
`Task { await model.ingest(...) }` unconditionally and returns `true` regardless.

**Failure scenario.** Two quick drops start two overlapping `ingest` cycles. The
second `beginCommand` bumps `commandGeneration` (`AppModel.swift:976-981`), so
the first drop's progress events are discarded; then the **first** cycle's
`endCommand` (`:986-992`) clears `activeCommand`/`activeStem` while the second
ingest is still running. Every affordance gated on `activeCommand != nil` —
Approve, Reprocess, Retry, the sliders — unlocks mid-ingest. The pipeline's
`O_EXCL` lock keeps the data safe (the second mutation gets `LOCK_HELD` → busy
pill); what breaks is the app's own busy bookkeeping. This is m7's case 3, still
open, and it is the sharpest of m7's three.

### F4 (Minor) — the 8×10 crop is undraggable wherever 5×7 covers it, and the mis-grab is carried into the approval

`CropOverlayView.swift:15-24` and `:45`. Both outlines set
`.contentShape(Rectangle())` over their whole area, and the `ForEach` draws
`5x7` last, so 5×7 is on top. With the fixture geometry
(`crops_suggested.json`: 8×10 at w=0.938/h=1.0, 5×7 at w=1.0/h=0.952) the only
grabbable 8×10 region is a thin band outside the 5×7 rect.

This is n13, and it is worse than "a small hit region": a user aiming at the 8×10
outline grabs the 5×7 one, and the resulting nudge is written into the draft
(`AppModel.swift:474-478`) and carried verbatim into the review file
(`:744-761`), so they approve a 5×7 window they never meant to move. There is no
undo and no per-crop indication in the inspector beyond a "nudged" tag
(`InspectorView.swift:140-144`).

**Verdict: fix now** — stroke-only hit region, or an explicit selected-crop
toggle. This is one of the app's two core review affordances.

### F5 (Minor) — needs-review counts are computed by string-comparing a display label, in two copies

`MainWindow.swift:131-135` and `SidebarView.swift:178-182` both do
`PhotoStateAppearance(state: $0.state).label == "Needs review"` against the
literal in `GridView.swift:15`. Renaming that string — a pure presentation
change — silently zeroes both counters, with no compiler error and no failing
test. This is m9, unchanged.

### F6 (Minor) — four `public var`s on `AppModel` are never read by any view

`lastAdvanced` (`AppModel.swift:145`), `lastPublished` (`:142`),
`lastIngestFailures` (`:148`), `lastMutatingArgs` (`:153`). Verified by grep
across `app/RAWdogPrintworks/Sources/`. `lastMutatingArgs` is a documented test
seam; `lastPublished` is duplicated by the `onPublished` callback that actually
drives notifications; `lastAdvanced` is dead.

`lastIngestFailures` is n21's real half: per-file failures are collected at
`:921-927` and rendered nowhere, so a partially-failed ingest shows the user only
the `PARTIAL_FAILURE` **count** in the banner ("2 file(s) failed",
`pipeline/__main__.py:247-250`) — never which file or why. The per-file reason
exists in the model and dies there.

### F7 (Minor) — the grid is the one view that is neither keyboard- nor VoiceOver-operable

`GridView.swift:42-47`: cards open on `.onTapGesture(count: 2)` with no `Button`
wrapper, no `.accessibilityLabel`, no `.isButton` trait, no keyboard path. A
VoiceOver user cannot open a photo for review at all. Compare, inspector, sidebar
and the crop outlines are all labelled (`CompareView` `:63`, `InspectorView`
`:81/:98/:112/:126/:159/:173/:189`, `CropOverlayView` `:69-70`) — the grid is the
outlier, which is the honest answer to cross-seam question 4 on accessibility.

### F8 (Minor, latent) — `.convertFromSnakeCase` converts dictionary *keys* too

`Contract.swift:331`, against the `[String: …]` members at `:132-136` and `:214`.
Inert today: `paths.STYLES = ("natural","filmic","bw","vibrant")` and
`paths.CROPS = ("8x10","5x7")` are underscore-free constants
(`pipeline/paths.py:4-5`). Add a style spelled `warm_tone` and `previews`,
`preview_hashes` and `adjustments` come back keyed `warmTone` while `styles` and
`stale_previews` — arrays, and so unconverted — still say `warm_tone`. Every
lookup by style name misses; the style renders "Not rendered" forever and its
staleness never clears. A trap with no failure signal, worth a comment or an
explicit `CodingKey`-free dictionary decode before someone adds a style.

### F9 (Nit) — the e2e smoke test's stub emits a state the pipeline never emits

`SmokeTests.swift:11` uses `"state":"published"`; the terminal state is
`verified` (`driver.py:651`). `PhotoStateAppearance` has no `"published"` case,
so that value falls through to "Ingested" (`GridView.swift:19-22`). The
assertion at `:74-75` only checks the string it fed in, so nothing fails — but
the smoke test does not actually exercise the terminal state the app receives.
One-character fix; worth doing since the brief treats these fixtures as binding.

### F10 (Nit) — a UTF-8 sequence split across pipe reads is mangled in the stderr tail

`PipelineClient.swift:297`: `buffer += String(decoding: data, as: UTF8.self)`
decodes each `availableData` chunk independently, so a multi-byte sequence
straddling a chunk boundary becomes U+FFFD. **Envelopes and events are not
affected** — `jsonio._write` uses `json.dumps` defaults, i.e. `ensure_ascii=True`
(`pipeline/jsonio.py:59`), so stdout is pure ASCII. This is display-only
corruption in "Show Details". Correct fix is to split on `0x0A` in `Data` and
decode per line.

### F11 (Nit) — `RepoWatcher.stop()` blocks its caller, and `AppRuntime.save()` calls it on the MainActor

`RepoWatcher.swift:151-155` waits on each watch's semaphore with a 2 s timeout,
across 11 watched directories; `PrintworksApp.swift:104` calls it from
`AppRuntime.save()` on the MainActor. Bounded (so N1 cannot wedge permanently —
see below), but a stalled cancel handler freezes the UI for up to ~22 s.

### Branch-scale duplication (cross-seam question 5)

Three copies of the `["natural","filmic","bw","vibrant"]` fallback
(`ReviewView.swift:215-219`, `InspectorView.swift:271-275`,
`CompareView.swift:75-79`) and two of `["8x10","5x7"]`
(`InspectorView.swift:134`, `CropOverlayView.swift:15`) — pipeline constants
transcribed into Swift in five places. Combined with F5's two label copies, this
is the branch's one structural smell. No dead seams or abandoned code otherwise,
and **the `#if DEBUG` surface is clean**: exactly one block
(`RepoWatcher.swift:107-117`, two test hooks), and `scripts/build-app.sh` builds
`-configuration Release`, so it does not ship.

---

## The deferred pile — verdict on every item

### From Task 6

| item | verdict | why |
|---|---|---|
| **M1** in-place edits invisible to kqueue | **file** | Real and confirmed: the sources watch directory vnodes (`RepoWatcher.swift:251-254`), so an in-place write to a file inside one fires nothing. Every pipeline writer uses temp+`os.replace` (`recipe.py:41-54`, `publish.py:143`), and the 5 s poll covers a hand-edit within one tick. Exposure is unchanged from when it was deferred. |
| **M2** a re-publish caught only incidentally | **drop** | Confirmed, and the "incidental" mechanism is actually load-bearing and reliable: `Output/photos/<stem>/` is not watched, but `run/` is (`:21`), and **every** mutating CLI command creates and removes `run/driver.lock` (`__main__.py:66-74`, `publish.acquire_lock`). Any CLI-driven publish therefore always produces two watched events. Worth one comment; not worth code. |
| **N1** `start()` no-ops during a `stop()` | **drop** | The premise ("a wedged `stop()` makes it permanent") does not hold: the wait is `.now() + 2` per watch (`:153`) and `stopsInFlight` is decremented unconditionally at `:159-161`, so the window is bounded. The residue is F11, filed there instead. |
| **N2/N3** `changes` contract documentation | **drop — done** | `RepoWatcher.swift:56-58` documents multicast registration and the "register before `start()`" rule, and `PrintworksApp.swift:36-38` follows it with the reason inline. |
| **N4** `FakeClient` residual races | **drop — verified fixed** | `AppModelTests.swift:7-34`: `storedStatusQueue`, `storedStatusCalls`, `storedCropsQueue`, `storedCropsLog`, `activeCrops` and `peakCrops` are all behind `stateLock` now, not just the mutate log. |

### From Task 7

| item | verdict | why |
|---|---|---|
| **m6** stale `firstPendingChangeAt` across a consumer-less gap | **file** | Confirmed live: `emitCoalesced` clears `pendingCoalesce` but not `pendingChange`/`firstPendingChangeAt` when there are no consumers (`RepoWatcher.swift:336-339`), so the next change computes a `maximumDeadline` already in the past and emits uncoalesced. Cost is exactly one extra `status`, which `refresh()`'s gate (`AppModel.swift:260-271`) absorbs. |
| **m7** silent drop target | **fix now (case 3 only)** | Cases 1–2 are genuinely low-value. Case 3 is F3 above and deserves the guard. |
| **m8** indeterminate spinner vs §5.2's compact bar | **file** | Unchanged (`MainWindow.swift:69-75`). Notable only because the determinate fraction *is* already available — `renderProgress` carries `index`/`total` and `GridView.swift:129-134` already computes it. Cheap when someone touches the toolbar. |
| **m9** counts via display-label string compare | **fix now** | F5. Two copies, silent failure mode, ~10 lines to give `PhotoStateAppearance` a real enum case. |
| **m10** delivery-filter rule in three copies | **drop — no regression** | Task 9's collapse held: `GridView.swift:121-127`, `MainWindow.swift:106-117` and `SidebarView.swift:159-163` all route through `model.photos(inDeliveryOf:)` / `model.deliveries()`. What remains duplicated is the two-line double-optional unwrap, not the rule. |
| **i5** M1's fix made m6 routinely reachable | **acknowledged; folds into m6** | The premise is right (no windows open = live watcher, zero consumers, an ordinary macOS state) and the impact assessment still holds — a newly opened window calls `refresh()` before iterating (`PrintworksApp.swift:39`), so nothing is stale on reopen. |
| **i11** sidebar warm brown vs §5.1's black primary | **file** | `Theme.swift`: `panel` is `#141416` and the sidebar is `.ultraThinMaterial` over it (`MainWindow.swift:11`), with `accent` `#E8A849` doing the warm work. Whether that reads as a §5.1 violation is a visual call I will not make from source, and I deliberately did not launch the app — its default repo path is the user's **live** repo (`PrintworksApp.swift:77-79`), which my read-only constraint forbids touching. |

### From Task 8

| item | verdict | why |
|---|---|---|
| **N3** portrait compare cells waste landscape previews | **file** | Unchanged: `CompareView.swift:9-19` is a fixed 2×2 `Grid` with no aspect awareness. Cosmetic, and it is the one item the visual QA pass already confirmed by eye. |
| **N5** Escape does not close compare | **drop — verified fixed** | `ReviewView.swift:200-203` adds an Escape-shortcut button gated on `showingCompare`, inside the hidden `keyboardShortcuts` overlay (`:176-208`). |

### From Task 9

| item | verdict | why |
|---|---|---|
| **n13** 8×10 hit region is a sliver | **fix now** | F4. Re-scoped upward: it is not just a small target, it silently redirects the nudge into the *other* crop and that nudge is what gets approved. |
| **n14** dead `.onChange(of: model.selectedStyle)` | **drop — verified fixed** | No such handler exists anywhere in `app/RAWdogPrintworks/Sources/` (grep). Matches `task-10-rereview.md:252`. |
| **n15** LRU test never exercised recency | **drop — verified fixed** | `task-10-rereview.md:254`; the suite is green at 85 tests. |
| **n16** residual per-revision crop refetch | **drop — verified fixed, and its overshoot (m13) is fixed too** | The revision is out of both crop task identities (`ReviewView.swift:246-249`, `InspectorView.swift:298-301`), and `28dd02d` restored the retry through `PhotoStatus.cropRetryToken` (`Contract.swift:161-168`), which re-fetches on a readiness change but not on revision churn. |

### From Task 10

| item | verdict | why |
|---|---|---|
| **n18** `pendingInputFiles` matches fewer spellings than the pipeline | **drop — substantially closed** | Both sides now match `.rw2` case-insensitively: `AppModel.swift:312-317` vs `pipeline/ingest.py:146-148`. Residual mismatches are contrived (a hidden `.x.rw2`, a *directory* named `X.rw2`, or a case-differing stem, which would leave the banner up after a no-op ingest). Not worth code. |
| **n19** Settings' Cancel does not revert | **file** | Confirmed: `SettingsSheet.swift:44` only dismisses, and the `@State` fields keep the abandoned edits if the Settings scene stays alive. Mildly confusing, never destructive — Save is gated on validation. |
| **n20** Save is not gated on an idle model | **drop** | I traced the consequence and it is benign: `AppRuntime.save()` (`PrintworksApp.swift:96-110`) swaps in a new model and watcher; the in-flight command holds the old model and completes against it, and the new model's `status` re-derives the busy pill from the driver lock, which is the authority. The user loses sight of the running command's progress; nothing corrupts. |
| **n21** notifications have no body, `lastIngestFailures` renders nowhere | **split: body → file; ingest failures → fix now** | The empty body is cosmetic (`PrintworksApp.swift:167-169` puts everything in the title). The unrendered per-file failures are F6 and are a genuine information loss on a partial ingest. Note also that a Reprocess-All posts one notification per photo in a single burst (`:164-174`). |

### From Task 11

| item | verdict | why |
|---|---|---|
| **I1** the ingest→run chain narrowing | **confirm — this is the behaviour we want** | `AppModel.swift:796-804` and `:840-847` chain `run` only when `result.ingested` is non-empty. That is right: a fully-deduped or failed ingest has nothing to render, and chaining would take the driver lock a second time only to re-report the same failure. The skip is not silent — skips and conflicts still surface as an `INGEST_NOTICE` banner (`:812-818`). Keep it. |

### Standing decision

**m12** — not reopened, and I have nothing to add: the rationale in
`PipelineClient.swift:39-47` is sound and correctly names what a real Cancel
would require. Its one downstream cost is that F2 has no exit, which is why F2's
fix is a confirmation rather than a cancel.

---

## Cross-seam questions

**1. Does the app honour the pipeline's state machine everywhere?** Almost. The
approval-fingerprint machinery is honoured correctly and defended twice:
`expected_review_revision` is always the revision the review file was built
against (re-read *after* the slider flush, `AppModel.swift:686-691`), the app
never recomputes pipeline state, `canApprove` refuses on any stale preview, and
`approve_review` independently re-checks both revision and staleness
(`driver.py:510-520`). Backward transitions work through the one shared `rebase`
path (`AppModel.swift:490-498`) with `reconcileDrafts` (`:505-522`) enforcing the
second half of the rule at the terminal refresh. The `current` symlink and
version pruning are never touched from Swift. **The single gap is F1: `canApprove`
has no state gate**, so the terminal state is the one place the app does not
honour the machine.

**2. `--force` reachability.** Swept every path. `--force` appears exactly twice
(`AppModel.swift:866` and `:872`), both reached only from the explicit Reprocess
menu; `approve` appears once, behind `canApprove`; the Task 7 escalation is
genuinely gone — the grid's Retry calls `retryRender` → plain `run --stem`
(`GridView.swift:77-79` → `AppModel.swift:877-889`), and every banner Retry
re-runs its own scoped action (`:951-963`). No affordance reaches a destructive
command without a deliberate user choice. The remaining objection is F2's missing
confirmation, not reachability.

**3. Contract drift.** None. Diffing `Contract.swift` from its introducing commit
`3378ea9` to `HEAD`, the only substantive additions are memberwise `init`s (for
tests) and the computed `cropRetryToken` — no property added, removed, renamed or
retyped, and the decoder configuration is untouched. `cropRetryToken` is a
**computed** property, so it is excluded from `Codable` synthesis entirely: it is
genuinely additive. `ContractTests.swift:19-27` decodes the golden fixtures from
the repo path itself, not a copy, so drift would fail the suite.

**4. Consistency across the four views.** Status mapping is centralised in
`PhotoStateAppearance` and used consistently (F5's fragility is *how* it is
queried, not where it lives). Error surfacing is uniform — one `surface()` path,
one `ErrorBanner`, `LOCK_HELD` always the pill and never a banner. Image loading
is fully consistent: all four views route through `PreviewImage`, which is the
only ImageIO caller and keeps decoding off the MainActor. Accessibility is
consistent except the grid — F7.

**5. Branch-scale.** Covered above: five transcriptions of pipeline constants,
four unread `public var`s, one clean `#if DEBUG` seam that does not ship.

---

## Why it merges

The branch is additive. It creates `app/` and touches the existing tree in
exactly three ways: three `.gitignore` lines, `scripts/build-app.sh`, and one
golden fixture widened to cover a case it previously missed (plus the
out-of-scope `HANDOFF.md` churn). There is no path by
which it can regress the pipeline, and I re-ran both gates to confirm — 85 Swift
tests and 295 Python tests, both exit 0.

The two Majors are worth fixing promptly, and neither is a merge blocker. Both
are UI *gating* defects in a single-user local tool, both need a deliberate
multi-step user action to reach, and — the part that matters — neither can
publish or approve pixels the user did not visually approve. I verified that
claim against the pipeline rather than assuming it: `--force` cannot promote a
photo past visual review, toolchain drift aborts before any render, and F1's
worst case reproduces byte-identical artifacts under a new version number. The
app's central safety property holds.

Holding the merge would not make those fixes safer — they land as commits either
way, and they are cheap: a state check in `canApprove`, a confirmation dialog, a
hit-region change. Merge, then land F1, F2, F4 and the `lastIngestFailures`
surface as a short follow-up round.
