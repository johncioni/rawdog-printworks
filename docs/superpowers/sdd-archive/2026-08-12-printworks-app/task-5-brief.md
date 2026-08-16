### Task 5: `AppModel` — state tree, drafts, actions

**Files:**
- Create: `Sources/PrintworksCore/AppModel.swift`
- Test: `Tests/PrintworksCoreTests/AppModelTests.swift`

**Interfaces:**
- Consumes: `PipelineClient` (behind a protocol so tests inject a fake), Contract types, `Debouncer`.
- Produces:
  - `protocol PipelineRunning: Sendable` — `func status() async -> CommandResult<StatusSnapshot>`; `func mutate<R>(_ type: R.Type, args: [String], onEvent: (@Sendable (ProgressEvent) -> Void)?) async -> CommandResult<R>`; `func crops(stem: String) async -> CommandResult<CropsResult>`. `PipelineClient` gets a conforming extension mapping to `run`/`runMutating` with the canonical arg spellings. The model stores each failure's `stderrTail` alongside `banner` (`bannerDetails: String?`) for the Show Details disclosure.
  - **Result-before-error rule (binding):** on any `ok: false` envelope with a non-nil `result` (aggregate `run`/`ingest`), the model applies the result's successes (progress records, notifications for `published` entries) BEFORE setting `banner`; every action's exit path — success or failure — ends with `refresh()`.
  - `struct ReviewDraft: Sendable { stem: String; baseRevision: String; checks: [String: Bool]; note: String; cropNudges: [String: CropWindow]; isStale: Bool }` — check keys: `"eyes_open"`, `"expressions_natural"`, `"no_blinks_in_crops"`.
  - `@Observable @MainActor final class AppModel`:
    - `init(client: PipelineRunning, repo: URL, sliderDebounce: Duration = .seconds(2))` — `repo` is needed for `pendingInputFiles` (Task 10) and repo-relative path resolution; exposed as `let repo: URL`.
    - Published state: `snapshot: StatusSnapshot?`, `drafts: [String: ReviewDraft]`, `banner: PipelineErrorInfo?`, `bannerDetails: String?` (stderr tail), `busyExternally: Bool`, `activeCommand: String?` (nil = idle), `activeStem: String?` (the stem the active command targets, for §6.1 deferred reconcile), `renderProgress: [String: ProgressEvent]` (latest per stem), `selectedStem: String?`, `selectedStyle: String` (default `"natural"`), `selectedDeliveryId: String??` (`.none` = browse all; `.some(nil)` = the "Earlier" group) — consumed by Task 7's sidebar; `lastPublished: [PublishedPhoto]` (successes from the most recent run result — applied even on `PARTIAL_FAILURE`, drives Task 10's notifications).
    - Slider debouncing is keyed **per (stem, style)**: `private var debouncers: [String: Debouncer]` keyed `"\(stem)|\(style)"`, each with its own pending temperature/exposure accumulator — switching photo or style must never cancel or merge another pair's pending edit. `flushPendingAdjustments(stem:) async` flushes every debouncer for that stem (all styles) — approve calls it.
    - `func reprocess(stem: String) async` / `func reprocessAll() async` — `run --stem S --force --json` / `run --force --json` through the standard action cycle (consumed by Task 7's toolbar; test asserts args).
    - `func retryBannerAction() async` — re-runs the last failed action for `RENDER_FAILED`/`VERIFY_FAILED`/`INTERNAL` banners (the model remembers the last mutating args); `.openSettings` and `.reReview` are signaled to views via `bannerAction: BannerAction?` (`enum BannerAction { case retry, openSettings, reReview }` derived from the error code per spec §7).
    - `func refresh() async` — `client.status()`; on ok: store snapshot, `busyExternally = snapshot.lock.held && activeCommand == nil`, reconcile drafts (below); on error: `banner = error`.
    - Draft reconcile: for each draft, if the photo's `reviewRevision != draft.baseRevision` and no rebase pair matched since the last refresh → `isStale = true` (contents preserved). While `activeCommand != nil && activeStem == stem`, defer reconcile for that stem (spec §6.1); reconcile once at the command's terminal refresh.
    - **One shared rebase path** used by BOTH `applyAdjust` and `rerenderPreview` (their results carry the same `reviewRevisionBefore/After` pair): `rebase(stem:, before:, after:)` — rebases iff `draft.baseRevision == before` (→ `baseRevision = after`), else marks stale.
    - `func reReview(stem: String)` — the stale-banner action: adopts the photo's current `reviewRevision` as the draft's `baseRevision`, **resets all three checks to false** (the user must re-verify against the fresh pixels), clears `isStale`, keeps the note and crop nudges.
    - `func startDraft(stem: String)` — creates a draft keyed to the photo's current `reviewRevision`, all checks false.
    - `func canApprove(stem: String) -> Bool` — draft exists, all three checks true, `!isStale`, photo `stalePreviews.isEmpty`, `activeCommand == nil`, `!busyExternally`.
    - `func setSlider(stem: String, style: String, temperature: Double?, exposure: Double?)` — stores pending values and debounces `applyAdjust`.
    - `func applyAdjust(stem: String, style: String, temperature: Double?, exposure: Double?) async` — `mutate(AdjustResult…)`; on ok, rebase the stem's draft iff `draft.baseRevision == result.reviewRevisionBefore` → `baseRevision = result.reviewRevisionAfter`; else mark stale. Then `refresh()`.
    - `func approve(stem: String) async` — flush the debouncer; build the review-file JSON (audit strings below, crops = `crops` from status merged with `cropNudges`, `expected_review_revision` = draft.baseRevision); write to `FileManager.default.temporaryDirectory`; `mutate(ApproveResult…, args: ["approve", "--stem", stem, "--review-file", path, "--json"])`; on ok chain `mutate(RunResult…, args: ["run", "--stem", stem, "--json"])` feeding `renderProgress`; delete temp file; `refresh()`; on `STALE_REVIEW` → banner + mark draft stale.
    - Audit string mapping: `"eyes open — all: pass"`, `"expressions natural: pass"`, `"no blinks in crops: pass"`, plus `"note: \(note)"` when non-empty — only checked items make `canApprove` true, so all three always serialize as `: pass`.
    - `func ingest(paths: [String]) async` — `mutate(IngestResult…, args: ["ingest", "--from"] + paths + ["--delivery-id", UUID().uuidString, "--json"])`, then `mutate(RunResult…, ["run", "--json"])`, then refresh; surfaces skips/conflicts via `banner` when non-empty (message joined).
    - `func deliveries() -> [(id: String?, photos: [PhotoStatus])]` — group by `deliveryId`, `nil` last as "Earlier", newest `ingestedAt` first.

- [ ] **Step 1: Write the failing tests** (fake client; the heart of the task)

```swift
import XCTest
@testable import PrintworksCore

/// Scriptable fake: every call pops the next canned envelope.
/// (Envelopes are wrapped in CommandResult with an empty stderrTail.)
final class FakeClient: PipelineRunning, @unchecked Sendable {
    var statusQueue: [Envelope<StatusSnapshot>] = []
    var mutateLog: [[String]] = []
    var mutateHandler: ((_ args: [String]) -> Any)!

    func status() async -> CommandResult<StatusSnapshot> {
        CommandResult(envelope: statusQueue.removeFirst(), stderrTail: "")
    }
    func crops(stem: String) async -> CommandResult<CropsResult> {
        CommandResult(envelope: Envelope(ok: true, result: CropsResult(
            stem: stem, basis: "faces", windows: [:]), error: nil),
            stderrTail: "")
    }
    func mutate<R>(_ type: R.Type, args: [String],
                   onEvent: (@Sendable (ProgressEvent) -> Void)?) async
    -> CommandResult<R> {
        mutateLog.append(args)
        return CommandResult(envelope: mutateHandler(args) as! Envelope<R>,
                             stderrTail: "")
    }
}

@MainActor
final class AppModelTests: XCTestCase {
    private func photo(stem: String, revision: String,
                       stale: [String] = []) -> PhotoStatus {
        PhotoStatus(stem: stem, state: "review_required", deliveryId: "d1",
                    ingestedAt: "2026-08-12T00:00:00Z",
                    reviewRevision: revision, previews: [:], previewHashes: [:],
                    stalePreviews: stale, adjustments: [:], crops: [:],
                    expressionAudit: [], published: PublishedInfo(
                        version: nil, path: nil, artifactCount: nil))
    }

    private func snap(_ photos: [PhotoStatus],
                      lockHeld: Bool = false) -> Envelope<StatusSnapshot> {
        Envelope(ok: true, result: StatusSnapshot(
            repo: "/r", toolchain: ToolchainStatus(ok: true, failures: []),
            lock: LockStatus(held: lockHeld, stale: false, pid: nil),
            styles: ["natural", "filmic", "bw", "vibrant"],
            photos: photos), error: nil)
    }

    func testExternalRevisionChangeMarksDraftStale() async {
        let fake = FakeClient()
        fake.statusQueue = [snap([photo(stem: "P1", revision: "r1")]),
                            snap([photo(stem: "P1", revision: "r2")])]
        let model = AppModel(client: fake, repo: URL(fileURLWithPath: "/r"), sliderDebounce: .zero)
        await model.refresh()
        model.startDraft(stem: "P1")
        await model.refresh()                       // external change r1→r2
        XCTAssertTrue(model.drafts["P1"]!.isStale)
    }

    func testAdjustRebasesDraftOnMatchingPair() async {
        let fake = FakeClient()
        fake.statusQueue = [snap([photo(stem: "P1", revision: "r1")]),
                            snap([photo(stem: "P1", revision: "r2")])]
        fake.mutateHandler = { _ in
            Envelope(ok: true, result: AdjustResult(
                stem: "P1", style: "natural", preview: "p.jpg",
                temperature: Control(value: 5600, source: "sidecar"),
                exposure: Control(value: nil, source: "camera"),
                reviewRevisionBefore: "r1", reviewRevisionAfter: "r2"),
                error: nil)
        }
        let model = AppModel(client: fake, repo: URL(fileURLWithPath: "/r"), sliderDebounce: .zero)
        await model.refresh()
        model.startDraft(stem: "P1")
        await model.applyAdjust(stem: "P1", style: "natural",
                                temperature: 5600, exposure: nil)
        XCTAssertFalse(model.drafts["P1"]!.isStale)
        XCTAssertEqual(model.drafts["P1"]!.baseRevision, "r2")
    }

    func testCanApproveGates() async {
        let fake = FakeClient()
        fake.statusQueue = [snap([photo(stem: "P1", revision: "r1")])]
        let model = AppModel(client: fake, repo: URL(fileURLWithPath: "/r"), sliderDebounce: .zero)
        await model.refresh()
        model.startDraft(stem: "P1")
        XCTAssertFalse(model.canApprove(stem: "P1"))     // unchecked boxes
        for key in ["eyes_open", "expressions_natural", "no_blinks_in_crops"] {
            model.drafts["P1"]!.checks[key] = true
        }
        XCTAssertTrue(model.canApprove(stem: "P1"))
        model.drafts["P1"]!.isStale = true
        XCTAssertFalse(model.canApprove(stem: "P1"))
    }

    func testStalePreviewsBlockApprove() async {
        let fake = FakeClient()
        fake.statusQueue = [snap([photo(stem: "P1", revision: "r1",
                                        stale: ["filmic"])])]
        let model = AppModel(client: fake, repo: URL(fileURLWithPath: "/r"), sliderDebounce: .zero)
        await model.refresh()
        model.startDraft(stem: "P1")
        for key in ["eyes_open", "expressions_natural", "no_blinks_in_crops"] {
            model.drafts["P1"]!.checks[key] = true
        }
        XCTAssertFalse(model.canApprove(stem: "P1"))
    }

    func testBusyPillFromExternalLock() async {
        let fake = FakeClient()
        fake.statusQueue = [snap([], lockHeld: true)]
        let model = AppModel(client: fake, repo: URL(fileURLWithPath: "/r"), sliderDebounce: .zero)
        await model.refresh()
        XCTAssertTrue(model.busyExternally)
    }

    func testApproveChainsRunAndSendsReviewFile() async throws {
        let fake = FakeClient()
        fake.statusQueue = [snap([photo(stem: "P1", revision: "r1")]),
                            snap([photo(stem: "P1", revision: "r9")])]
        nonisolated(unsafe) var reviewFileBody: [String: Any]?
        fake.mutateHandler = { args in
            if args.first == "approve" {
                if let i = args.firstIndex(of: "--review-file"),
                   let data = FileManager.default.contents(atPath: args[i + 1]) {
                    reviewFileBody = try? JSONSerialization.jsonObject(
                        with: data) as? [String: Any]
                }
                return Envelope(ok: true, result: ApproveResult(
                    stem: "P1", state: "approved", fingerprint: "f"),
                    error: nil) as Any
            }
            return Envelope(ok: true, result: RunResult(
                published: [PublishedPhoto(stem: "P1", version: "v004",
                                           artifactCount: 29)],
                advanced: [], failed: []), error: nil) as Any
        }
        let model = AppModel(client: fake, repo: URL(fileURLWithPath: "/r"), sliderDebounce: .zero)
        await model.refresh()
        model.startDraft(stem: "P1")
        for key in ["eyes_open", "expressions_natural", "no_blinks_in_crops"] {
            model.drafts["P1"]!.checks[key] = true
        }
        await model.approve(stem: "P1")
        XCTAssertEqual(fake.mutateLog.map(\.first), ["approve", "run"])
        let body = try XCTUnwrap(reviewFileBody)
        XCTAssertEqual(body["expected_review_revision"] as? String, "r1")
        let audit = try XCTUnwrap(body["expression_audit"] as? [String])
        XCTAssertTrue(audit.contains("eyes open — all: pass"))
    }

    func testDebouncersAreKeyedPerStemAndStyle() async {
        let fake = FakeClient()
        fake.statusQueue = Array(repeating: snap([photo(stem: "P1", revision: "r1"),
                                                  photo(stem: "P2", revision: "r1")]),
                                 count: 4)
        fake.mutateHandler = { args in
            Envelope(ok: true, result: AdjustResult(
                stem: args[args.firstIndex(of: "--stem")! + 1],
                style: args[args.firstIndex(of: "--style")! + 1],
                preview: "p.jpg",
                temperature: Control(value: 5600, source: "sidecar"),
                exposure: Control(value: nil, source: "camera"),
                reviewRevisionBefore: "r1", reviewRevisionAfter: "r1"),
                error: nil)
        }
        let model = AppModel(client: fake, repo: URL(fileURLWithPath: "/r"),
                             sliderDebounce: .zero)
        await model.refresh()
        // Two different (stem, style) pairs scheduled back-to-back: BOTH fire.
        model.setSlider(stem: "P1", style: "natural", temperature: 5600,
                        exposure: nil)
        model.setSlider(stem: "P2", style: "bw", temperature: 5400,
                        exposure: nil)
        await model.flushPendingAdjustments(stem: "P1")
        await model.flushPendingAdjustments(stem: "P2")
        let adjustTargets = fake.mutateLog.filter { $0.first == "adjust" }
            .map { "\($0[$0.firstIndex(of: "--stem")! + 1])|\($0[$0.firstIndex(of: "--style")! + 1])" }
        XCTAssertEqual(Set(adjustTargets), ["P1|natural", "P2|bw"])
    }

    func testReReviewAdoptsRevisionAndResetsChecks() async {
        let fake = FakeClient()
        fake.statusQueue = [snap([photo(stem: "P1", revision: "r1")]),
                            snap([photo(stem: "P1", revision: "r2")])]
        let model = AppModel(client: fake, repo: URL(fileURLWithPath: "/r"),
                             sliderDebounce: .zero)
        await model.refresh()
        model.startDraft(stem: "P1")
        for key in ["eyes_open", "expressions_natural", "no_blinks_in_crops"] {
            model.drafts["P1"]!.checks[key] = true
        }
        await model.refresh()                       // r1 → r2: stale
        XCTAssertTrue(model.drafts["P1"]!.isStale)
        model.reReview(stem: "P1")
        let draft = model.drafts["P1"]!
        XCTAssertFalse(draft.isStale)
        XCTAssertEqual(draft.baseRevision, "r2")
        XCTAssertTrue(draft.checks.values.allSatisfy { $0 == false })
    }

    func testPartialFailureAppliesResultBeforeBanner() async {
        let fake = FakeClient()
        fake.statusQueue = [snap([photo(stem: "P1", revision: "r1")]),
                            snap([photo(stem: "P1", revision: "r1")])]
        fake.mutateHandler = { _ in
            Envelope(ok: false, result: RunResult(
                published: [PublishedPhoto(stem: "P1", version: "v004",
                                           artifactCount: 29)],
                advanced: [], failed: [StemFailure(
                    stem: "P2", code: "VERIFY_FAILED", message: "bad")]),
                error: PipelineErrorInfo(code: "PARTIAL_FAILURE",
                                         message: "1 of 2 failed"))
        }
        let model = AppModel(client: fake, repo: URL(fileURLWithPath: "/r"),
                             sliderDebounce: .zero)
        await model.refresh()
        await model.reprocessAll()
        XCTAssertEqual(model.lastPublished.map(\.stem), ["P1"])  // result first
        XCTAssertEqual(model.banner?.code, "PARTIAL_FAILURE")    // then error
    }
}
```

- [ ] **Step 2: Run to verify failure**, **Step 3: Implement `AppModel.swift`** per the Interfaces block. Key mechanics: `@Observable @MainActor final class`; `PhotoStatus` needs a public memberwise init (add to Contract.swift alongside `CropWindow`'s — same for the other structs used by tests: `StatusSnapshot`, `ToolchainStatus`, `LockStatus`, `PublishedInfo`, `Control`, `AdjustResult`, `ApproveResult`, `RunResult`, `PublishedPhoto`, `CropsResult`); review-file serialization via `JSONSerialization` with keys `expected_review_revision`, `expression_audit`, `crops` (windows as `{"x":…,"y":…,"w":…,"h":…}` dropping `source`); crops for approve come from the photo's persisted `crops` else the `crops()` command result, overridden by `cropNudges`.

- [ ] **Step 4: Run to verify pass** — `swift test --package-path app/PrintworksCore` → PASS.

- [ ] **Step 5: Commit**

```bash
git add app/PrintworksCore
git commit -m "feat(app): AppModel — snapshot state, draft lifecycle, approve chain"
```

---

