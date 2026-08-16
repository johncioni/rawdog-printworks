# Task 11 fix round 1 — dispatch (final round of Plan 2's task list)

Read `task-11-rereview.md` first; it is the authority. Task 11 is COMPLETE — this
round hardens the safety net before the whole-branch review. One commit, then stop.

## M1 (MEDIUM) — the smoke test models an approve that cannot happen

`SmokeTests.swift:7` gives P1 exactly one crop (`"8x10"`), but the real pipeline
requires both: `pipeline/paths.py:5` defines `CROPS = ("8x10","5x7")` and
`pipeline/driver.py:498-502` raises `BAD_INPUT: crops missing windows: ['5x7']`.
`AppModel.approveCropWindows` short-circuits the `crops --stem` fetch when the
photo already has persisted windows, so the one-crop fixture produces a one-crop
review file — and the stub blindly `cp`s it and returns canned success.

Two consequences, both bad: the approve this test "proves" would fail against the
real pipeline, and **deleting the `crops` key from `writeReviewFile` entirely
leaves every assertion passing** while every real approve dies.

Fix: give P1 **both** `8x10` and `5x7` in the canned status, and assert the
review-file `crops` dictionary has both keys, with the expected geometry and
**no** `source` field (`AppModel.swift:749-752` deliberately strips it).
Then prove it: delete the `crops` key from `writeReviewFile`, watch the smoke
test go RED, revert. Record that.

## M2 (MEDIUM) — the smoke test does not pin "no repo writes from Swift"

That is one of Plan 2's binding constraints and nothing in the suite enforces it.
Per the finding: snapshot the fixture repo before the flow and assert afterwards
that the only changes are the ones the stub itself made. Make it fail if the app
writes anything.

## L1 (LOW) — the render progress bar snaps back to 0% on stage boundaries

Per the finding. This is the one user-visible defect in the round; it is why the
bar looks broken during a real multi-stage render.

## L2 (LOW) — `scripts/build-app.sh`

`--deep` is pointless now and wrong later, and nothing verifies the signature
after signing. Drop `--deep`, add a `codesign --verify` (and let a failure fail
the script — `set -e` alone does not cover every path).

## Do NOT change

The `OTHER_SWIFT_FLAGS` env quirk (I2) is an agent-environment artifact, not a
script defect — the controller's run on a normal shell exited 0 unaided. Leave
the script's flags alone. I3's defensive `break` is fine as-is.

## Gates

```
swift test --disable-sandbox --package-path app/PrintworksCore
xcodebuild -project app/RAWdogPrintworks/RAWdogPrintworks.xcodeproj \
  -scheme RAWdogPrintworks -destination 'platform=macOS' \
  OTHER_SWIFT_FLAGS='$(inherited) -disable-sandbox' build
zsh scripts/build-app.sh
```

Exit code is the oracle, never a grep.

## Report + stop

Write `task-11-fix-round-1-report.md` **in this ledger directory**, including the
RED you induced for M1. You cannot commit — leave the work uncommitted with the
intended commit message. Do not open the app. Do NOT rewrite `HANDOFF.md`.
