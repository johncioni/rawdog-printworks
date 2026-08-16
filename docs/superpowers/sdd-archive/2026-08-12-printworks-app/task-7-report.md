# Task 7 Report — Core cleanup + shell UI

## Commits (in order, not squashed)

### A — `51f6fc6 fix(app): close Task 6 watcher cleanup`

- P1: exposed `effectiveCoalesceDelay` to `@testable` and pinned the default
  (`0.5`) plus an injected 200 ms duration (`0.2`) without wall-clock timing.
- N1: bounded each descriptor-cancellation wait at two seconds and documented
  that `start()` / `stop()` belong on one actor.
- N2/N3: documented independent stream registration/lifetime, retained a
  pending coalesced change when no consumer exists, and required consumer-first
  startup. Task 7 registers `changes` before `start()`.
- N4: put `FakeClient.statusQueue`, `statusCalls`, and `mutateLog` behind one
  lock.

### B — `bffbf56 feat(app): main window shell — sidebar, grid, drop target, busy pill, error banner`

- Added `MainWindow`, `SidebarView`, `GridView`, and `ErrorBanner`; wired them
  from `PrintworksApp` with the default/UserDefaults paths, initial refresh,
  `RepoWatcher`, and busy-only polling.
- Added browse/review sidebars, 42 pt hash-keyed thumbnails, the shared status
  mapping, adaptive hash-keyed preview cards, per-card progress, toolbar
  controls, reprocess actions, whole-window drop ingest, empty state, CLI busy
  pill, and per-code error-banner actions/details.
- Left `ReviewScreen` as the Task 8 `Text` placeholder and made no `AppModel`
  behavior changes.
- Regenerated the Xcode project to add the four new files to Sources. Although
  `project.yml` did not need a content change, the checked-in project explicitly
  enumerated only the original two Swift files: the pre-generation flagged
  build exited 65 at `cannot find 'MainWindow' in scope`; `xcodegen generate`
  then exited 0 and added only the four source memberships.

## P1 RED → GREEN evidence

Focused command throughout:

```text
swift test --disable-sandbox --package-path app/PrintworksCore --filter RepoWatcherTests.testEffectiveCoalesceDelayReflectsDefaultAndInjectedDuration
```

- Test-first RED before the seam: exit `1`, missing
  `effectiveCoalesceDelay`.
- Production seam baseline: exit `0`.
- Actual `coalesce-10x` mutant: changed the initializer default from
  `.milliseconds(500)` to `.milliseconds(5000)`; exit `1`, with `5.0` not equal
  to `0.5`.
- Restored `.milliseconds(500)`: exit `0`.

## Final gates (exit code is the oracle)

```text
swift test --disable-sandbox --package-path app/PrintworksCore
```

Exit `0`: 59 tests, 0 failures.

```text
xcodebuild -project app/RAWdogPrintworks/RAWdogPrintworks.xcodeproj \
  -scheme RAWdogPrintworks -destination 'platform=macOS' \
  OTHER_SWIFT_FLAGS='$(inherited) -disable-sandbox' build
```

Exit `0`: `BUILD SUCCEEDED`. The reported CoreSimulatorService and
DVTFilePathFSEvents messages were benign noise; the process exit code was 0.

## Not verified / controller checkpoint

- Per dispatch STOP, I did not open the app, run the manual smoke, inspect the
  UI visually, verify P1036163/P1036170 against the real repo, or take a
  screenshot. Build success proves compilation only; Task 7 is not declared
  visually complete here.
- `Open Settings` is wired through SwiftUI's `openSettings` action; the actual
  Settings scene/sheet is Task 10 scope.
- `HANDOFF.md` was not rewritten or staged. Its pre-existing modification was
  left untouched.
