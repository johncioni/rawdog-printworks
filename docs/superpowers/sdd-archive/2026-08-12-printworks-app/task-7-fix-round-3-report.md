# Task 7 fix round 3 report

Scope: exactly M1, m2, and i3 from
`task-7-fix-round-3-dispatch.md`, with
`task-7-fix-round-2-rereview.md` as the authority.

## M1 + m2 — one durable failure stamp

- Replaced refresh's `state == "verified"` clearing rule with one
  `failureStamps` dictionary. Each `FailureStamp` stores the photo's optional
  published version and its review revision.
- `applyRunResult` writes that pair from the current snapshot when it merges a
  failed stem. If a failure arrives before any snapshot is available (the
  regression probe's test seam), the first successful refresh seeds the same
  stamp and does not treat an unknown baseline as evidence of resolution.
- A successful refresh clears a failure and its stamp only when either the
  published version or review revision differs from the stored pair. State by
  itself no longer clears anything: a failed forced re-render that stays at
  `verified` with `v001`/`r1` keeps its badge; a new published version or a
  changed review revision clears it.
- `applyRunResult` still clears failures immediately for stems returned in
  `published` or `advanced`, and now removes their stamps at the same time.
  These are the only other clearing paths.

## Regression tests and RED -> GREEN

- Added the review probe's verified-photo regression:
  `testForceReprocessFailureOnVerifiedPhotoKeepsBadge`. It asserts the exact
  `run --stem P1 --force --json` argv, that the failed-stem badge survives the
  terminal verified refresh, and that `PARTIAL_FAILURE` offers no banner
  action.
- Before the production fix, the focused command below exited 1 at the badge
  assertion: `XCTAssertNotNil failed - force-reprocess failure erased by the
  verified filter`. One test ran and failed. Production code was untouched at
  that point.

  ```sh
  swift test --disable-sandbox --package-path app/PrintworksCore \
    --filter AppModelTests.testForceReprocessFailureOnVerifiedPhotoKeepsBadge
  ```

- Extended the former disk-state test to prove `v001 -> v002` clears while an
  unchanged terminal `verified` snapshot does not, and added coverage proving
  `r1 -> r2` clears in a non-verified state. Before the production fix those
  two tests exited 1 with the expected opposite failures.
- After the fix, the M1 test plus both stamp-transition tests exited 0: 3 tests,
  0 failures.

## i3 — remove global content-hash eviction

- Deleted `PreviewImageCache.evict(contentHash:)` and its hash-change call
  site. A view still clears its own displayed preview when its hash changes;
  unreachable old cache keys now age out through the existing bounded LRU.
- The confirmed count/cost bounds, eviction loop, cache-hit recency, 256 px
  ladder, and image-loading guards were not changed.

## Gates and boundaries

- `swift test --disable-sandbox --package-path app/PrintworksCore`: exit 0,
  64 tests passed, 0 failures.
- `xcodebuild -project app/RAWdogPrintworks/RAWdogPrintworks.xcodeproj -scheme
  RAWdogPrintworks -destination 'platform=macOS'
  OTHER_SWIFT_FLAGS='$(inherited) -disable-sandbox' build`: exit 0,
  `BUILD SUCCEEDED`.
- `git diff --check` over the three source/test paths: exit 0.
- The app was not opened. No commit was attempted.
- The bounded cache, ladder, watcher fix, and both `--force` call sites were
  inspected in the scoped diff and not changed.
- `HANDOFF.md` was read and not touched; its pre-existing worktree modification
  remains outside this round.
- Intended commit message:
  `fix(app): preserve reprocess failures and rely on preview LRU`.

## Changed paths

- `app/PrintworksCore/Sources/PrintworksCore/AppModel.swift`
- `app/PrintworksCore/Tests/PrintworksCoreTests/AppModelTests.swift`
- `app/RAWdogPrintworks/Sources/PreviewImage.swift`
- `.superpowers/sdd/2026-08-12-printworks-app/task-7-fix-round-3-report.md`
