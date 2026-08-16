# Task 11 fix round 1 report

## What changed

- **M1:** Gave P1 both required persisted crop windows in every canned status.
  The smoke test now requires exactly `8x10` and `5x7`, checks each window's
  expected `x`/`y`/`w`/`h`, and requires the serialized windows to omit
  `source`.
- **M2:** Snapshotted every fixture-repo directory and file byte before the
  flow. Afterward, the test allows exactly the stub's four new artifacts and
  requires the rest of the tree and all original file bytes to be unchanged.
- **L1:** Progress merging now retains the last determinate event when a later
  stage event has no index/total, so verify/publish boundaries do not reset the
  bar to zero. Added a focused regression test.
- **L2:** Removed `codesign --deep` and added standalone
  `codesign --verify --strict "$APP"`; under `set -e`, verification failure
  terminates the script.

## M1 mutation RED then restored GREEN

Every Swift command included `--disable-sandbox`; exit code was the oracle.

1. Strengthened smoke test before mutation:
   `swift test --disable-sandbox --package-path app/PrintworksCore --filter
   SmokeTests.testFullReviewFlowAgainstStubPipeline` exited 0; 1 test passed.
2. Temporarily deleted the `crops` key from `writeReviewFile` and reran the same
   command. It exited 1 at `SmokeTests.swift:68`: `XCTUnwrap failed` because the
   review-file crops dictionary was absent.
3. Restored the production `crops` serialization and reran the same command.
   It exited 0; 1 test passed.

## Verification

- Focused L1 regression:
  `swift test --disable-sandbox --package-path app/PrintworksCore --filter
  AppModelTests.testProgressStageKeepsLastDeterminateFraction`
  - Exit 0; 1 test passed.
- `swift test --disable-sandbox --package-path app/PrintworksCore`
  - Exit 0; 85 tests, 0 failures.
- `xcodebuild -project app/RAWdogPrintworks/RAWdogPrintworks.xcodeproj -scheme
  RAWdogPrintworks -destination 'platform=macOS'
  OTHER_SWIFT_FLAGS='$(inherited) -disable-sandbox' build`
  - Exit 0; `BUILD SUCCEEDED`.
- Exact bare `zsh scripts/build-app.sh`
  - Exit 65 in this managed agent environment, on the known macro-host
    `sandbox-exec: sandbox_apply: Operation not permitted` failure before the
    script reached signing. A second bare run had the same exit. No script flag
    or `OTHER_SWIFT_FLAGS` behavior was changed.
  - Supplemental managed-environment run with inherited `-disable-sandbox`
    exited 0, reached the new sign-and-verify lines, and built the Release app.
  - A final direct `codesign --verify --strict` on that Release app exited 0.
- `git diff --check` exited 0.

## Boundaries and handoff

- Did not open the app, run against the real photo repo, or commit.
- `HANDOFF.md` was read and left byte-for-byte untouched.
- Intended commit message:
  `fix(app): close Task 11 follow-up findings`
