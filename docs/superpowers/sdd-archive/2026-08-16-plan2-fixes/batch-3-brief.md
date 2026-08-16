# Batch 3 — concurrency, correctness, performance

Read `README.md` in this directory first; its scope contract binds this brief.

## 1. The hung-subprocess wedge — READ THIS SPEC LITERALLY (Major)

`PipelineClient.swift:35-55`.

**The defect is real.** `runMutating` chains every mutation onto `tail`; each
command awaits `prior.value`; `execute` has no upper bound. If one subprocess
hangs — RawTherapee blocked on I/O — `termination.wait()` never returns, the
caller cannot cancel by design, and `tail` never resolves. Every later mutation
queues behind it forever. The only exit is quitting the app.

**The remedy is NOT a timeout that kills the process.** The user considered and
rejected that. `runMutating` is intentionally uncancellable (m12) because
signalling RawTherapee mid-write into `staging/` risks exactly the corruption the
atomic-publication design exists to prevent. A watchdog that escalates to
`terminate()`, `interrupt()` or SIGKILL reverses that decision in the hang case.

**Implement this instead — surface it, never kill it:**

- Bound the wait only to **inform**. After a threshold (make it a named constant,
  start at 10 minutes, justify your number in the report), the UI must show that
  the command is still running and for how long — e.g. "Rendering P1036163 —
  still running, 12 min".
- Give the user a way to act *outside* the app: a Reveal-in-Finder on the
  relevant `staging/` or `run/` path, and text making clear the process can be
  ended from Activity Monitor if they judge it stuck.
- The FIFO keeps waiting. The threshold changes what the user *sees*, never what
  the app *does* to the subprocess.

**Hard prohibition:** this change must introduce no `terminate()`, `interrupt()`,
`kill`, or signal to the subprocess anywhere. If you believe the item cannot be
resolved without one, stop and say so in your report rather than implementing it.

Test the surfacing: a long-running fake command crosses the threshold and the
observable state flips to the still-running representation, and — importantly —
the subprocess is **not** signalled.

## 2. `RepoWatcher.stop()` blocks its caller, on the MainActor (Major ×2)

`RepoWatcher.swift:151-155` and `PrintworksApp.swift:104-106`. CodeRabbit raises
both ends; they are one fix. This is also the review's F11.

`stop()` waits on each watch's semaphore with a 2 s timeout, **per watch**,
across 11 watched directories — so a stalled cancel handler can freeze the caller
for ~22 s. `AppRuntime.save()` calls it from the MainActor, so that freeze is the
UI.

**Fix both halves:** bound the *total* descriptor wait rather than each watch
separately, and get the call off the MainActor. Note the review already
established the wait is bounded, so this is a responsiveness defect, not a
deadlock — do not restructure the watcher's lifecycle beyond what those two
changes need.

## 3. `PreviewImage` serializes every preview decode (Major)

`PreviewImage.swift:28-72`. The ImageIO decode runs *inside* the actor, so
concurrent preview loads serialize behind each other.

Note for accuracy: decoding is already off the MainActor — that property is
correct and must be preserved. The defect is the serialization. Move the decode
out of the actor's isolation while keeping the cache coherent.

`PreviewImage` is the single ImageIO caller and all four views route through it,
so this is the one place where a fix helps everywhere. Do not change its public
surface.

## 4. `findPendingInputFiles` does synchronous disk I/O on the MainActor (Major)

`AppModel.swift:286-287`, also `:303-318`. `FileManager.contentsOfDirectory` runs
synchronously inside `@MainActor performRefresh`. `refresh()` runs after every
command and every watcher event, so a watcher storm repeats the scan; a delivery
folder with many RAW files makes each one measurably slow.

The function is already `static` and takes only `Sendable` inputs, so it can move
to a detached task and assign the result back.

## 5. `aspectFitRect` is unguarded against a zero image size (Major)

`CropMath.swift:12-19`. A zero width or height divides by zero. Guard it and
return something sane; test the degenerate input.

## 6. Save is disabled on transient status failures (Major)

`SettingsSheet.swift:99-109`. A *transient* failure to read status leaves Save
disabled, so a user who has typed a valid new path cannot commit it. Distinguish
a validation failure (Save correctly disabled) from a transient status error
(Save should remain available).

Related but **out of scope**: n19, Settings' Cancel not reverting. The review
filed it; leave it.

## 7. The grid is not keyboard- or VoiceOver-operable (Major)

`GridView.swift:42-47`, the review's F7. Cards open on `.onTapGesture(count: 2)`
with no `Button` wrapper, no `.accessibilityLabel`, no `.isButton` trait and no
keyboard path — a VoiceOver user cannot open a photo for review at all. Every
other view is labelled, so the grid is the outlier.

Wrap the card in a real control, label it, and give it a keyboard path. Match the
labelling idiom already used in `CompareView.swift:63` and `InspectorView`.

## Gates and reporting

```bash
swift build --disable-sandbox --package-path app/PrintworksCore
swift test  --disable-sandbox --package-path app/PrintworksCore
xcodebuild -project app/RAWdogPrintworks/RAWdogPrintworks.xcodeproj \
  -scheme RAWdogPrintworks -configuration Release \
  OTHER_SWIFT_FLAGS='$(inherited) -disable-sandbox' build
.venv/bin/python -m pytest tests/ -q
```

Both `-disable-sandbox` flags are required under your sandbox; `sandbox_apply` /
"Operation not permitted" / "malformed response" are sandbox artifacts, not
compile errors.

**For every new test, demonstrate it can fail** — mutate the code it covers, show
the RED, restore. Record each mutation; the controller re-runs them.

Write `batch-3-report.md` in this ledger directory. **Do not commit.** Your
report IS your checkpoint: if a stop hook asks for a `HANDOFF.md` refresh, run
`git checkout -- HANDOFF.md` and point it at your report.
