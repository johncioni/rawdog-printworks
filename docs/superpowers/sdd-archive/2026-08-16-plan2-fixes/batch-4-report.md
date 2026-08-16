# Batch 4 report

## Result

COMPLETE. Both PR #6 findings were addressed at the user-selected depth. No
out-of-scope fix was added and nothing was committed.

## Item 1 — bounded preview decoding (partial fix)

- Added a cache-wide FIFO async permit gate around the synchronous ImageIO
  decoder. Production permits are capped at 16.
- The grid uses adaptive 260-point cards; 16 permits exceed a normal visible
  page while placing a firm CPU/memory ceiling on a rapid-scroll decode storm.
- The test-only initializer can inject a smaller permit count so the bound can
  be exercised deterministically instead of depending on executor thread count.
- Same-key requests still share the single task stored in `inFlight`.
- Only the caller that creates that task removes its `inFlight` entry. Waiters
  no longer remove the shared entry when they resume.
- Deliberately deferred: cancellation propagation and per-key waiter tracking.
  The existing post-decode `Task.isCancelled` guard remains, and a synchronous
  ImageIO decode still runs to completion once started.

### RED / GREEN

- New bound test, with 4 distinct keys and an injected limit of 1, against the
  unbounded implementation:
  `swift test --disable-sandbox --package-path app/PrintworksCore --filter PreviewImageCacheTests.testConcurrentPreviewDecodesAreBoundedAndAllComplete`
  — exit 1. The over-limit start was `success` instead of `timedOut`, and peak
  concurrency was 4 instead of at most 1. All four requests were released and
  allowed to finish before the assertions.
- An initial version using the production limit of 16 was rejected because this
  executor did not schedule a seventeenth blocking detached task; it falsely
  passed the unbounded code. Injecting the low test limit makes the RED stable.
- Focused GREEN for both cache tests plus the settings test: 3 tests, exit 0.
- The complete 100-test Swift suite passed four consecutive times; see Gates.

## Item 2 — settings classification coverage

- The transient `INTERNAL` case now asserts the full
  `.transientError("temporary status read failed")` state and `allowsSave == true`.
- The `TOOLCHAIN_FAILED` case now asserts the full
  `.invalid("RawTherapee missing")` state and `allowsSave == false`.
- Added the missing `INTERNAL` / `"could not launch:"` case, asserting
  `.invalid(...)` and `allowsSave == false`.

### Required mutation evidence

Both mutations used
`swift test --disable-sandbox --package-path app/PrintworksCore --filter SettingsStatusValidationTests`.

1. Changed the transient default branch to `.valid`: exit 1. The new state
   assertion reported `valid` versus the expected `transientError`; the old
   `allowsSave`-only assertion would still have passed.
2. Changed the `could not launch:` branch to `.transientError`: exit 1. The
   state assertion reported `transientError` versus `invalid`, and the
   `allowsSave == false` assertion also failed.

Both mutations were reverted before GREEN verification.

## Gates

- `swift build --disable-sandbox --package-path app/PrintworksCore` — exit 0.
- `swift test --disable-sandbox --package-path app/PrintworksCore` — run four
  consecutive times; each run executed 100 tests with 0 failures and exited 0
  (15.804 s, 15.527 s, 15.497 s, and 15.502 s test time).
- `xcodebuild -project app/RAWdogPrintworks/RAWdogPrintworks.xcodeproj -scheme RAWdogPrintworks -configuration Release OTHER_SWIFT_FLAGS='$(inherited) -disable-sandbox' build`
  — exit 0, `** BUILD SUCCEEDED **`. Simulator/FSEvents diagnostics were
  non-fatal managed-environment noise.
- `.venv/bin/python -m pytest tests/ -q` — exit 0; 295 passed, 1 skipped.
- `git diff --check` — exit 0.

## Changed paths

- `app/PrintworksCore/Sources/PrintworksCore/PreviewImageCache.swift`
- `app/PrintworksCore/Tests/PrintworksCoreTests/PreviewImageCacheTests.swift`
- `app/PrintworksCore/Tests/PrintworksCoreTests/SettingsStatusValidationTests.swift`
- `.superpowers/sdd/2026-08-16-plan2-fixes/batch-4-report.md`

## HANDOFF check

`git status --short -- HANDOFF.md` produced no output and exited 0. `HANDOFF.md`
was not modified, so no checkout was needed.
