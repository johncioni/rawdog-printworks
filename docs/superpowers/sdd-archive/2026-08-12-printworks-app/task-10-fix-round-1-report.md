# Task 10 fix round 1 report

## What changed

- **m12:** Kept `runMutating` intentionally uncancellable. Renamed the read-path
  cancellation test so it cannot imply mutation coverage, added a sibling test
  proving caller cancellation does not terminate a mutating subprocess, and
  documented the FIFO and mid-staging-write SIGTERM rationale plus the policy
  work required before cancellation can be propagated.
- **m13:** Added `PhotoStatus.cropRetryToken`, based on state and first-preview
  availability only while persisted crops are absent. Both crop-loading views
  now include that token in their task identity and reject results from an old
  readiness epoch. A render/state transition retries a cached negative, while a
  review-revision-only change does not restore the n16 refetch churn.
- **m14:** Replaced unbounded `AsyncGate` waits with named
  `XCTestExpectation`s and a 5-second timeout, added a `defer` release for held
  stubs, retained the observed-call assertion, and retained the peak assertion
  at exactly eight.
- **n17:** `ingestPending` now runs only when something landed and surfaces
  skip/conflict notices, matching the existing drag-ingest path.
- **n18:** Pending Input discovery now matches `.rw2` case-insensitively.
- n19-n21 were skipped: they require additional Settings or notification/error
  presentation behavior beyond this narrowly tested follow-up.

## RED then GREEN evidence

All Swift test commands used `--disable-sandbox`; exit code was the oracle.

1. **m13 readiness token**
   - RED: `swift test --disable-sandbox --package-path app/PrintworksCore
     --filter ContractTests.testCropRetryTokenTracksReadinessButNotReviewRevision`
     exited 1 because `PhotoStatus` had no `cropRetryToken`.
   - GREEN: the same command exited 0; 1 test passed.
2. **n17 skip-only ingest**
   - RED: `swift test --disable-sandbox --package-path app/PrintworksCore
     --filter AppModelTests.testIngestPendingSkipsRunWhenNothingLandsAndSurfacesNotices`
     exited 1 (signal 6): the fake trapped the unexpected `run` command.
   - GREEN: the same command exited 0; 1 test passed.
3. **n18 mixed-case RAW extension**
   - RED: `swift test --disable-sandbox --package-path app/PrintworksCore
     --filter AppModelTests.testPendingInputFilesListsRawFilesMissingFromSnapshot`
     exited 1; actual `[P2.rw2]` omitted expected `P3.Rw2`.
   - GREEN: the same command exited 0; 1 test passed.
4. **m12 characterization**
   - `swift test --disable-sandbox --package-path app/PrintworksCore --filter
     PipelineClientTests.testCancelling` exited 0; both the renamed read-path
     termination test and the mutating no-termination test passed.
5. **m14 fail-fast mutation probe**
   - Temporarily disabled `pending.task.cancel()` and ran only
     `testCropsStayAtEightAcrossRevisionChurn`: exit 1 after 5.124 seconds of
     test time, naming unfulfilled `crop wave 2 started` and asserting observed
     calls `8 != 32`. The held stubs drained; the run did not hang.
   - Restored the production line and reran the same test: exit 0 in 0.011
     seconds; observed peak remained eight.

## Required gates

- `swift test --disable-sandbox --package-path app/PrintworksCore`
  - Exit 0; 83 tests, 0 failures.
- `xcodebuild -project app/RAWdogPrintworks/RAWdogPrintworks.xcodeproj -scheme
  RAWdogPrintworks -destination 'platform=macOS'
  OTHER_SWIFT_FLAGS='$(inherited) -disable-sandbox' build`
  - Exit 0; `BUILD SUCCEEDED`.
  - CoreSimulator/FSEvents diagnostics were non-fatal host-environment noise.

## Boundaries and handoff

- Did not open the app, run a visual smoke, or touch the real photo repo.
- Did not stage or commit. `HANDOFF.md` was read but never written or rewritten
  by this session.
- Intended commit message:
  `fix(app): close Task 10 follow-up findings`
