### Task 11: End-to-end smoke test, release build script, visual QA gate

**Files:**
- Create: `Tests/PrintworksCoreTests/SmokeTests.swift`, `scripts/build-app.sh`
- Test: itself + the visual QA checklist

**Interfaces:**
- Produces:
  - `SmokeTests` — builds a temp fixture repo (dirs from `tests/conftest.py` list; two fake photos: recipes + tiny preview JPG bytes) and a stub `python` shell script that answers `status --json` from a canned `StatusSnapshot` JSON (with `stale_previews: []`), `adjust`/`preview`/`approve`/`run` from canned envelopes (adjust/preview envelopes carry a `review_revision_before/after` pair matching the canned status revisions). Drives the REAL `PipelineClient` + `AppModel` end-to-end through the full spec-§8 flow: refresh → startDraft → `setSlider` → `flushPendingAdjustments` (debounced adjust fires, draft REBASES on the revision pair, not stale) → check all → approve → asserts the adjust/approve/run arg sequence, the review-file contents the stub received, and the final refresh landed. This is the app-side twin of Plan 1's fixtures — it catches wiring drift the unit fakes can't.
  - `scripts/build-app.sh`:

```bash
#!/bin/zsh
set -euo pipefail
cd "$(dirname "$0")/.."
(cd app/RAWdogPrintworks && xcodegen generate)
xcodebuild -project app/RAWdogPrintworks/RAWdogPrintworks.xcodeproj \
  -scheme RAWdogPrintworks -configuration Release \
  -derivedDataPath app/build build
APP="app/build/Build/Products/Release/RAWdogPrintworks.app"
codesign --force --deep --sign - "$APP"
echo "Built + ad-hoc signed: $APP"
echo "Install: cp -R \"$APP\" /Applications/"
```

  - **Visual QA gate (done-criteria, spec §8):** run the Release app against the real repo and capture screenshots of: grid, review (each of the 4 styles), compare mode, crop overlay, slider adjust with shimmer, render progress (trigger a reprocess of one photo), busy pill (hold the lock via a paused CLI `run` in another terminal), stale-draft banner (touch a sidecar mid-draft), error banner (bogus python path). Every screenshot is reviewed by eye before this task is complete; the review is recorded in the task's completion note. Green tests alone do not close this task.

- [ ] **Step 1: Write SmokeTests** (canned JSON inline in the test file; stub script pattern from Task 3) → fail (compile) → implement any missing glue. Structure (the stub dispatches on `$1`; canned payloads are string constants in the test file):

```swift
@MainActor
final class SmokeTests: XCTestCase {
    func testFullReviewFlowAgainstStubPipeline() async throws {
        let repo = try makeFixtureRepo()          // conftest dir list + 2 recipes + tiny preview JPGs
        let stub = try makeStubPython(at: repo)   // case "$1" in status) … adjust) … approve) … run) …
        // PipelineClient conforms to PipelineRunning via the Task 5
        // extension — passed directly, no adapter type exists.
        // executableOverride is REQUIRED here: without it the client runs
        // `stub -m pipeline <args>` and the stub (which dispatches on $1)
        // would see "-m" as its command.
        let client = PipelineClient(
            config: PipelineConfig(repo: repo, python: stub),
            executableOverride: stub)
        let model = AppModel(client: client,
                             repo: repo, sliderDebounce: .zero)
        await model.refresh()
        XCTAssertEqual(model.snapshot?.photos.count, 2)

        model.startDraft(stem: "P1")
        model.setSlider(stem: "P1", style: "natural", temperature: 5600,
                        exposure: nil)
        await model.flushPendingAdjustments(stem: "P1")
        // Canned adjust envelope carries review_revision_before/after matching
        // the canned status revisions → the draft REBASES, not stales.
        XCTAssertFalse(model.drafts["P1"]!.isStale)

        for key in ["eyes_open", "expressions_natural", "no_blinks_in_crops"] {
            model.drafts["P1"]!.checks[key] = true
        }
        await model.approve(stem: "P1")
        // The stub logs argv per call to <repo>/stub-calls.log; assert the
        // sequence adjust → approve (with a readable review-file whose
        // expected_review_revision matches) → run --stem P1 → final status.
        let calls = try String(contentsOf: repo.appendingPathComponent("stub-calls.log"),
                               encoding: .utf8).split(separator: "\n")
        XCTAssertTrue(calls.contains { $0.hasPrefix("adjust") })
        XCTAssertTrue(calls.contains { $0.hasPrefix("approve") })
        XCTAssertTrue(calls.contains { $0.hasPrefix("run --stem P1") })
    }
}
```
- [ ] **Step 2: Gate** — full `swift test` + `xcodebuild build` + `zsh scripts/build-app.sh` all succeed.
- [ ] **Step 3: Visual QA** — capture + review the screenshot set; fix what the eye finds; re-shoot.
- [ ] **Step 4: Commit**

```bash
git add app/ scripts/build-app.sh
git commit -m "feat(app): e2e smoke test, release build script, visual QA pass"
```

---

## Self-Review

1. **Spec coverage:** §4.1 components → Tasks 3 (PipelineClient), 5 (AppModel), 6 (RepoWatcher), 7–10 (views); §5.1 visual language → Task 1 Theme + view tasks; §5.2 window structure → Task 7; §5.3 review interactions → Tasks 8–9 (⌘1–4/space/C/arrows, sliders+debounce, checklist, approve gating incl. stale previews); §5.4 ingest → Tasks 7 (drop) + 10 (banner, conflicts surfaced from pipeline result); §5.5 settings → Task 10; §6 data flows → Tasks 5, 8–10; §6.1 drafts → Task 5 (rebase rule, stale, deferred reconcile) + Task 9 (re-confirm UI); §7 error handling → Tasks 3 (INTERNAL synth, envelope trust), 5 (banner, busy pill), 7 (ErrorBanner actions); §8 testing → fixtures (Task 2), stream/model tests (3, 5), smoke (11), visual QA (11); notifications → Task 10; ad-hoc signing → Task 11.
2. **Placeholder scan:** Task 7–10 view bodies are deliberately skeleton-plus-fixed-names (build-gated, logic pre-tested in core) — each carries the structural code and exact behavior list; no TBDs.
3. **Type consistency:** Contract type names fixed in Task 2's Interfaces and reused verbatim in Tasks 3, 5, 11 test code; `PipelineRunning` protocol (Task 5) is what views consume via `AppModel` only; check keys (`eyes_open` etc.) and audit strings match between Task 5's tests and spec §4.3's review-file example; CLI spellings match Plan 1's Global Constraints line.
