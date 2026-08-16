# HANDOFF

## Goal
Deliver Task 11 Steps 1–2: a real PipelineClient/AppModel end-to-end smoke
test and the exact Release build/ad-hoc signing script. Leave Step 3 visual QA
to the controller and do not call Task 11 complete before that gate passes.

## Done
- Added `app/PrintworksCore/Tests/PrintworksCoreTests/SmokeTests.swift`.
- The fixture creates the `tests/conftest.py` directories, two recipes, two
  tiny previews, and a `$1`-dispatching stub with argv/review-file logs.
- The smoke drives refresh → draft → slider flush/adjust → rebase → checks →
  approve → targeted run → final refresh through real PipelineClient/AppModel.
- Required `executableOverride: stub` and matching `r1` → `r2` adjust/preview
  revision pairs are present; review-file revision and command order are tested.
- Deliberate missing-override mutation went RED with exit 1 by exposing the
  `-m pipeline` argv trap; restored focused test passed 1/1 with exit 0.
- Added executable `scripts/build-app.sh` exactly as specified.
- Full SwiftPM gate passed 84/84 with exit 0.
- Sandbox-disabled Xcode gate passed with exit 0.
- With `OTHER_SWIFT_FLAGS='$(inherited) -disable-sandbox'` exported, exact
  `zsh scripts/build-app.sh` passed with exit 0 and produced the signed app.
- Strict codesign verification passed with exit 0.
- Wrote ignored ledger file `.superpowers/sdd/2026-08-12-printworks-app/
  task-11-report.md`. Work remains uncommitted.

## Ruled out
- Omitting `executableOverride`: the stub sees `-m`, so no status loads.
- Mismatched canned revisions: they stale the draft instead of rebasing it.
- Bare release-script execution in this managed sandbox: exit 65 from nested
  `sandbox-exec: sandbox_apply: Operation not permitted`; exporting the
  mandatory Xcode Swift flag resolved it without changing the exact script.
- App launch, real pipeline execution, and screenshot judgment: Step 3 belongs
  to the controller and was intentionally not performed.

## In flight
Nothing. No tests, builds, app processes, or background tasks are running.

## Next
1. Controller: open the Release app from
   `app/build/Build/Products/Release/RAWdogPrintworks.app` against the safe
   configured scratch repo; never point it at `~/Projects/rawdog-printworks`.
2. Capture and eye-review the complete §8 Step 3 screenshot set, fix any visual
   defects, re-shoot, and record the results in `task-11-report.md`.
3. If code changes, rerun `swift test --disable-sandbox --package-path
   app/PrintworksCore` and the dispatch's sandbox-disabled Xcode gate.
4. Export `OTHER_SWIFT_FLAGS='$(inherited) -disable-sandbox'`, then run
   `zsh scripts/build-app.sh` and require exit 0.
5. After visual QA passes: `git add app/ scripts/build-app.sh` then
   `git commit -m 'feat(app): e2e smoke test, release build script, visual QA pass'`.
