# Task 7 fix round 2 report

Scope: exactly M1, m2, m3, and m4 from
`task-7-fix-round-2-dispatch.md`, with
`task-7-fix-round-1-rereview.md` as the authority.

## M1 — bounded preview cache

- Quantized `maxPixelSize` upward onto a 256 px ladder before it enters the
  request/cache key: `(raw + 255) / 256 * 256`.
- Replaced the unbounded dictionary with an exact-cost LRU capped at both 40
  entries and 256 MiB of decoded pixel storage. Cost is
  `CGImage.bytesPerRow * CGImage.height`.
- On insertion, least-recently-used entries are evicted until both limits hold.
  Cache hits update recency. Hash eviction removes every size for that hash and
  subtracts its cost. An individual image over 256 MiB is returned to the view
  but is not cached.
- Worst-case retained cache storage, including a full-window review-canvas
  entry, is **268,435,456 bytes (256 MiB)** of decoded pixels across at most 40
  entries. Object/container overhead is not included in that decoded-pixel
  accounting. Oversized images cannot become permanent cache residents.

## m2 — no placeholder flash on resize

- Moved `preview = nil` inside the content-hash-changed branch. A size-only
  request keeps displaying the current pixels while a better-sized image loads;
  a changed or removed image hash still clears stale pixels.

## m3 — durable per-stem render failures

- `applyRunResult` now removes only stems reported as published/advanced and
  merges new failures by stem, so a targeted Retry cannot erase unrelated
  failures.
- A successful status refresh removes stored failures for stems whose disk
  state is now `verified`, preventing simultaneous Published/Render failed UI.
- Added two model tests covering both directions.
- RED: focused command with `--disable-sandbox` exited 1 with two expected
  assertion failures: P2 was erased after retrying P1, and P1 remained after a
  verified refresh.
- GREEN: the same focused command exited 0; 2 tests passed.

## m4 — opaque render-failed badge

- Replaced `Color.red.opacity(0.9)` with opaque `Color.red`, removing photo
  sampling from the failure-chip background.

## Gates and boundaries

- `swift test --disable-sandbox --package-path app/PrintworksCore`: exit 0,
  62 tests passed, 0 failures.
- `xcodebuild -project app/RAWdogPrintworks/RAWdogPrintworks.xcodeproj -scheme
  RAWdogPrintworks -destination 'platform=macOS'
  OTHER_SWIFT_FLAGS='$(inherited) -disable-sandbox' build`: exit 0,
  `BUILD SUCCEEDED`.
- No files were added to the Xcode target, so `xcodegen generate` was not needed.
- The app was not opened; the controller owns the smoke.
- Confirmed-done watcher M1 and `--force` M3 were not changed. Deferred i5/i6
  and all other out-of-scope findings were not changed.
- `HANDOFF.md` was read at session start and not rewritten.
- The work remains uncommitted because linked-worktree Git metadata is outside
  the writable roots. Intended commit message:
  `fix(app): bound previews and preserve render failures`.

## Changed paths

- `app/RAWdogPrintworks/Sources/PreviewImage.swift`
- `app/RAWdogPrintworks/Sources/GridView.swift`
- `app/PrintworksCore/Sources/PrintworksCore/AppModel.swift`
- `app/PrintworksCore/Tests/PrintworksCoreTests/AppModelTests.swift`
- `.superpowers/sdd/2026-08-12-printworks-app/task-7-fix-round-2-report.md`
