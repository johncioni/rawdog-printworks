# HANDOFF

## Goal
Close Task 9 re-review findings M1–M5, N6, N11, and N12 for the
RAWdog Printworks macOS app while leaving N7–N10 and deferred work untouched.

## Done
- Read the fix dispatch and authoritative `task-9-rereview.md`.
- Fixed crop hit testing with `frame → contentShape → position`; 8×10 is no
  longer hidden by a full-canvas 5×7 hit shape, and letterbox presses are out.
- Clamped the live drag preview through `CropMath.nudged`.
- Decoupled crop loads from style switching and stopped cancelled revision
  retries; persisted crop status now falls back to `photo.crops`.
- Treat and revision-cache the specific missing-render-dimensions response as
  “no suggestion yet” without an error banner.
- Added stale-style guidance below Approve and restored the shortcut legend.
- Bounded crop results to a 40-entry LRU and crop queries to eight concurrent
  tracked requests.
- Added exposure-only and both-touched slider argv tests, plus crop cancellation,
  missing-dimensions, cache-eviction, and request-bound regression tests.
- Mutation RED evidence: one-decimal exposure and dropped pending temperature
  each failed their focused test with exit 1; both were restored to GREEN.
- `swift test --disable-sandbox --package-path app/PrintworksCore`: exit 0,
  75 tests passed.
- Required `xcodebuild ... OTHER_SWIFT_FLAGS='$(inherited) -disable-sandbox'
  build`: exit 0, `BUILD SUCCEEDED`.
- Wrote `.superpowers/sdd/2026-08-12-printworks-app/
  task-9-fix-round-1-report.md`. Work remains uncommitted.

## Ruled out
- Raw `.offset(translation)` for the live outline: it escapes the photo before
  snapping back, so the displayed window now uses the shared clamp.
- Refetching crops on every style change: crop geometry is style-independent.
- Live app/smoke work in this session: the dispatch assigns it to the controller
  against a scratch repo; no app or real-repo mutation was run.
- N7–N10 and prior deferred findings: explicitly out of scope.

## In flight
Nothing. No builds, tests, app processes, or background tasks are running.

## Next
1. Controller: run the app against the scratch repo and confirm an 8×10 drag
   works and a drag in the black letterbox changes neither crop.
2. Review `.superpowers/sdd/2026-08-12-printworks-app/
   task-9-fix-round-1-report.md` and the uncommitted diff.
3. If desired, rerun:
   `swift test --disable-sandbox --package-path app/PrintworksCore`
4. Then rerun the dispatch's `xcodebuild` command with
   `OTHER_SWIFT_FLAGS='$(inherited) -disable-sandbox'`.
5. Commit the scoped files with:
   `git commit -m 'fix(app): close Task 9 crop overlay review findings'`
