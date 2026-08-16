# Task 7 fix round 1 report

Scope: exactly M1, M2, M3, m4, and m5 from `task-7-rereview.md`.
No claim that Task 7 ships; the controller owns the gate rerun and smoke.

## M1 — watcher lifetime

- Chose an app-scoped watcher rather than making the primary scene single-window.
  `WindowGroup` remains the intended primary-scene model, and `RepoWatcher`
  already supports independent continuation cancellation.
- Removed the per-window `defer { watcher.stop() }`. A closing window now drops
  only its continuation; the shared watch sources stop from `RepoWatcher.deinit`.
- Evidence: source reasoning plus the full gate's passing
  `testCancellingOneConsumerDoesNotFinishAnother`. The requested live
  ⌘N/⌘W/watched-directory scenario was not run because the final dispatch says
  not to open the app and assigns that smoke to the controller.

## M2 — content-hash preview cache

- Added reusable `Sources/PreviewImage.swift`; both `GridView` and `SidebarView`
  now use it instead of constructing `NSImage(contentsOf:)` in `body`.
- `.task(id:)` is keyed by a request containing the content hash and target pixel
  size. ImageIO source creation and `CGImageSourceCreateThumbnailAtIndex` run on
  a cache actor, with the target derived from view size × display scale.
- Cache entries live in `PreviewImageCache`, keyed by content hash + target pixel
  size. When a view's content hash changes, every cached size for the old hash is
  evicted before the replacement is loaded.
- Evidence: the generated Xcode project includes the file and the app build
  compiled it successfully. No performance timing or live-render smoke was run.

## M3 — ingest run-failure Retry

- Added private plain `runAll()` (`run --json`) and wired only the post-ingest
  run-failure Retry to it. Explicit Reprocess All remains `run --force --json`.
- Added `testIngestRunFailureRetryDoesNotForceWholeRepo` in `AppModelTests`.
- RED: focused test exited 1; actual Retry args were
  `["run", "--force", "--json"]`, failing both the equality and no-force checks.
- GREEN: the same focused test exited 0; Retry args were `["run", "--json"]`.

## m4 — badge contrast

- Replaced the photo-sampling `.ultraThinMaterial` state-chip background with
  `Theme.panel.opacity(0.85)`.
- Evidence: app build exited 0. Contrast was not re-sampled; controller owns QA.

## m5 — render-failed badge

- Cards whose stem is present in `model.lastFailures` now show a top-right
  `Render failed` badge with Retry.
- Retry calls public `retryRender(stem:)`, which issues plain
  `run --stem <stem> --json` (never `--force`).
- Evidence: app build exited 0. The failed-card UI state was not smoke-tested.

## Gates and boundaries

- `xcodegen generate`: exit 0.
- `swift test --disable-sandbox --package-path app/PrintworksCore`: exit 0,
  60 tests passed.
- `xcodebuild ... OTHER_SWIFT_FLAGS='$(inherited) -disable-sandbox' build`:
  exit 0, `BUILD SUCCEEDED`; CoreSimulator/FSEvents noise was benign.
- m6–m10 and i11/i12 were left unchanged. `HANDOFF.md` was not rewritten; its
  pre-existing worktree modification was left untouched.
- The requested commit could not be created in this managed session. `git add`
  failed to create
  `/Users/john/Projects/rawdog-printworks/.git/worktrees/plan2-printworks-app/index.lock`
  (`Operation not permitted`) because the real worktree Git metadata is outside
  the writable roots. Nothing was staged. Intended commit message:
  `fix(app): Task 7 review findings — watcher, previews, retry`.
