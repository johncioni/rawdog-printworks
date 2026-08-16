# Task 11 Steps 1–2 report

## Scope

- Implemented Steps 1 and 2 only.
- Did not open the app, run the pipeline, point at the real photo repo, or
  perform the controller-owned visual QA gate.
- Task 11 is not complete until the controller performs and records Step 3.

## Implemented

- Added `app/PrintworksCore/Tests/PrintworksCoreTests/SmokeTests.swift`.
  It creates the exact `tests/conftest.py` directory set, two recipe fixtures,
  two tiny preview JPEGs, and a shell stub that dispatches on `$1` and logs
  argv. The real `PipelineClient` (with required `executableOverride`) and
  `AppModel` drive initial refresh, draft creation, slider flush, adjust rebase,
  checklist enablement, approve, targeted run, and final refresh.
- The smoke test asserts the full command ordering, exact adjust/run argv,
  approve review-file receipt, `expected_review_revision: r2`, audit strings,
  and the final published snapshot. The canned adjust and preview results both
  carry the matching `r1` → `r2` revision pair.
- Added executable `scripts/build-app.sh` exactly as specified: XcodeGen,
  Release build in `app/build`, and ad-hoc codesigning.

## Deliberate RED → GREEN

- RED: temporarily set `executableOverride: nil` and ran
  `swift test --disable-sandbox --package-path app/PrintworksCore --filter
  SmokeTests.testFullReviewFlowAgainstStubPipeline`.
  Exit 1. `PipelineClient` invoked the stub as `-m pipeline status --json`, so
  the `$1` dispatcher rejected it and the initial snapshot assertions failed.
  This proves the smoke test detects the exact argv wiring trap from the brief.
- Restored `executableOverride: stub`.
- GREEN: the same focused command exited 0; 1 test passed.

## Required gates

- `swift test --disable-sandbox --package-path app/PrintworksCore`
  - Exit 0; 84 tests, 0 failures.
- `xcodebuild -project app/RAWdogPrintworks/RAWdogPrintworks.xcodeproj -scheme
  RAWdogPrintworks -destination 'platform=macOS'
  OTHER_SWIFT_FLAGS='$(inherited) -disable-sandbox' build`
  - Exit 0; `BUILD SUCCEEDED`.
  - Managed-environment CoreSimulator/FSEvents diagnostics were non-fatal.
- First bare `zsh scripts/build-app.sh` attempt:
  - Exit 65 before app production/signing because the managed environment
    rejected Xcode's nested Swift macro sandbox with
    `sandbox-exec: sandbox_apply: Operation not permitted`.
- Required sandbox-disabled release gate:
  - Exported `OTHER_SWIFT_FLAGS='$(inherited) -disable-sandbox'`, then ran the
    unchanged exact command `zsh scripts/build-app.sh`.
  - Exit 0; `BUILD SUCCEEDED`; the script reported the ad-hoc signed app at
    `app/build/Build/Products/Release/RAWdogPrintworks.app`.
  - `codesign --verify --deep --strict` on that app exited 0.

## Controller handoff

- Step 3 remains: capture and eye-review the full §8 visual QA screenshot set.
- Work is intentionally uncommitted. Intended commit message:
  `feat(app): e2e smoke test, release build script, visual QA pass`
- `HANDOFF.md` was not rewritten.
