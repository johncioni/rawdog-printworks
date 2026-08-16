# CodeRabbit ↔ whole-branch review — reconciliation

PR #5, run `76c3045b`, profile ASSERTIVE. **32 findings: 16 Major, 10 Minor, 6
Trivial.** CodeRabbit could not post them inline ("Comments failed to post (32)",
a GitHub limit), so they live in the COMMENTED review body — there are **zero**
inline comments to reply to, which changes how they get resolved.

Both PR checks are green: `pytest` pass (1m4s, first CI run this branch ever
got), CodeRabbit `pass` after its CHANGES_REQUESTED review.

## Where the two reviews agree (highest confidence)

| review | CodeRabbit | note |
|---|---|---|
| **F3** drop-target re-entrancy | `MainWindow.swift:50-53` Major — "Gate the drop destination while a command runs" | same defect, same fix |
| **F5** counts from a display label | `SidebarView.swift:178-182` Major — "Do not derive the review count from a display label" | same defect |
| **F7** grid not keyboard/VoiceOver operable *(review filed)* | `GridView.swift:42-47` Major | CR ranks it higher than we did |
| **F10** UTF-8 split across pipe reads *(review called it a Nit)* | `PipelineClient.swift:296-305` Major | CR adds the root cause (`LineCollector`) **and** that no test covers a split multi-byte char |
| **F11** `RepoWatcher.stop()` on the MainActor *(filed)* | `PrintworksApp.swift:104-106` + `RepoWatcher.swift:151-155`, both Major | CR wants the total wait bounded, not per-watch |
| **m6** coalesce window survives a consumer-less gap *(filed)* | `RepoWatcher.swift:330-349` Minor | same |
| branch-scale duplication *(review: a smell)* | `InspectorView.swift:75-77` Minor | CR found an actual **bug** in it: `"bw".capitalized` → "Bw" vs `staleStylesText`'s "B&W" — the copies **disagree** |

## Review-only — CodeRabbit missed these

**F1, F2 and F6 have no CodeRabbit counterpart**, and F1/F2 are the two Majors.
Expected: all three are *semantic* gaps (a missing state check, a missing
confirmation, a value computed and never displayed) rather than local code
defects. Nothing here is retracted.

**F4** is half-matched: CR's `CropOverlayView.swift:52-70` Major says nudging is
drag-only and needs a keyboard path — a *different* defect in the same code from
the review's z-order finding (5×7 drawn last steals 8×10's hit region). Fix both
together; the file is opened once either way.

## CodeRabbit-only — genuinely new, worth acting on

- **`PipelineClient.swift:35-55` Major — a hung subprocess stalls the mutation
  FIFO permanently.** ⚠️ **Touches m12 — needs your call, see below.**
- **`DebouncerTests.swift:12-19` + `:31-43`, both Major** — `nonisolated(unsafe)
  var fired` is a real data race and the timing makes it flaky; and
  `testScheduledActionDoesNotRunInCancelledTask` **does not exercise
  cancellation**. Plus `LineCollectorTests:10-16` Major (asserts only
  `allLines`, never the return value), `RepoWatcherTests:33-39` (teardown
  assertion **cannot fail**), `:102-113`, `:293-297` (asserts on a closed fd
  number the kernel can reassign).
  → **This is the repo's known recurring failure mode.** Three tests that could
  not fail were already caught by hand across Tasks 6, 9 and 11. CodeRabbit just
  found five or six more of the same species in one pass. Highest-value cluster
  in the whole report.
- `CropMath.swift:12-19` Major — `aspectFitRect` unguarded against a zero size.
- `PreviewImage.swift:28-72` Major — the ImageIO decode runs *inside* the actor,
  serializing every preview load. (Not a contradiction of the review's "decoding
  stays off the MainActor" — off-MainActor and serialized are both true.)
- `AppModel.swift:286-287` Major — `findPendingInputFiles` does synchronous
  directory I/O on the MainActor, repeated on every refresh and watcher storm.
- `SettingsSheet.swift:99-109` Major — Save disabled on *transient* status
  failures. Adjacent to n20, which the review dropped as benign; this is a
  different, sharper case.
- `InspectorView.swift:50-56` Minor — cached `nil` crop results are not
  invalidated when readiness changes. Touches `cropRetryToken`; the review
  verified that token as additive to the contract, and this does not undo that.
- Minors/Trivials: `GridView:73-93` (use the failure code for the badge),
  `SidebarView:35-47` (stable row identity), `ReviewView:189-198` (bare
  shortcuts unscoped), plus 6 style/idiom trivials.

## Recommend dismissing

- **`scripts/build-app.sh:5-7` Major — "Pass the required Swift build setting"
  (`OTHER_SWIFT_FLAGS='$(inherited) -disable-sandbox'`).** False positive, and
  an instructive one: it is reading a *handoff note* as a build requirement.
  That flag is the **Codex seatbelt workaround** (memory `codex-swift-sandbox-fix`),
  needed only so an agent in a sandbox can build. Adding it to the shipping
  Release build would disable the Swift build sandbox in the signed artifact for
  no reason. `build-app.sh` already exits 0 producing a verified-signed bundle
  without it.

## Needs your decision

**`PipelineClient.swift:35-55` vs m12.** CodeRabbit's reasoning is careful and it
does *not* ask to reopen m12 — it draws a real distinction: *"The uncancellable
policy is defensible. The absence of any upper bound is separate from that
policy."* If RawTherapee hangs on I/O, `termination.wait()` never returns, the
user cannot cancel by design, and `tail` never resolves — so every later mutation
queues behind it forever, with quitting the app the only exit.

But its proposed remedy — watchdog → `terminate()` → SIGKILL — is **exactly what
m12 rejected**: SIGTERM to RawTherapee mid-write into `staging/`.

Three ways to go, none of which I should pick for you:

1. **Dismiss**, m12 covers it: a hang is a stuck render, and killing it risks the
   corruption m12 exists to prevent.
2. **Surface without killing**: bound the wait only to *inform* — after N
   minutes show "still running, N min" with a Reveal-in-Finder / manual-kill
   affordance. Keeps m12 intact, removes the silent-wedge property.
3. **Adopt CR's fix**, accepting a bounded corruption risk in exchange for a
   self-draining FIFO. This reverses m12 in the hang case.

My read: **(2)**. It answers CR's actual objection — the *silent* unbounded wedge
— without touching the write path m12 protects. But m12 is your standing
decision, so it is yours to move.
