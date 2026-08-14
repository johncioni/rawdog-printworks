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

/// A `status` that takes measurable time, counting calls and overlap — for
/// the refresh gate.
final class SlowStatusClient: PipelineRunning, @unchecked Sendable {
    private let lock = NSLock()
    private let delay: Duration
    private var calls = 0
    private var inFlight = 0
    private var peak = 0

    init(delay: Duration) { self.delay = delay }

    var callCount: Int { lock.withLock { calls } }
    var maxConcurrent: Int { lock.withLock { peak } }

    func status() async -> CommandResult<StatusSnapshot> {
        lock.withLock {
            calls += 1
            inFlight += 1
            peak = max(peak, inFlight)
        }
        try? await Task.sleep(for: delay)
        lock.withLock { inFlight -= 1 }
        return CommandResult(envelope: Envelope(ok: true, result: StatusSnapshot(
            repo: "/r", toolchain: ToolchainStatus(ok: true, failures: []),
            lock: LockStatus(held: false, stale: false, pid: nil),
            styles: [], photos: []), error: nil), stderrTail: "")
    }

    func crops(stem: String) async -> CommandResult<CropsResult> {
        CommandResult(envelope: Envelope(ok: true, result: CropsResult(
            stem: stem, basis: nil, windows: [:]), error: nil), stderrTail: "")
    }

    func mutate<R>(_ type: R.Type, args: [String],
                   onEvent: (@Sendable (ProgressEvent) -> Void)?) async
    -> CommandResult<R> {
        fatalError("unused")
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

    // MARK: - Rebase rule, both halves (spec §6.1)
    //
    // The brief's cases cover "external change → stale" and "matching pair →
    // rebase". These cover the two branches that decide whether pixels the
    // user never saw can be approved, and neither is exercised above.

    /// The shared rebase path in isolation, with no refresh behind it: a
    /// non-matching `before` stales the draft on the spot. (The terminal
    /// reconcile catches the same case, so this asserts the rebase branch
    /// itself rather than the safety net underneath it.)
    func testRebaseStalesDirectlyOnUnmatchedBefore() async {
        let fake = FakeClient()
        fake.statusQueue = [snap([photo(stem: "P1", revision: "r1")])]
        let model = AppModel(client: fake, repo: URL(fileURLWithPath: "/r"),
                             sliderDebounce: .zero)
        await model.refresh()
        model.startDraft(stem: "P1")

        model.rebase(stem: "P1", before: "rX", after: "r2")
        XCTAssertTrue(model.drafts["P1"]!.isStale)
        XCTAssertEqual(model.drafts["P1"]!.baseRevision, "r1")  // not adopted

        model.drafts["P1"]!.isStale = false
        model.rebase(stem: "P1", before: "r1", after: "r2")
        XCTAssertFalse(model.drafts["P1"]!.isStale)
        XCTAssertEqual(model.drafts["P1"]!.baseRevision, "r2")
    }

    /// `before` ≠ the draft's key: something moved the photo between the draft
    /// and our own command → stale, never a silent rebase.
    func testAdjustWithUnmatchedBeforeMarksDraftStale() async {
        let fake = FakeClient()
        fake.statusQueue = [snap([photo(stem: "P1", revision: "r1")]),
                            snap([photo(stem: "P1", revision: "r2")])]
        fake.mutateHandler = { _ in
            Envelope(ok: true, result: AdjustResult(
                stem: "P1", style: "natural", preview: "p.jpg",
                temperature: Control(value: 5600, source: "sidecar"),
                exposure: Control(value: nil, source: "camera"),
                reviewRevisionBefore: "rX", reviewRevisionAfter: "r2"),
                error: nil)
        }
        let model = AppModel(client: fake, repo: URL(fileURLWithPath: "/r"),
                             sliderDebounce: .zero)
        await model.refresh()
        model.startDraft(stem: "P1")
        await model.applyAdjust(stem: "P1", style: "natural",
                                temperature: 5600, exposure: nil)
        XCTAssertTrue(model.drafts["P1"]!.isStale)
    }

    /// `before` matched but the refreshed state is NOT `after` — an external
    /// edit hid behind our own command. The AND-half of the rule.
    func testRebasedDraftStalesWhenRefreshedStateIsNotAfter() async {
        let fake = FakeClient()
        fake.statusQueue = [snap([photo(stem: "P1", revision: "r1")]),
                            snap([photo(stem: "P1", revision: "r3")])]
        fake.mutateHandler = { _ in
            Envelope(ok: true, result: AdjustResult(
                stem: "P1", style: "natural", preview: "p.jpg",
                temperature: Control(value: 5600, source: "sidecar"),
                exposure: Control(value: nil, source: "camera"),
                reviewRevisionBefore: "r1", reviewRevisionAfter: "r2"),
                error: nil)
        }
        let model = AppModel(client: fake, repo: URL(fileURLWithPath: "/r"),
                             sliderDebounce: .zero)
        await model.refresh()
        model.startDraft(stem: "P1")
        await model.applyAdjust(stem: "P1", style: "natural",
                                temperature: 5600, exposure: nil)
        XCTAssertTrue(model.drafts["P1"]!.isStale)
    }

    /// Staleness evaluation is deferred while the stem's own command runs, and
    /// happens once at the terminal refresh (spec §6.1).
    func testReconcileIsDeferredWhileTheStemsOwnCommandRuns() async {
        let fake = FakeClient()
        fake.statusQueue = [snap([photo(stem: "P1", revision: "r1")]),
                            snap([photo(stem: "P1", revision: "r2")]),
                            snap([photo(stem: "P1", revision: "r2")])]
        let model = AppModel(client: fake, repo: URL(fileURLWithPath: "/r"),
                             sliderDebounce: .zero)
        await model.refresh()
        model.startDraft(stem: "P1")

        model.activeCommand = "adjust"
        model.activeStem = "P1"
        await model.refresh()          // intermediate state — must not flap
        XCTAssertFalse(model.drafts["P1"]!.isStale)

        model.activeCommand = nil
        model.activeStem = nil
        await model.refresh()          // terminal refresh reconciles
        XCTAssertTrue(model.drafts["P1"]!.isStale)
    }

    /// The review-file is the only file this app writes: it goes to the system
    /// temp directory (never the repo) and is gone once the envelope is in.
    /// Crop nudges from the draft override the persisted windows.
    func testReviewFileLivesOutsideTheRepoIsDeletedAndCarriesNudges() async throws {
        let repo = URL(fileURLWithPath: "/r")
        let persisted = PhotoStatus(
            stem: "P1", state: "review_required", deliveryId: "d1",
            ingestedAt: "2026-08-12T00:00:00Z", reviewRevision: "r1",
            previews: [:], previewHashes: [:], stalePreviews: [],
            adjustments: [:],
            crops: ["8x10": CropWindow(x: 0.09, y: 0.02, w: 0.75, h: 0.96,
                                       source: "persisted")],
            expressionAudit: [],
            published: PublishedInfo(version: nil, path: nil,
                                     artifactCount: nil))
        let fake = FakeClient()
        fake.statusQueue = [snap([persisted]), snap([persisted])]
        nonisolated(unsafe) var reviewFilePath: String?
        nonisolated(unsafe) var body: [String: Any]?
        fake.mutateHandler = { args in
            if args.first == "approve" {
                let i = args.firstIndex(of: "--review-file")!
                reviewFilePath = args[i + 1]
                if let data = FileManager.default.contents(atPath: args[i + 1]) {
                    body = try? JSONSerialization.jsonObject(
                        with: data) as? [String: Any]
                }
                return Envelope(ok: true, result: ApproveResult(
                    stem: "P1", state: "approved", fingerprint: "f"),
                    error: nil) as Any
            }
            return Envelope(ok: true, result: RunResult(
                published: [], advanced: [], failed: []), error: nil) as Any
        }
        let model = AppModel(client: fake, repo: repo, sliderDebounce: .zero)
        await model.refresh()
        model.startDraft(stem: "P1")
        for key in ["eyes_open", "expressions_natural", "no_blinks_in_crops"] {
            model.drafts["P1"]!.checks[key] = true
        }
        model.drafts["P1"]!.cropNudges["8x10"] = CropWindow(
            x: 0.20, y: 0.02, w: 0.75, h: 0.96, source: "persisted")
        model.drafts["P1"]!.note = "dad mid-laugh"
        await model.approve(stem: "P1")

        let path = try XCTUnwrap(reviewFilePath)
        XCTAssertTrue(path.hasPrefix(FileManager.default.temporaryDirectory.path))
        XCTAssertFalse(path.hasPrefix(repo.path))
        XCTAssertFalse(FileManager.default.fileExists(atPath: path))

        let crops = try XCTUnwrap(body?["crops"] as? [String: [String: Double]])
        XCTAssertEqual(crops["8x10"]?["x"], 0.20)          // nudge wins
        XCTAssertNil(crops["8x10"]?["source"])             // dropped
        let audit = try XCTUnwrap(body?["expression_audit"] as? [String])
        XCTAssertEqual(audit.last, "note: dad mid-laugh")
    }

    /// The refresh gate (spec §7): concurrent refreshes collapse to one active
    /// `status` plus exactly one trailing one — user interaction and watcher
    /// bursts can never fan out into unbounded concurrent subprocesses.
    func testConcurrentRefreshesCollapseToOneActiveAndOneTrailing() async {
        let fake = SlowStatusClient(delay: .milliseconds(80))
        let model = AppModel(client: fake, repo: URL(fileURLWithPath: "/r"),
                             sliderDebounce: .zero)
        async let a: Void = model.refresh()
        async let b: Void = model.refresh()
        async let c: Void = model.refresh()
        async let d: Void = model.refresh()
        async let e: Void = model.refresh()
        _ = await (a, b, c, d, e)
        XCTAssertEqual(fake.callCount, 2)
        XCTAssertEqual(fake.maxConcurrent, 1)
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
