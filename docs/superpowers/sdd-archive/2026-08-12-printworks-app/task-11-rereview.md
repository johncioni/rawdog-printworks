# Task 11 re-review — `de1e774..HEAD`

Reviewer: Opus 5 (xhigh). Scope: `28dd02d` (Task 10 fix round), `b311322`
(Task 11 steps 1–2), `adae41c` (HANDOFF revert — no code).
Read: `task-11-brief.md`, `task-11-dispatch.md`, `task-11-report.md`,
`task-11-visual-qa-note.md`.

## Verdict

**Task 11 is complete, and with it Plan 2's task list.** The smoke test does pin
real wiring, the build script is sound, both un-captured QA states are genuinely
implemented, and the Release-vs-Debug input anomaly is not an app defect. Two
MEDIUM findings are test-hardening gaps in `SmokeTests` itself — they weaken the
net for future refactors but do not describe a broken app, and both carry forward
to the whole-branch review rather than blocking this task.

Accepting the QA pass having been driven against **Debug** is justified, and not
merely pragmatically: the app target has no `#if DEBUG` code, one shared
`Info.plist`, and no entitlements in either configuration, so for every behaviour
the QA exercised, the Debug binary is the Release binary. See Q4.

## What I verified myself vs. what I took on attestation

- **Attested by the controller, not re-run by me:** `swift test` (84 tests),
  `xcodebuild`, `zsh scripts/build-app.sh` exit 0, the independent smoke-test
  mutation, and the 11-screenshot visual pass. I reviewed by reading.
- **Verified by me:** every file:line claim below; `set -e` propagation in the
  build script (empirically); the Release bundle's signature and entitlements;
  the LaunchServices registration state; the pipeline's review-file contract.

---

## Q3 — Render progress bar and "rendering preview…" shimmer: **both implemented**

Confirmed by reading the full chain, not by pattern-matching a symbol.

### Render progress bar — reachable, end to end

| Link | Location |
|---|---|
| Pipeline emits stem-carrying NDJSON | `pipeline/driver.py:256` (`stage`), `:265-271` (`_RenderProgress.landed` → `index`/`total`), `:754-761` (preview loop) |
| Golden fixture pins the shape | `tests/fixtures/json_contract/run_stream.ndjson:1-11` |
| Client parses lines *live*, not at exit | `PipelineClient.swift:150-156` |
| Model fans events into state | `AppModel.swift:1003-1014` (`progressHandler`), keyed `event.stem ?? activeStem` |
| Cleared on every command exit | `AppModel.swift:986-992` |
| Toolbar spinner | `MainWindow.swift:69-75` |
| Per-photo determinate bar | `GridView.swift:95-103`, fraction at `:129-134` |

`streamProgress: true` is passed on all six long-running paths
(`AppModel.swift:715, 781, 800, 829, 843, 894`) — `run`, `run --stem`,
`run --force`, and both ingest chains. Real `run` output carries `"stem"` on
every event, so the `event.stem ?? defaultStem` key resolves even for the
repo-wide `run` where `activeStem` is nil. The bar is real and will render.

**Why the controller couldn't capture it:** the post-approve `run --stem` had
all four previews already fresh, so the render stage emitted its progress faster
than the polling window. That is an observation gap, not a defect. To force it:
`scripts/process.sh run --stem <s> --force`, which re-renders all 22 artifacts
and emits `_RenderProgress` ticks for each.

### Shimmer — reachable, end to end

- Overlay implementation: `ReviewView.swift:272-307` — a `TimelineView`-driven
  1.4 s gradient sweep with the `Label("Rendering preview…", …)` badge,
  `allowsHitTesting(false)`, `accessibilityLabel("Rendering preview")`.
- Gate: `ReviewView.swift:101-105` — shown when
  `activeCommand ∈ {"preview","adjust"}` **and** `activeStem == photo.stem`.
- Both gate values are set by `beginCommand` at `AppModel.swift:611`
  (`applyAdjust`, the slider path), `:648` (`resetAdjust`), and `:668`
  (`rerenderPreview`, the stale-chip path), and cleared at `:987-988`.

So the shimmer covers *every* slider adjust as well as the stale-preview
re-render — it is strictly easier to hit than the QA note assumed. The reason it
wasn't seen is that against the scratch repo an `adjust` returns in well under a
second, so the overlay's lifetime was shorter than the capture cadence. To force
it: touch a sidecar to stale one style, then click the stale chip (the `preview`
render is seconds, not milliseconds).

**Answer: yes, both are implemented and reachable. Neither is a stub.**

---

## Q4 — Release-vs-Debug input anomaly: **not an app concern**

I'll separate what is airtight from what is probable, because they carry
different weight.

### Airtight: it cannot be the app's window/scene configuration

- There is **no windowing or activation code in the app at all** — zero hits for
  `NSApp`, `activate`, `activationPolicy`, `NSWindow`, `orderFront`, `makeKey`,
  `NSApplicationDelegate` across `app/RAWdogPrintworks/Sources/`. The scene is a
  plain `WindowGroup` (`PrintworksApp.swift:11-24`).
- `Info.plist` has **no `LSUIElement`, no `LSBackgroundOnly`** — regular
  activation policy, and it is one file shared by both configurations.
- The Release bundle has **no entitlements at all** and `flags=0x2(adhoc)` — no
  hardened runtime, no sandbox, no library validation. Nothing to differ.
- The **only** `#if DEBUG` in the entire codebase is
  `RepoWatcher.swift:107-117`, two test-only accessors. No configuration-
  dependent behaviour exists anywhere near windowing.

There is no configuration axis on which Debug and Release *can* differ here.
Whatever caused it is outside the app.

### Also airtight: it is not the signing artifact the QA note guessed

`window_not_focused` is the automation provider's **focus precondition**, mapped
at `/Applications/Orca.app/…/out/main/computer-sidecar.js:781` from the native
provider's refusal text. It is raised *before* any event is synthesized — the
app never receives anything to accept or reject. And code-signing identity
governs the **poster's** TCC grant (which is fine — AX reads work), not the
target's focusability. A target's ad-hoc signature cannot make it unclickable.

### Probable, verified-present, but not reproduced end to end: bundle-ID collision

Two LaunchServices registrations exist for the **same** bundle identifier
`com.john.rawdog-printworks`:

```
…/DerivedData/RAWdogPrintworks-bbbsnsxyyiyarsfvggpflrfwxcsc/Build/Products/Debug/RAWdogPrintworks.app
…/plan2-printworks-app/app/build/Build/Products/Release/RAWdogPrintworks.app
```

and **a Debug instance is running right now** — pid 89376, from the DerivedData
path. That is sufficient to produce exactly this symptom: activation by name or
bundle ID (System Events `activate`, `open -a`) resolves through LaunchServices,
which with two same-ID registrations can route to the Debug copy — or, if
Release was launched while Debug was already running, LaunchServices would
simply have activated the running Debug instance and never brought Release
forward at all. Screenshots and AX reads target a *window* directly and are
unaffected, which is precisely the asymmetry observed.

`project.yml:23` sets `PRODUCT_BUNDLE_IDENTIFIER` in `settings.base`, so both
configurations share the identifier by design. That is normal and not worth
changing.

### Discriminator, if you want it closed rather than set aside

```bash
kill 89376                                   # or quit the Debug app
/System/Library/Frameworks/CoreServices.framework/Frameworks/LaunchServices.framework/\
Support/lsregister -u ~/Library/Developer/Xcode/DerivedData/RAWdogPrintworks-*/Build/Products/Debug/RAWdogPrintworks.app
open app/build/Build/Products/Release/RAWdogPrintworks.app
osascript -e 'tell application "System Events" to get bundle identifier of first application process whose frontmost is true'
pgrep -fl RAWdogPrintworks                   # expect exactly one, the Release path
```

If the frontmost check returns `com.john.rawdog-printworks` and clicks then land,
it was the collision. **You can stop worrying about it either way — it is not a
finding against the app.**

---

## Findings

### M1 — MEDIUM · the smoke test's review-file `crops` is neither asserted nor contract-valid

`SmokeTests.swift:57-66` reads back the review file the stub received and checks
`expected_review_revision` and `expression_audit` — but never `crops`. Separately,
the canned status at `SmokeTests.swift:7` gives P1 exactly one crop, `"8x10"`.

The real pipeline requires **both** crops. `pipeline/paths.py:5` defines
`CROPS = ("8x10", "5x7")`, and `pipeline/driver.py:498-502` rejects anything
short:

```python
windows = _review_windows(review.get("crops") or {})
missing = [c for c in paths.CROPS if c not in windows]
if missing:
    raise jsonio.CommandError("BAD_INPUT", f"crops missing windows: {missing}")
```

`AppModel.approveCropWindows` (`AppModel.swift:732-740`) short-circuits the
`crops --stem` fetch when the photo already has persisted windows — so with a
one-crop fixture it emits a one-crop review file. The golden fixture
`tests/fixtures/json_contract/crops_suggested.json` carries both keys; the smoke
fixture does not.

**Failure scenario A (fidelity):** the approve this test "proves" would fail
against the real pipeline with `BAD_INPUT: crops missing windows: ['5x7']`. The
stub blindly `cp`s the file and returns canned success (`SmokeTests.swift:121-130`),
so the app-side twin of the golden fixtures currently models an approve that
cannot happen.

**Failure scenario B (coverage):** delete the `"crops"` key from
`writeReviewFile` (`AppModel.swift:746-753`), or let `approveCropWindows` return
`[:]`. Every assertion still passes; the app ships and every real approve dies on
`BAD_INPUT`.

*Fix:* give P1 both `8x10` and `5x7` in the canned status, and assert the
review-file `crops` dictionary has both keys with the expected geometry and **no**
`source` field (`AppModel.swift:749-752` deliberately strips it).

### M2 — MEDIUM · the smoke test does not pin Plan 2's "no repo writes from Swift" constraint

`SmokeTests.swift:18-72` drives the whole flow against a real temp repo and never
checks what landed in it. That constraint is the one the controller verified by
hand (`git status` showing only `recipes/` and `sidecars/`) and the one a
refactor is most likely to break silently.

**Failure scenario:** change `reviewFileDirectory` (`AppModel.swift:754`) to
resolve under the repo instead of the system temp directory — a plausible
"keep the review file next to the recipe" refactor. The smoke test stays green;
the app starts writing into a git-tracked working tree, violating a Global
Constraint, and only a human running `git status` would notice.

*Fix:* snapshot the repo tree before the flow and assert afterwards that the only
new entries are the stub's own (`stub-calls.log`, `stub-review.json`,
`adjust-seen`, `run-seen`) — the stub writes into `$PWD`, which
`PipelineClient.swift:83` sets to the repo, so the assertion needs that allowlist
rather than a bare "nothing changed".

### L1 — LOW · the render progress bar snaps back to 0 % on stage boundaries

`AppModel.swift:1010` overwrites `renderProgress[key]` with whichever event
arrived last, and `GridView.swift:129-134` returns `0` for any event without
`index`/`total`. `stage` events (`pipeline/driver.py:256`) carry neither.

**Failure scenario:** a real `run --stem` emits `stage:render`, then render
progress `1/29 … 29/29`, then `stage:verify`, then `stage:publish`. The bar
fills to 100 %, then **empties to 0 %** for the verify and publish stages and
stays there until the command ends — reading as "restarted" or "stalled" during
the two stages where the user is most likely watching.

*Fix:* keep the last fractional value when an index-less event arrives, or render
indeterminate for `stage` events instead of `value: 0`. Cosmetic, but it is the
one progress affordance the app has.

### L2 — LOW · `scripts/build-app.sh`: `--deep` is pointless now and wrong later, and nothing verifies the signature

`scripts/build-app.sh:9` — `codesign --force --deep --sign - "$APP"`.

- `--force` is **correct and required**: `project.yml` sets
  `CODE_SIGN_IDENTITY: "-"`, so Xcode already ad-hoc signed the bundle and a
  re-sign without `--force` would fail.
- `--deep` is a **verified no-op**: the bundle contains no nested code at all —
  `Contents/` holds only `MacOS/`, `Info.plist`, `PkgInfo`, `_CodeSignature/`.
  PrintworksCore links statically. Apple deprecates `--deep` for signing, and if
  this app ever embeds a framework or XPC service, `--deep` signs it in the wrong
  order and with the wrong entitlements. Drop it.
- The script prints "Built + ad-hoc signed" without verifying. Adding
  `codesign --verify --strict "$APP"` makes the claim earned rather than
  asserted — the implementer ran it by hand, but the script doesn't.

**Correctness of `set -euo pipefail` — checked empirically, it is fine.** I
confirmed in a scratch zsh script that a failing `(cd … && …)` subshell aborts
before the following line, so a `xcodegen`/`xcodebuild`/`codesign` failure does
fail the script. `-u` and `-o pipefail` are both valid zsh; there are no pipes,
so `pipefail` is inert but harmless. `cd "$(dirname "$0")/.."` resolves
correctly under `zsh scripts/build-app.sh` from the repo root. `app/build` is
gitignored (`.gitignore:14`), so the script cannot dirty the tree.

### I1 — INFO · the ingest→run chain narrowing is a deliberate behaviour change

`AppModel.swift:792-804, 838-847` now chain `run` only when
`!result.ingested.isEmpty`. A user who re-drops files that all dedupe now gets an
`INGEST_NOTICE` banner and no render pass — where previously `run` would have
advanced any photo already sitting at `ingested`. The comment at `:792-794`
justifies it (don't take the lock to re-report the same failure), and
**Reprocess → All Photos** (`MainWindow.swift:85-87`) covers the gap. Recording
it as an intentional narrowing, not a defect.

### I2 — INFO · the recorded build-script green depended on an env var not in the script

`task-11-report.md:45-54`: the bare `zsh scripts/build-app.sh` exited 65 in the
implementer's managed environment until `OTHER_SWIFT_FLAGS='$(inherited)
-disable-sandbox'` was exported. That is the known Seatbelt/SwiftPM-macro quirk
of the agent environment, not a script defect — the controller's own run on a
normal shell exited 0 unaided. Worth knowing before someone "fixes" the script.

### I3 — INFO · defensive dead branch in the churn test

`AppModelTests.swift:722-725` — `guard callCount >= expectedCalls else { break }`
after `fulfillment(of:timeout:)`. A timeout already records an XCTest failure, and
the terminal `XCTAssertEqual(observedCalls, 32)` (`:733`) would catch an early
exit, so the `break` cannot mask a regression. Noted only so nobody reads it as a
silent-skip. The new `defer { shouldFinish = true }` (`:695`) is a genuine
improvement — it releases the spinning fake handlers on every exit path.

---

## Focus 5 — did Task 10's fix round or Task 11 break Tasks 1–9?

Checked each changed behaviour against what it replaced. **No regressions found.**

- **`pathExtension.lowercased() == "rw2"`** (`AppModel.swift:310`) — this is an
  *alignment fix*, not a widening bug. `pipeline/ingest.py:147` and `:155` both
  use `suffix.lower() == ".rw2"`, so the previous `rw2 || RW2` check under-
  reported exactly the files the pipeline would have accepted. The test fixture
  change to `P3.Rw2` (`AppModelTests.swift:1271, 1281`) pins the new behaviour
  against the pipeline's actual rule.
- **`cropRetryToken`** (`Contract.swift:157-166`) is coherent with the model's
  revision-keyed cache. The `"render dims not recorded"` path caches `nil` at a
  revision (`AppModel.swift:381-385`); rendering a preview changes both the token
  (`preview:false → preview:true`) and the revision, so the view refires
  (`InspectorView.swift:45-59`, `ReviewView.swift:37-50`) *and* the model cache
  misses. Deliberate insensitivity to ordinary revision churn is preserved. The
  in-flight token guard is self-healing: a token change that discards a result
  also changes the task id, so the task re-fires rather than leaving `cropResult`
  stranded. `ContractTests.swift:38-58` pins exactly this — equal across
  revision-only change, unequal across state change and across first preview.
- **Cancellation policy** (`PipelineClient.swift:36-44`) — the new comment and
  the two tests match the shipped behaviour: reads terminate on cancellation
  (`PipelineClientTests.swift:135`), mutations run to completion
  (`:161-191`), and the mutation test asserts both "not terminated" *and*
  "envelope ok", so it cannot pass by the subprocess merely dying quietly. The
  rationale (never SIGTERM RawTherapee mid-write into `staging/<stem>.tmp/`) is
  correct and matches the pipeline's atomic-publication design.
- **`INGEST_NOTICE`** maps to no banner button (`AppModel.swift:965-972` default
  case), which is right — skips and conflicts are CLI-resolvable, not retryable.
  `AppModelTests.swift:1310-1328` pins it.
- Task 11 added only a test file and a script; it changed no production code.

## What I did *not* review

Per the dispatch: the deferred pile (m6–m10, i11, N3/N5, n13–n21, kqueue vs
in-place edits, `Output/photos/<stem>/`, the Task 5 refresh gate) belongs to the
whole-branch review. M1, M2 and L1 above should join that list.

## Disclosures

- I re-signed `app/build/Build/Products/Release/RAWdogPrintworks.app` in place
  while testing `codesign --force --deep --sign -` behaviour. The operation is
  idempotent and the bundle is gitignored, but it did reset the ad-hoc cdhash —
  if anything was granted to the previous hash, re-grant it.
- pid 89376 (the Debug app instance) is still running as of this review; I did
  not kill it.
