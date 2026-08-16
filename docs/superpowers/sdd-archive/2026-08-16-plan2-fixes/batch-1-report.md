# Batch 1 report — gating and safety

Date: 2026-08-16. Branch: `johncioni/plan2-fixes` at base `3919b99`.

## Changed

- F1: added typed `PhotoWorkflowState`; `canApprove` now accepts only
  `preview_ready` and `review_required`, so `verified` cannot be re-approved.
- F2: “All Photos” now opens a visible confirmation naming the snapshot photo
  count and full consequence. Confirm is destructive; Cancel is the default.
- F3: drops route through `ingestDropped`, which synchronously reserves the
  command before starting async work and returns `false` while app/CLI work is active.
- F4: chose stroke-proximity targeting because it maps a grab to the visible
  outline without an extra selection step. The nearest outline wins; filled
  interiors cannot steal another crop. The focusable overlay accepts arrow keys,
  and drag and keyboard both use the same normalized, clamped nudge function.
- F5: moved `PhotoStateAppearance` to a typed enum; toolbar/sidebar counts query
  `.needsReview`, never the display label.
- F6: partial-ingest filename/reason lines are prepended to the existing banner
  details disclosure (stderr remains below them). Removed dead `lastAdvanced`
  and `lastPublished`; publishing still uses `onPublished`. Retained the required
  `lastMutatingArgs` test seam and the latest `lastIngestFailures` data.

## Test-first and mutation evidence

Before production edits, the focused command exited 1 because the seven new APIs
did not exist. After implementation it ran 7/7 GREEN.

Mutation command:

```bash
swift test --disable-sandbox --package-path app/PrintworksCore --filter 'AppModelTests.testVerifiedPhotoCannotBeApproved|AppModelTests.testReprocessAllConfirmationNamesPhotoCount|AppModelTests.testDropIsRefusedWhileMutationOrExternalLockIsActive|AppModelTests.testPartialIngestBannerDetailsListFilenameAndReason|ContractTests.testNeedsReviewCountUsesTypedAppearanceCase|CropMathTests.testGrabOnEightByTenOutlineTargetsEightByTen|CropMathTests.testKeyboardNudgeMatchesEquivalentClampedDrag'
```

Result: **exit 1**, 7 tests executed, 9 assertion failures. Every mutation was
then restored with `apply_patch`.

| New test | Injected production defect | RED evidence |
|---|---|---|
| `testVerifiedPhotoCannotBeApproved` | allowed `.verified` in `canApprove` | `XCTAssertFalse failed` |
| `testReprocessAllConfirmationNamesPhotoCount` | added one to snapshot count | `4 photos` vs `3 photos` |
| `testDropIsRefusedWhileMutationOrExternalLockIsActive` | reported refused drops as accepted | two `XCTAssertFalse failed` |
| `testPartialIngestBannerDetailsListFilenameAndReason` | rendered failure codes instead of reasons | `BAD_INPUT` vs reason text |
| `testNeedsReviewCountUsesTypedAppearanceCase` | renamed label and regressed count to label comparison | `0` vs `2` |
| `testGrabOnEightByTenOutlineTargetsEightByTen` | restored filled-interior targeting | `5x7` vs `8x10` |
| `testKeyboardNudgeMatchesEquivalentClampedDrag` | reversed keyboard Down | `y=0.0` vs clamped `y=0.04` |

Restored focused command: **exit 0**, 7 tests, 0 failures.

## Required gates

- `swift build --disable-sandbox --package-path app/PrintworksCore` — **exit 0**.
- `swift test --disable-sandbox --package-path app/PrintworksCore` — **exit 0**;
  92 tests, 0 failures.
- `xcodebuild -project app/RAWdogPrintworks/RAWdogPrintworks.xcodeproj -scheme RAWdogPrintworks -configuration Release OTHER_SWIFT_FLAGS='$(inherited) -disable-sandbox' build` — **exit 0**, `BUILD SUCCEEDED`. Expected
  CoreSimulator/FSEvents warnings were benign.
- `.venv/bin/python -m pytest tests/ -q` — **exit 0**; 295 passed, 1 skipped.

## Scope and checkpoint

No README OUT-OF-SCOPE item was changed, including the named adjacent regions
in Grid/Sidebar/Inspector/Review/RepoWatcher and `scripts/build-app.sh`. No git
add or commit was run. No task remains in flight. Per this batch brief, this
report is the checkpoint and `HANDOFF.md` remains unchanged.
