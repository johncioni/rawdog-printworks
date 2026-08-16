# Batch 1 — gating and safety

Read `README.md` in this directory first; its scope contract binds this brief.

Six items. All are **gating** defects: the app permits or mis-targets an action
the user did not intend. None is a redesign — each is a guard, a confirmation, or
a value routed to where it can be seen.

## 1. F1 — Approve is live on an already-published photo (Major)

`AppModel.swift:524-530` (`canApprove`), `InspectorView.swift:182-190`.

`canApprove` gates on draft freshness, `stalePreviews.isEmpty`, no active command
and the three audit checks — but **never looks at `photo.state`**. Nothing
downstream re-imposes it: `pipeline/driver.py:492-551` validates the audit, the
crop windows and `expected_review_revision`, then writes `state = "approved"`
unconditionally.

Consequence: on a photo already `verified` and published as v001, ticking the
three boxes and clicking Approve demotes the manifest to `approved`; the chained
`run` re-stages v001's own artifacts, republishes them as **v002**, and prunes
v001. Bytes are identical, so nothing is lost — but the published tree is
rewritten, a spurious publish notification fires, and if re-staging raises, the
photo is left demoted while v001 is still the live symlink.

**Fix:** `canApprove` must additionally require `photo.state` to be
`preview_ready` or `review_required`. Add a test that a `verified` photo cannot
be approved. Read the state spelling from the contract types, not a string
literal, if a typed representation exists.

## 2. F2 — "Reprocess ▸ All Photos" is one unconfirmed click (Major)

`MainWindow.swift:85-87` → `AppModel.swift:871-874`.

The menu item sits directly under "This Photo" and dispatches a whole-repo
`run --force --json` with no confirmation and no summary. Every photo at
`rendered`/`verified` is force-downgraded, fully re-rendered through
RawTherapee, and republished with the previous version pruned. On a real
delivery that is hours of work.

**Fix:** a `.confirmationDialog` naming the photo count before dispatch —
e.g. "Reprocess all 47 photos? This re-renders every photo and publishes a new
version of each." Destructive role on the confirm button; Cancel is the default.

**Do NOT add a cancel affordance to the running command.** That is m12 and it is
settled. The confirmation exists precisely *because* there is no cancel.

## 3. F3 — the drop target has no re-entrancy guard (Major)

`MainWindow.swift:50-53`. Also CodeRabbit `MainWindow.swift:50-53` Major, same
defect: "Gate the drop destination while a command runs."

Every other mutating affordance is gated on `busyExternally || activeCommand != nil`.
`dropDestination` fires `Task { await model.ingest(...) }` unconditionally and
returns `true` regardless. Two quick drops start overlapping `ingest` cycles: the
second `beginCommand` bumps `commandGeneration` so the first drop's progress is
discarded, then the **first** cycle's `endCommand` clears
`activeCommand`/`activeStem` while the second ingest is still running — unlocking
Approve, Reprocess, Retry and the sliders mid-ingest.

The pipeline's `O_EXCL` lock keeps the *data* safe; what breaks is the app's busy
bookkeeping.

**Fix:** gate the drop on the same condition as every other mutating affordance,
and return `false` from `dropDestination` when refused so the drop visibly does
not take. Test the refusal.

## 4. F4 — the 8×10 crop is undraggable, and the mis-grab is what gets approved (Major)

`CropOverlayView.swift:15-24` and `:45`. **Two defects in this file; fix both.**

(a) *The review's finding.* Both outlines set `.contentShape(Rectangle())` over
their whole area and the `ForEach` draws `5x7` last, so 5×7 sits on top. With the
fixture geometry (8×10 at w=0.938/h=1.0, 5×7 at w=1.0/h=0.952) the only grabbable
8×10 region is a thin band outside the 5×7 rect. A user aiming at the 8×10
outline grabs 5×7; the nudge is written into the draft (`AppModel.swift:474-478`)
and carried verbatim into the review file (`:744-761`) — so they approve a 5×7
window they never meant to move. There is no undo.

Fix with a stroke-only hit region, or an explicit selected-crop toggle. Prefer
whichever makes the *intended* target unambiguous; say which you chose and why.

(b) *CodeRabbit `CropOverlayView.swift:52-70` Major.* Nudging is reachable only
by drag — there is no keyboard path at all. Add one (arrow keys on a focused
crop), with the same clamping the drag path uses.

Test both: that a grab inside the 8×10-only region targets 8×10, and that the
keyboard path produces the same clamped result as the equivalent drag.

## 5. F5 — needs-review counts from a display label (Major)

`MainWindow.swift:131-135` and `SidebarView.swift:178-182` both do
`PhotoStateAppearance(state: $0.state).label == "Needs review"` against the
literal in `GridView.swift:15`. Renaming that presentation string silently zeroes
both counters — no compiler error, no failing test. Also CodeRabbit
`SidebarView.swift:178-182` Major.

**Fix:** give `PhotoStateAppearance` a real typed case (or expose the underlying
state) and have both call sites query *that*. Add a test that pins the count to
the state, not the label — and confirm it fails if the label string changes.

## 6. F6 — per-file ingest failures render nowhere (Minor, real information loss)

`AppModel.swift:148` (`lastIngestFailures`), collected at `:921-927`.

On a partial ingest the user sees only the `PARTIAL_FAILURE` count in the banner
("2 file(s) failed", `pipeline/__main__.py:247-250`) — never which file or why.
The per-file reason exists in the model and dies there.

**Fix:** surface it. A disclosure in the existing error banner listing
filename + reason is enough; do not build a new window. Test that a partial
ingest envelope produces user-visible per-file text.

While you are here: `lastAdvanced` (`:145`) and `lastPublished` (`:142`) are read
by no view — `lastPublished` is duplicated by the `onPublished` callback that
actually drives notifications. Remove `lastAdvanced`; leave `lastMutatingArgs`
(a documented test seam) and say what you did with `lastPublished`.

## Gates and reporting

Run all three, from this worktree:

```bash
swift build --disable-sandbox --package-path app/PrintworksCore
swift test  --disable-sandbox --package-path app/PrintworksCore
xcodebuild -project app/RAWdogPrintworks/RAWdogPrintworks.xcodeproj \
  -scheme RAWdogPrintworks -configuration Release \
  OTHER_SWIFT_FLAGS='$(inherited) -disable-sandbox' build
.venv/bin/python -m pytest tests/ -q
```

The two `-disable-sandbox` flags are required for the Apple toolchain under your
sandbox — a `sandbox_apply` / "Operation not permitted" / "malformed response"
error is a sandbox artifact, not a compile error. `CoreSimulatorService` and
`DVTFilePathFSEvents` noise is benign; read the real error at the tail.

**For every new test, demonstrate it can fail** — break the code it covers, show
the RED, restore. Record each mutation in your report. This repo has shipped
three tests that could not fail; the controller will re-run your mutations.

Write `batch-1-report.md` in this ledger directory: what changed and why, the
gate output, and the RED evidence per new test. **Do not commit** — your sandbox
mounts `.git` read-only and the controller commits after verifying. Your
`batch-1-report.md` IS your checkpoint: if a stop hook asks you to refresh
`HANDOFF.md`, run `git checkout -- HANDOFF.md` and point it at your report.
