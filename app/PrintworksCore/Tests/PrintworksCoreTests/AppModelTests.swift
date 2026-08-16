import XCTest
@testable import PrintworksCore

/// Scriptable fake: every call pops the next canned envelope.
/// (Envelopes are wrapped in CommandResult with an empty stderrTail.)
final class FakeClient: PipelineRunning, @unchecked Sendable {
    private let stateLock = NSLock()
    private var storedMutateLog: [[String]] = []
    private var storedStatusQueue: [Envelope<StatusSnapshot>] = []
    private var storedStatusCalls = 0
    private var storedCropsQueue: [CommandResult<CropsResult>] = []
    private var storedCropsLog: [String] = []
    private var activeCrops = 0
    private var peakCrops = 0

    var statusQueue: [Envelope<StatusSnapshot>] {
        get { stateLock.withLock { storedStatusQueue } }
        set { stateLock.withLock { storedStatusQueue = newValue } }
    }
    var statusCalls: Int {
        stateLock.withLock { storedStatusCalls }
    }
    var mutateLog: [[String]] {
        stateLock.withLock { storedMutateLog }
    }
    var cropsQueue: [CommandResult<CropsResult>] {
        get { stateLock.withLock { storedCropsQueue } }
        set { stateLock.withLock { storedCropsQueue = newValue } }
    }
    var cropsLog: [String] {
        stateLock.withLock { storedCropsLog }
    }
    var maxConcurrentCrops: Int {
        stateLock.withLock { peakCrops }
    }
    var mutateHandler: ((_ args: [String]) -> Any)!
    var asyncMutateHandler: ((_ args: [String]) async -> Any)?
    var asyncCropsHandler: ((_ stem: String) async
                            -> CommandResult<CropsResult>)?

    func status() async -> CommandResult<StatusSnapshot> {
        let envelope = stateLock.withLock {
            storedStatusCalls += 1
            return storedStatusQueue.removeFirst()
        }
        return CommandResult(envelope: envelope, stderrTail: "")
    }
    func crops(stem: String) async -> CommandResult<CropsResult> {
        let queued = stateLock.withLock { () -> CommandResult<CropsResult>? in
            storedCropsLog.append(stem)
            activeCrops += 1
            peakCrops = max(peakCrops, activeCrops)
            return storedCropsQueue.isEmpty
                ? nil : storedCropsQueue.removeFirst()
        }
        let response: CommandResult<CropsResult>
        if let asyncCropsHandler {
            response = await asyncCropsHandler(stem)
        } else if let queued {
            response = queued
        } else {
            response = CommandResult(envelope: Envelope(
                ok: true,
                result: CropsResult(stem: stem, basis: "faces", windows: [:]),
                error: nil), stderrTail: "")
        }
        stateLock.withLock { activeCrops -= 1 }
        return response
    }
    func mutate<R>(_ type: R.Type, args: [String],
                   onEvent: (@Sendable (ProgressEvent) -> Void)?) async
    -> CommandResult<R> {
        stateLock.withLock { storedMutateLog.append(args) }
        let response = if let asyncMutateHandler {
            await asyncMutateHandler(args)
        } else {
            mutateHandler(args) as Any
        }
        return CommandResult(envelope: response as! Envelope<R>,
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

actor AsyncGate {
    private var isOpen = false
    private var waiters: [CheckedContinuation<Void, Never>] = []

    func wait() async {
        if isOpen { return }
        await withCheckedContinuation { continuation in
            waiters.append(continuation)
        }
    }

    func open() {
        isOpen = true
        let pending = waiters
        waiters.removeAll()
        for waiter in pending { waiter.resume() }
    }
}

/// Holds an adjust and a watcher refresh independently, so a test can prove
/// what a refresh reconciles when its `status` returns only after the command
/// ended — whether it was dispatched during that command or before it began.
final class DeferredReconcileClient: PipelineRunning, @unchecked Sendable {
    private let lock = NSLock()
    private var statusCallCount = 0
    private let initial: Envelope<StatusSnapshot>
    private let heldStatus: Envelope<StatusSnapshot>
    private let terminal: Envelope<StatusSnapshot>

    let mutationStarted = AsyncGate()
    let mutationCanFinish = AsyncGate()
    let capturedStatusStarted = AsyncGate()
    let capturedStatusCanFinish = AsyncGate()

    init(initial: Envelope<StatusSnapshot>,
         heldStatus: Envelope<StatusSnapshot>,
         terminal: Envelope<StatusSnapshot>) {
        self.initial = initial
        self.heldStatus = heldStatus
        self.terminal = terminal
    }

    func status() async -> CommandResult<StatusSnapshot> {
        let call = lock.withLock {
            statusCallCount += 1
            return statusCallCount
        }
        let envelope: Envelope<StatusSnapshot>
        switch call {
        case 1:
            envelope = initial
        case 2:
            await capturedStatusStarted.open()
            await capturedStatusCanFinish.wait()
            envelope = heldStatus
        default:
            envelope = terminal
        }
        return CommandResult(envelope: envelope, stderrTail: "")
    }

    func crops(stem: String) async -> CommandResult<CropsResult> {
        CommandResult(envelope: Envelope(ok: true, result: CropsResult(
            stem: stem, basis: nil, windows: [:]), error: nil), stderrTail: "")
    }

    func mutate<R>(_ type: R.Type, args: [String],
                   onEvent: (@Sendable (ProgressEvent) -> Void)?) async
    -> CommandResult<R> {
        await mutationStarted.open()
        await mutationCanFinish.wait()
        let result = AdjustResult(
            stem: "P1", style: "natural", preview: "p.jpg",
            temperature: Control(value: 5600, source: "sidecar"),
            exposure: Control(value: nil, source: "camera"),
            reviewRevisionBefore: "r1", reviewRevisionAfter: "r2")
        return CommandResult(envelope: Envelope(ok: true, result: result,
                                                error: nil) as! Envelope<R>,
                             stderrTail: "")
    }
}

@MainActor
final class AppModelTests: XCTestCase {
    private func photo(stem: String, revision: String,
                       state: String = "review_required",
                       stale: [String] = [],
                       version: String? = nil) -> PhotoStatus {
        PhotoStatus(stem: stem, state: state, deliveryId: "d1",
                    ingestedAt: "2026-08-12T00:00:00Z",
                    reviewRevision: revision, previews: [:], previewHashes: [:],
                    stalePreviews: stale, adjustments: [:], crops: [:],
                    expressionAudit: [], published: PublishedInfo(
                        version: version, path: nil, artifactCount: nil))
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

    func testRerenderPreviewSendsExactArgsAndRefreshes() async {
        let fake = FakeClient()
        fake.statusQueue = [snap([photo(stem: "P1", revision: "r2")])]
        fake.mutateHandler = { _ in
            Envelope(ok: true, result: AdjustResult(
                stem: "P1", style: "filmic", preview: "p.jpg",
                temperature: Control(value: nil, source: "camera"),
                exposure: Control(value: nil, source: "camera"),
                reviewRevisionBefore: "r1", reviewRevisionAfter: "r2"),
                error: nil)
        }
        let model = AppModel(client: fake, repo: URL(fileURLWithPath: "/r"),
                             sliderDebounce: .zero)

        await model.rerenderPreview(stem: "P1", style: "filmic")

        XCTAssertEqual(fake.mutateLog, [[
            "preview", "--stem", "P1", "--style", "filmic", "--json",
        ]])
        XCTAssertEqual(fake.statusCalls, 1)
    }

    func testRerenderPreviewUsesSharedRebaseForBothPairBranches() async {
        let matching = FakeClient()
        matching.statusQueue = [
            snap([photo(stem: "P1", revision: "r1")]),
            snap([photo(stem: "P1", revision: "r2")]),
        ]
        matching.mutateHandler = { _ in
            Envelope(ok: true, result: AdjustResult(
                stem: "P1", style: "filmic", preview: "p.jpg",
                temperature: Control(value: nil, source: "camera"),
                exposure: Control(value: nil, source: "camera"),
                reviewRevisionBefore: "r1", reviewRevisionAfter: "r2"),
                error: nil)
        }
        let matchingModel = AppModel(
            client: matching, repo: URL(fileURLWithPath: "/r"),
            sliderDebounce: .zero)
        await matchingModel.refresh()
        matchingModel.startDraft(stem: "P1")

        await matchingModel.rerenderPreview(stem: "P1", style: "filmic")

        XCTAssertFalse(matchingModel.drafts["P1"]!.isStale)
        XCTAssertEqual(matchingModel.drafts["P1"]!.baseRevision, "r2")

        let nonmatching = FakeClient()
        // Keep the terminal snapshot at the draft's old revision so only the
        // shared rebase path can mark the non-matching pair stale.
        nonmatching.statusQueue = [
            snap([photo(stem: "P1", revision: "r1")]),
            snap([photo(stem: "P1", revision: "r1")]),
        ]
        nonmatching.mutateHandler = { _ in
            Envelope(ok: true, result: AdjustResult(
                stem: "P1", style: "filmic", preview: "p.jpg",
                temperature: Control(value: nil, source: "camera"),
                exposure: Control(value: nil, source: "camera"),
                reviewRevisionBefore: "rX", reviewRevisionAfter: "r2"),
                error: nil)
        }
        let nonmatchingModel = AppModel(
            client: nonmatching, repo: URL(fileURLWithPath: "/r"),
            sliderDebounce: .zero)
        await nonmatchingModel.refresh()
        nonmatchingModel.startDraft(stem: "P1")

        await nonmatchingModel.rerenderPreview(stem: "P1", style: "filmic")

        XCTAssertTrue(nonmatchingModel.drafts["P1"]!.isStale)
        XCTAssertEqual(nonmatchingModel.drafts["P1"]!.baseRevision, "r1")
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

    func testVerifiedPhotoCannotBeApproved() async {
        let fake = FakeClient()
        fake.statusQueue = [snap([photo(
            stem: "P1", revision: "r1", state: "verified", version: "v001")])]
        let model = AppModel(
            client: fake, repo: URL(fileURLWithPath: "/r"),
            sliderDebounce: .zero)
        await model.refresh()
        model.startDraft(stem: "P1")
        for key in ReviewDraft.checkKeys {
            model.setDraftCheck(stem: "P1", key: key, isChecked: true)
        }

        XCTAssertFalse(model.canApprove(stem: "P1"))
    }

    func testReprocessAllConfirmationNamesPhotoCount() async {
        let fake = FakeClient()
        fake.statusQueue = [snap([
            photo(stem: "P1", revision: "r1"),
            photo(stem: "P2", revision: "r1"),
            photo(stem: "P3", revision: "r1"),
        ])]
        let model = AppModel(
            client: fake, repo: URL(fileURLWithPath: "/r"),
            sliderDebounce: .zero)
        await model.refresh()

        XCTAssertEqual(model.reprocessAllConfirmation.title,
                       "Reprocess all 3 photos?")
        XCTAssertEqual(
            model.reprocessAllConfirmation.message,
            "This re-renders every photo and publishes a new version of each.")
    }

    func testDropIsRefusedWhileMutationOrExternalLockIsActive() async {
        let fake = FakeClient()
        let model = AppModel(
            client: fake, repo: URL(fileURLWithPath: "/r"),
            sliderDebounce: .zero)

        model.activeCommand = "run"
        XCTAssertFalse(model.ingestDropped(paths: ["/incoming/P1.rw2"]))

        model.activeCommand = nil
        model.busyExternally = true
        XCTAssertFalse(model.ingestDropped(paths: ["/incoming/P2.rw2"]))
        XCTAssertTrue(fake.mutateLog.isEmpty)
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

    func testProgressStageKeepsLastDeterminateFraction() {
        let landed = ProgressEvent(event: "progress", stem: "P1", stage: nil,
                                   index: 29, total: 29, detail: nil)
        let verify = ProgressEvent(event: "stage", stem: "P1", stage: "verify",
                                   index: nil, total: nil, detail: nil)

        XCTAssertEqual(AppModel.progressEventPreservingFraction(
            current: landed, incoming: verify), landed)
        XCTAssertEqual(AppModel.progressEventPreservingFraction(
            current: nil, incoming: verify), verify)
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

    func testSetSliderSendsOnlyChangedTemperatureControl() async {
        let fake = FakeClient()
        fake.statusQueue = [snap([])]
        fake.mutateHandler = { _ in
            Envelope(ok: true, result: AdjustResult(
                stem: "P1", style: "natural", preview: "p.jpg",
                temperature: Control(value: 5600, source: "sidecar"),
                exposure: Control(value: nil, source: "camera"),
                reviewRevisionBefore: "r1", reviewRevisionAfter: "r2"),
                error: nil)
        }
        let model = AppModel(client: fake, repo: URL(fileURLWithPath: "/r"),
                             sliderDebounce: .seconds(60))

        model.setSlider(stem: "P1", style: "natural", temperature: 5600,
                        exposure: nil)
        await model.flushPendingAdjustments(stem: "P1")

        XCTAssertEqual(fake.mutateLog, [[
            "adjust", "--stem", "P1", "--style", "natural",
            "--temperature", "5600", "--json",
        ]])
    }

    func testSetSliderSendsExposureWithTwoDecimalPlaces() async {
        let fake = FakeClient()
        fake.statusQueue = [snap([])]
        fake.mutateHandler = { _ in
            Envelope(ok: true, result: AdjustResult(
                stem: "P1", style: "natural", preview: "p.jpg",
                temperature: Control(value: nil, source: "camera"),
                exposure: Control(value: 0.35, source: "sidecar"),
                reviewRevisionBefore: "r1", reviewRevisionAfter: "r2"),
                error: nil)
        }
        let model = AppModel(client: fake, repo: URL(fileURLWithPath: "/r"),
                             sliderDebounce: .seconds(60))

        model.setSlider(stem: "P1", style: "natural", temperature: nil,
                        exposure: 0.35)
        await model.flushPendingAdjustments(stem: "P1")

        XCTAssertEqual(fake.mutateLog, [[
            "adjust", "--stem", "P1", "--style", "natural",
            "--exposure", "0.35", "--json",
        ]])
    }

    func testSetSliderComposesBothTouchedControlsInOneCommand() async {
        let fake = FakeClient()
        fake.statusQueue = [snap([])]
        fake.mutateHandler = { _ in
            Envelope(ok: true, result: AdjustResult(
                stem: "P1", style: "natural", preview: "p.jpg",
                temperature: Control(value: 5650, source: "sidecar"),
                exposure: Control(value: -0.40, source: "sidecar"),
                reviewRevisionBefore: "r1", reviewRevisionAfter: "r2"),
                error: nil)
        }
        let model = AppModel(client: fake, repo: URL(fileURLWithPath: "/r"),
                             sliderDebounce: .seconds(60))

        model.setSlider(stem: "P1", style: "natural", temperature: 5650,
                        exposure: nil)
        model.setSlider(stem: "P1", style: "natural", temperature: nil,
                        exposure: -0.40)
        await model.flushPendingAdjustments(stem: "P1")

        XCTAssertEqual(fake.mutateLog, [[
            "adjust", "--stem", "P1", "--style", "natural",
            "--temperature", "5650", "--exposure", "-0.40", "--json",
        ]])
    }

    func testResetAdjustSendsResetFlag() async {
        let fake = FakeClient()
        fake.statusQueue = [snap([])]
        fake.mutateHandler = { _ in
            Envelope(ok: true, result: AdjustResult(
                stem: "P1", style: "natural", preview: "p.jpg",
                temperature: Control(value: nil, source: "camera"),
                exposure: Control(value: nil, source: "camera"),
                reviewRevisionBefore: "r1", reviewRevisionAfter: "r2"),
                error: nil)
        }
        let model = AppModel(client: fake, repo: URL(fileURLWithPath: "/r"),
                             sliderDebounce: .zero)

        await model.resetAdjust(stem: "P1", style: "natural")

        XCTAssertEqual(fake.mutateLog, [[
            "adjust", "--stem", "P1", "--style", "natural", "--reset",
            "--json",
        ]])
    }

    func testCropsUsesCanonicalArgsAndCachesUntilRevisionChanges() async throws {
        let directory = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(
            at: directory, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: directory) }

        let script = directory.appendingPathComponent("crops-stub.sh")
        try """
        #!/bin/sh
        printf '%s\\n' "$*" >> "$PWD/args.log"
        case "$1" in
          status)
            if [ -f "$PWD/status-seen" ]; then
              REV=r2
            else
              REV=r1
              : > "$PWD/status-seen"
            fi
            printf '%s\\n' '{"ok":true,"result":{"repo":"/r","toolchain":{"ok":true,"failures":[]},"lock":{"held":false,"stale":false,"pid":null},"styles":["natural"],"photos":[{"stem":"P1","state":"review_required","delivery_id":"d1","ingested_at":null,"review_revision":"'"$REV"'","previews":{},"preview_hashes":{},"stale_previews":[],"adjustments":{},"crops":{},"expression_audit":[],"published":{"version":null,"path":null,"artifact_count":null}}]}}'
            ;;
          crops)
            if [ -f "$PWD/crops-seen" ]; then
              BASIS=center
            else
              BASIS=faces
              : > "$PWD/crops-seen"
            fi
            printf '%s\\n' '{"ok":true,"result":{"stem":"P1","basis":"'"$BASIS"'","windows":{}}}'
            ;;
        esac
        """.write(to: script, atomically: true, encoding: .utf8)
        try FileManager.default.setAttributes([.posixPermissions: 0o755],
                                              ofItemAtPath: script.path)
        let client = PipelineClient(
            config: PipelineConfig(repo: directory, python: script),
            executableOverride: script)
        let model = AppModel(client: client, repo: directory,
                             sliderDebounce: .zero)

        await model.refresh()
        let first = await model.crops(stem: "P1")
        let cached = await model.crops(stem: "P1")
        await model.refresh()
        let refreshed = await model.crops(stem: "P1")

        XCTAssertEqual(first?.basis, "faces")
        XCTAssertEqual(cached?.basis, "faces")
        XCTAssertEqual(refreshed?.basis, "center")
        let cropInvocations = try String(
            contentsOf: directory.appendingPathComponent("args.log"),
            encoding: .utf8
        ).split(separator: "\n").map(String.init).filter {
            $0.hasPrefix("crops ")
        }
        XCTAssertEqual(cropInvocations, [
            "crops --stem P1 --json",
            "crops --stem P1 --json",
        ])
    }

    func testCropsCachesMissingRenderDimensionsWithoutShowingBanner() async {
        let fake = FakeClient()
        fake.statusQueue = [snap([photo(stem: "P1", revision: "r1")])]
        fake.cropsQueue = [CommandResult(
            envelope: Envelope(
                ok: false, result: nil,
                error: PipelineErrorInfo(
                    code: "BAD_INPUT",
                    message: "render dims not recorded; generate previews first")),
            stderrTail: "")]
        let model = AppModel(client: fake, repo: URL(fileURLWithPath: "/r"),
                             sliderDebounce: .zero)
        await model.refresh()

        let first = await model.crops(stem: "P1")
        let cached = await model.crops(stem: "P1")

        XCTAssertNil(first)
        XCTAssertNil(cached)
        XCTAssertNil(model.banner)
        XCTAssertEqual(fake.cropsLog, ["P1"])
    }

    func testCancelledCropsLoadDoesNotRetryAfterRevisionChanges() async {
        let fake = FakeClient()
        fake.statusQueue = [snap([photo(stem: "P1", revision: "r1")]),
                            snap([photo(stem: "P1", revision: "r2")])]
        let requestStarted = AsyncGate()
        let requestCanFinish = AsyncGate()
        fake.asyncCropsHandler = { stem in
            await requestStarted.open()
            await requestCanFinish.wait()
            return CommandResult(envelope: Envelope(
                ok: true,
                result: CropsResult(stem: stem, basis: "faces", windows: [:]),
                error: nil), stderrTail: "")
        }
        let model = AppModel(client: fake, repo: URL(fileURLWithPath: "/r"),
                             sliderDebounce: .zero)
        await model.refresh()

        let load = Task { @MainActor in await model.crops(stem: "P1") }
        await requestStarted.wait()
        await model.refresh()
        load.cancel()
        await requestCanFinish.open()

        let result = await load.value
        XCTAssertNil(result)
        XCTAssertEqual(fake.cropsLog, ["P1"])
    }

    func testCropsCacheEvictsLeastRecentlyUsedEntryAtForty() async {
        let fake = FakeClient()
        let photos = (0...40).map {
            photo(stem: "P\($0)", revision: "r1")
        }
        fake.statusQueue = [snap(photos)]
        let model = AppModel(client: fake, repo: URL(fileURLWithPath: "/r"),
                             sliderDebounce: .zero)
        await model.refresh()

        for photo in photos.prefix(40) {
            _ = await model.crops(stem: photo.stem)
        }
        _ = await model.crops(stem: "P0")
        XCTAssertEqual(fake.cropsLog.count, 40, "P0 must be a cache hit")
        _ = await model.crops(stem: "P40")
        _ = await model.crops(stem: "P0")
        _ = await model.crops(stem: "P1")

        XCTAssertEqual(fake.cropsLog.count, 42)
        XCTAssertEqual(fake.cropsLog.suffix(2), ["P40", "P1"])
    }

    func testCropsRequestsAllowAtMostEightConcurrentQueries() async {
        let fake = FakeClient()
        let photos = (0..<9).map {
            photo(stem: "P\($0)", revision: "r1")
        }
        fake.statusQueue = [snap(photos)]
        let firstEightStarted = AsyncGate()
        let requestsCanFinish = AsyncGate()
        let startLock = NSLock()
        nonisolated(unsafe) var started = 0
        fake.asyncCropsHandler = { stem in
            let reachedLimit = startLock.withLock {
                started += 1
                return started == 8
            }
            if reachedLimit { await firstEightStarted.open() }
            await requestsCanFinish.wait()
            return CommandResult(envelope: Envelope(
                ok: true,
                result: CropsResult(stem: stem, basis: "faces", windows: [:]),
                error: nil), stderrTail: "")
        }
        let model = AppModel(client: fake, repo: URL(fileURLWithPath: "/r"),
                             sliderDebounce: .zero)
        await model.refresh()

        let firstLoads = photos.prefix(8).map { photo in
            Task { @MainActor in await model.crops(stem: photo.stem) }
        }
        await firstEightStarted.wait()
        let ninthLoad = Task { @MainActor in
            await model.crops(stem: photos[8].stem)
        }
        await Task { @MainActor in }.value

        XCTAssertEqual(fake.cropsLog.count, 8)
        XCTAssertEqual(fake.maxConcurrentCrops, 8)

        await requestsCanFinish.open()
        for load in firstLoads { _ = await load.value }
        _ = await ninthLoad.value
        XCTAssertEqual(fake.cropsLog.count, 9)
        XCTAssertEqual(fake.maxConcurrentCrops, 8)
    }

    func testCropsStayAtEightAcrossRevisionChurn() async {
        let fake = FakeClient()
        let stems = (0..<8).map { "P\($0)" }
        fake.statusQueue = (1...4).map { revision in
            snap(stems.map { photo(stem: $0, revision: "r\(revision)") })
        }
        let waveStarted = (0..<4).map {
            XCTestExpectation(description: "crop wave \($0 + 1) started")
        }
        let stateLock = NSLock()
        nonisolated(unsafe) var callCount = 0
        nonisolated(unsafe) var shouldFinish = false
        defer { stateLock.withLock { shouldFinish = true } }
        fake.asyncCropsHandler = { stem in
            let call = stateLock.withLock {
                callCount += 1
                return callCount
            }
            if call.isMultiple(of: 8) {
                waveStarted[(call / 8) - 1].fulfill()
            }
            while !Task.isCancelled && stateLock.withLock({ !shouldFinish }) {
                try? await Task.sleep(for: .milliseconds(5))
            }
            return CommandResult(envelope: Envelope(
                ok: true,
                result: CropsResult(stem: stem, basis: "faces", windows: [:]),
                error: nil), stderrTail: "")
        }
        let model = AppModel(client: fake, repo: URL(fileURLWithPath: "/r"),
                             sliderDebounce: .zero)
        var loads: [Task<CropsResult?, Never>] = []

        for wave in 0..<4 {
            await model.refresh()
            loads += stems.map { stem in
                Task { @MainActor in await model.crops(stem: stem) }
            }
            await fulfillment(of: [waveStarted[wave]], timeout: 5)
            let expectedCalls = (wave + 1) * stems.count
            guard stateLock.withLock({ callCount }) >= expectedCalls else {
                break
            }
        }

        let observedCalls = fake.cropsLog.count
        let observedPeak = fake.maxConcurrentCrops
        stateLock.withLock { shouldFinish = true }
        for load in loads { _ = await load.value }

        XCTAssertEqual(observedCalls, 32)
        XCTAssertEqual(observedPeak, 8,
                       "revision churn must not orphan running crop queries")
    }

    func testDebouncersAreKeyedPerStemAndStyle() async {
        let fake = FakeClient()
        fake.statusQueue = Array(repeating: snap([photo(stem: "P1", revision: "r1"),
                                                  photo(stem: "P2", revision: "r1")]),
                                 count: 6)
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
        // Three different (stem, style) pairs scheduled back-to-back: all fire,
        // including both styles belonging to the stem flushed first.
        model.setSlider(stem: "P1", style: "natural", temperature: 5600,
                        exposure: nil)
        model.setSlider(stem: "P1", style: "filmic", temperature: 5500,
                        exposure: nil)
        model.setSlider(stem: "P2", style: "bw", temperature: 5400,
                        exposure: nil)
        await model.flushPendingAdjustments(stem: "P1")
        await model.flushPendingAdjustments(stem: "P2")
        let adjustTargets = fake.mutateLog.filter { $0.first == "adjust" }
            .map { "\($0[$0.firstIndex(of: "--stem")! + 1])|\($0[$0.firstIndex(of: "--style")! + 1])" }
        XCTAssertEqual(Set(adjustTargets),
                       ["P1|natural", "P1|filmic", "P2|bw"])
    }

    /// Approve can arrive after the debounce timer has removed its pending
    /// value but while the resulting adjust is still running. It must await
    /// that task and serialize the rebased revision into the review file.
    func testApproveWaitsForDebouncedAdjustAlreadyInFlight() async throws {
        let fake = FakeClient()
        fake.statusQueue = Array(repeating:
            snap([photo(stem: "P1", revision: "r2")]), count: 4)
        fake.statusQueue[0] = snap([photo(stem: "P1", revision: "r1")])

        let adjustStarted = AsyncGate()
        let adjustCanFinish = AsyncGate()
        let adjustFinished = AsyncGate()
        nonisolated(unsafe) var reviewRevision: String?
        fake.asyncMutateHandler = { args in
            switch args.first {
            case "adjust":
                await adjustStarted.open()
                await adjustCanFinish.wait()
                await adjustFinished.open()
                return Envelope(ok: true, result: AdjustResult(
                    stem: "P1", style: "natural", preview: "p.jpg",
                    temperature: Control(value: 5600, source: "sidecar"),
                    exposure: Control(value: nil, source: "camera"),
                    reviewRevisionBefore: "r1", reviewRevisionAfter: "r2"),
                    error: nil) as Any
            case "approve":
                // Model PipelineClient's FIFO: the invocation may be queued,
                // but the already-written review file exposes which revision
                // approve read before entering that queue.
                await adjustFinished.wait()
                let index = args.firstIndex(of: "--review-file")!
                let data = FileManager.default.contents(atPath: args[index + 1])!
                let body = try! JSONSerialization.jsonObject(with: data)
                    as! [String: Any]
                reviewRevision = body["expected_review_revision"] as? String
                return Envelope(ok: true, result: ApproveResult(
                    stem: "P1", state: "approved", fingerprint: "f"),
                    error: nil) as Any
            default:
                return Envelope(ok: true, result: RunResult(
                    published: [], advanced: [], failed: []), error: nil) as Any
            }
        }

        let model = AppModel(client: fake, repo: URL(fileURLWithPath: "/r"),
                             sliderDebounce: .zero)
        await model.refresh()
        model.startDraft(stem: "P1")
        model.setSlider(stem: "P1", style: "natural", temperature: 5600,
                        exposure: nil)
        await adjustStarted.wait()

        Task {
            try? await Task.sleep(for: .milliseconds(50))
            await adjustCanFinish.open()
        }
        await model.approve(stem: "P1")

        XCTAssertEqual(reviewRevision, "r2")
        XCTAssertEqual(model.drafts["P1"]?.baseRevision, "r2")
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

    /// A watcher status dispatched while this stem's own command is active can
    /// return after the command clears its flags. Its intermediate snapshot is
    /// still deferred; only the queued terminal refresh may reconcile.
    func testReconcileIsDeferredWhileTheStemsOwnCommandRuns() async {
        let fake = DeferredReconcileClient(
            initial: snap([photo(stem: "P1", revision: "r1")]),
            heldStatus: snap([photo(stem: "P1", revision: "r1")]),
            terminal: snap([photo(stem: "P1", revision: "r2")]))
        let model = AppModel(client: fake, repo: URL(fileURLWithPath: "/r"),
                             sliderDebounce: .zero)
        await model.refresh()
        model.startDraft(stem: "P1")

        let adjust = Task { @MainActor in
            await model.applyAdjust(stem: "P1", style: "natural",
                                    temperature: 5600, exposure: nil)
        }
        await fake.mutationStarted.wait()

        let watcherRefresh = Task { @MainActor in await model.refresh() }
        await fake.capturedStatusStarted.wait()

        await fake.mutationCanFinish.open()
        await adjust.value
        XCTAssertNil(model.activeCommand) // captured status has not landed yet

        await fake.capturedStatusCanFinish.open()
        await watcherRefresh.value
        XCTAssertEqual(model.drafts["P1"]!.baseRevision, "r2")
        XCTAssertFalse(model.drafts["P1"]!.isStale)
    }

    /// The mirror of the case above: the watcher status is dispatched while the
    /// app is IDLE, and an adjust begins and rebases the draft before it lands.
    /// Its pre-command snapshot still shows the pre-adjust revision, which no
    /// longer equals the rebased draft — reconciling it would mark the draft
    /// stale forever (reconcile only ever SETS `isStale`). A command having run
    /// between dispatch and landing must therefore skip reconciliation too;
    /// the queued trailing refresh is the one that judges this draft.
    func testReconcileIsSkippedWhenACommandRanBetweenDispatchAndLanding() async {
        let fake = DeferredReconcileClient(
            initial: snap([photo(stem: "P1", revision: "r1")]),
            heldStatus: snap([photo(stem: "P1", revision: "r1")]),
            terminal: snap([photo(stem: "P1", revision: "r2")]))
        let model = AppModel(client: fake, repo: URL(fileURLWithPath: "/r"),
                             sliderDebounce: .zero)
        await model.refresh()
        model.startDraft(stem: "P1")

        // Dispatched with no command running — the ONLY difference from the
        // test above, and the whole point of the case.
        let watcherRefresh = Task { @MainActor in await model.refresh() }
        await fake.capturedStatusStarted.wait()
        XCTAssertNil(model.activeCommand)

        let adjust = Task { @MainActor in
            await model.applyAdjust(stem: "P1", style: "natural",
                                    temperature: 5600, exposure: nil)
        }
        await fake.mutationStarted.wait()
        await fake.mutationCanFinish.open()
        await adjust.value
        XCTAssertEqual(model.drafts["P1"]!.baseRevision, "r2") // rebased

        await fake.capturedStatusCanFinish.open()
        await watcherRefresh.value
        XCTAssertEqual(model.drafts["P1"]!.baseRevision, "r2")
        XCTAssertFalse(model.drafts["P1"]!.isStale)
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
                advanced: [AdvancedPhoto(stem: "P3", state: "preview_ready")],
                failed: [StemFailure(
                    stem: "P2", code: "VERIFY_FAILED", message: "bad")]),
                error: PipelineErrorInfo(code: "PARTIAL_FAILURE",
                                         message: "1 of 2 failed"))
        }
        var notified: [PublishedPhoto] = []
        let model = AppModel(
            client: fake, repo: URL(fileURLWithPath: "/r"),
            sliderDebounce: .zero,
            onPublished: { notified = $0 })
        await model.refresh()
        model.lastFailures["P3"] = StemFailure(
            stem: "P3", code: "RENDER_FAILED", message: "old")
        await model.reprocessAll()
        XCTAssertEqual(notified.map(\.stem), ["P1"])             // result first
        XCTAssertNil(model.lastFailures["P3"])
        XCTAssertEqual(model.lastFailures["P2"], StemFailure(
            stem: "P2", code: "VERIFY_FAILED", message: "bad"))
        XCTAssertEqual(model.banner?.code, "PARTIAL_FAILURE")    // then error
    }

    func testRunResultPublishesThroughNotificationHook() async {
        let fake = FakeClient()
        fake.statusQueue = [snap([])]
        fake.mutateHandler = { _ in
            Envelope(ok: true, result: RunResult(
                published: [PublishedPhoto(
                    stem: "P1", version: "v004", artifactCount: 29)],
                advanced: [], failed: []), error: nil)
        }
        var notified: [PublishedPhoto] = []
        let model = AppModel(
            client: fake, repo: URL(fileURLWithPath: "/r"),
            sliderDebounce: .zero,
            onPublished: { notified = $0 })

        await model.reprocess(stem: "P1")

        XCTAssertEqual(notified, [PublishedPhoto(
            stem: "P1", version: "v004", artifactCount: 29)])
    }

    /// `run --stem P1 --force` on a published photo: the render fails, the
    /// pipeline restores the manifest to `verified` (driver.py
    /// `_restore_forced`), so the terminal refresh sees `verified` and the
    /// filter must not delete the failure the same command just recorded.
    func testForceReprocessFailureOnVerifiedPhotoKeepsBadge() async {
        let verifiedPhoto = PhotoStatus(
            stem: "P1", state: "verified", deliveryId: "d1",
            ingestedAt: "2026-08-12T00:00:00Z", reviewRevision: "r1",
            previews: [:], previewHashes: [:], stalePreviews: [],
            adjustments: [:], crops: [:], expressionAudit: [],
            published: PublishedInfo(version: "v001", path: "p",
                                     artifactCount: 29))
        let fake = FakeClient()
        fake.statusQueue = [snap([verifiedPhoto])]
        fake.mutateHandler = { _ in
            Envelope(ok: false, result: RunResult(
                published: [], advanced: [], failed: [StemFailure(
                    stem: "P1", code: "RENDER_FAILED",
                    message: "rawtherapee exited 1")]),
                error: PipelineErrorInfo(code: "PARTIAL_FAILURE",
                                         message: "1 of 1 photos failed")) as Any
        }
        let model = AppModel(client: fake, repo: URL(fileURLWithPath: "/r"),
                             sliderDebounce: .zero)

        await model.reprocess(stem: "P1")

        XCTAssertEqual(fake.mutateLog.first,
                       ["run", "--stem", "P1", "--force", "--json"])
        XCTAssertNotNil(model.lastFailures["P1"],
                        "force-reprocess failure erased by the verified filter")
        XCTAssertNil(model.bannerAction,
                     "PARTIAL_FAILURE maps to no banner action")
    }

    func testRetrySuccessPreservesOtherStemFailures() async {
        let fake = FakeClient()
        fake.statusQueue = [
            snap([photo(stem: "P1", revision: "r1"),
                  photo(stem: "P2", revision: "r1")]),
            snap([photo(stem: "P1", revision: "r1", state: "verified"),
                  photo(stem: "P2", revision: "r1")]),
        ]
        var runCalls = 0
        fake.mutateHandler = { _ in
            runCalls += 1
            if runCalls == 1 {
                return Envelope(ok: false, result: RunResult(
                    published: [], advanced: [], failed: [
                        StemFailure(stem: "P1", code: "RENDER_FAILED",
                                    message: "bad one"),
                        StemFailure(stem: "P2", code: "RENDER_FAILED",
                                    message: "bad two"),
                    ]), error: PipelineErrorInfo(
                        code: "PARTIAL_FAILURE", message: "2 failed")) as Any
            }
            return Envelope(ok: true, result: RunResult(
                published: [PublishedPhoto(stem: "P1", version: "v001",
                                           artifactCount: 29)],
                advanced: [], failed: []), error: nil) as Any
        }
        let model = AppModel(client: fake, repo: URL(fileURLWithPath: "/r"),
                             sliderDebounce: .zero)

        await model.reprocessAll()
        XCTAssertNotNil(model.lastFailures["P1"])
        XCTAssertNotNil(model.lastFailures["P2"])

        await model.retryRender(stem: "P1")
        XCTAssertNil(model.lastFailures["P1"])
        XCTAssertEqual(model.lastFailures["P2"]?.message, "bad two")
    }

    func testRefreshClearsFailureWhenPublishedVersionChanges() async {
        let fake = FakeClient()
        fake.statusQueue = [
            snap([photo(stem: "P1", revision: "r1", state: "verified",
                        version: "v001")]),
            snap([photo(stem: "P1", revision: "r1", state: "verified",
                        version: "v001")]),
            snap([photo(stem: "P1", revision: "r1", state: "verified",
                        version: "v002")]),
        ]
        fake.mutateHandler = { _ in
            Envelope(ok: false, result: RunResult(
                published: [], advanced: [], failed: [StemFailure(
                    stem: "P1", code: "RENDER_FAILED", message: "bad")]),
                error: PipelineErrorInfo(code: "RENDER_FAILED",
                                         message: "render failed"))
        }
        let model = AppModel(client: fake, repo: URL(fileURLWithPath: "/r"),
                             sliderDebounce: .zero)

        await model.refresh()
        await model.reprocessAll()
        XCTAssertNotNil(model.lastFailures["P1"])

        await model.refresh()
        XCTAssertNil(model.lastFailures["P1"])
    }

    func testRefreshClearsFailureWhenReviewRevisionChanges() async {
        let fake = FakeClient()
        fake.statusQueue = [
            snap([photo(stem: "P1", revision: "r1")]),
            snap([photo(stem: "P1", revision: "r1")]),
            snap([photo(stem: "P1", revision: "r2")]),
        ]
        fake.mutateHandler = { _ in
            Envelope(ok: false, result: RunResult(
                published: [], advanced: [], failed: [StemFailure(
                    stem: "P1", code: "RENDER_FAILED", message: "bad")]),
                error: PipelineErrorInfo(code: "RENDER_FAILED",
                                         message: "render failed"))
        }
        let model = AppModel(client: fake, repo: URL(fileURLWithPath: "/r"),
                             sliderDebounce: .zero)

        await model.refresh()
        await model.reprocessAll()
        XCTAssertNotNil(model.lastFailures["P1"])

        await model.refresh()
        XCTAssertNil(model.lastFailures["P1"])
    }

    func testIngestStoresPerFileFailures() async {
        let fake = FakeClient()
        fake.statusQueue = [snap([])]
        fake.mutateHandler = { _ in
            Envelope(ok: false, result: IngestResult(
                ingested: [], skipped: [], conflicts: [], failed: [FileFailure(
                    file: "bad.rw2", code: "BAD_INPUT", message: "corrupt")]),
                error: PipelineErrorInfo(code: "PARTIAL_FAILURE",
                                         message: "1 file failed"))
        }
        let model = AppModel(client: fake, repo: URL(fileURLWithPath: "/r"),
                             sliderDebounce: .zero)

        await model.ingest(paths: ["/incoming/bad.rw2"])

        XCTAssertEqual(model.lastIngestFailures["bad.rw2"], FileFailure(
            file: "bad.rw2", code: "BAD_INPUT", message: "corrupt"))
        XCTAssertEqual(model.banner?.code, "PARTIAL_FAILURE")
    }

    func testPartialIngestBannerDetailsListFilenameAndReason() async {
        let fake = FakeClient()
        fake.statusQueue = [snap([])]
        fake.mutateHandler = { _ in
            Envelope(ok: false, result: IngestResult(
                ingested: [], skipped: [], conflicts: [], failed: [
                    FileFailure(file: "bad-a.rw2", code: "BAD_INPUT",
                                message: "corrupt header"),
                    FileFailure(file: "bad-b.rw2", code: "BAD_INPUT",
                                message: "unsupported compression"),
                ]), error: PipelineErrorInfo(
                    code: "PARTIAL_FAILURE", message: "2 files failed"))
        }
        let model = AppModel(
            client: fake, repo: URL(fileURLWithPath: "/r"),
            sliderDebounce: .zero)

        await model.ingest(paths: [
            "/incoming/bad-a.rw2", "/incoming/bad-b.rw2",
        ])

        XCTAssertEqual(
            model.bannerDetails,
            "bad-a.rw2: corrupt header\nbad-b.rw2: unsupported compression")
    }

    func testPendingInputFilesListsRawFilesMissingFromSnapshot() async throws {
        let repo = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
        let input = repo.appendingPathComponent("Input", isDirectory: true)
        try FileManager.default.createDirectory(
            at: input, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: repo) }
        for name in ["P1.RW2", "P2.rw2", "P3.Rw2", "notes.txt"] {
            try Data().write(to: input.appendingPathComponent(name))
        }

        let fake = FakeClient()
        fake.statusQueue = [snap([photo(stem: "P1", revision: "r1")])]
        let model = AppModel(client: fake, repo: repo, sliderDebounce: .zero)

        await model.refresh()

        XCTAssertEqual(model.pendingInputFiles, ["P2.rw2", "P3.Rw2"])
    }

    func testIngestPendingSendsDeliveryIDThenRuns() async {
        let fake = FakeClient()
        fake.statusQueue = [snap([])]
        fake.mutateHandler = { args in
            if args.first == "ingest" {
                return Envelope(ok: true, result: IngestResult(
                    ingested: ["P1"], skipped: [], conflicts: [], failed: []),
                    error: nil) as Any
            }
            return Envelope(ok: true, result: RunResult(
                published: [], advanced: [], failed: []), error: nil) as Any
        }
        let model = AppModel(client: fake, repo: URL(fileURLWithPath: "/r"),
                             sliderDebounce: .zero)

        await model.ingestPending()

        XCTAssertEqual(fake.mutateLog.count, 2)
        let ingestArgs = fake.mutateLog[0]
        XCTAssertEqual(ingestArgs.count, 4)
        XCTAssertEqual(ingestArgs[0...1], ["ingest", "--delivery-id"])
        XCTAssertNotNil(UUID(uuidString: ingestArgs[2]))
        XCTAssertEqual(ingestArgs[3], "--json")
        XCTAssertEqual(fake.mutateLog[1], ["run", "--json"])
    }

    func testIngestPendingSkipsRunWhenNothingLandsAndSurfacesNotices() async {
        let fake = FakeClient()
        fake.statusQueue = [snap([])]
        fake.mutateHandler = { args in
            XCTAssertEqual(args.first, "ingest")
            return Envelope(ok: true, result: IngestResult(
                ingested: [],
                skipped: [FileNote(file: "P1.RW2", reason: "duplicate")],
                conflicts: [], failed: []), error: nil) as Any
        }
        let model = AppModel(client: fake, repo: URL(fileURLWithPath: "/r"),
                             sliderDebounce: .zero)

        await model.ingestPending()

        XCTAssertEqual(fake.mutateLog.count, 1)
        XCTAssertEqual(model.banner?.code, "INGEST_NOTICE")
        XCTAssertTrue(model.banner?.message.contains("P1.RW2: duplicate") == true)
    }

    func testIngestRunFailureRetryDoesNotForceWholeRepo() async {
        let fake = FakeClient()
        fake.statusQueue = [snap([]), snap([])]
        var runCalls = 0
        fake.mutateHandler = { args in
            if args.first == "ingest" {
                return Envelope(ok: true, result: IngestResult(
                    ingested: ["P1"], skipped: [], conflicts: [], failed: []),
                    error: nil) as Any
            }
            runCalls += 1
            if runCalls == 1 {
                return Envelope(ok: false, result: RunResult(
                    published: [], advanced: [], failed: [StemFailure(
                        stem: "P1", code: "RENDER_FAILED", message: "bad")]),
                    error: PipelineErrorInfo(code: "RENDER_FAILED",
                                             message: "render failed")) as Any
            }
            return Envelope(ok: true, result: RunResult(
                published: [], advanced: [], failed: []), error: nil) as Any
        }
        let model = AppModel(client: fake, repo: URL(fileURLWithPath: "/r"),
                             sliderDebounce: .zero)

        await model.ingest(paths: ["/incoming/P1.rw2"])
        XCTAssertEqual(model.bannerAction, .retry)
        await model.retryBannerAction()

        let retryArgs = fake.mutateLog.last
        XCTAssertEqual(retryArgs, ["run", "--json"])
        XCTAssertFalse(retryArgs?.contains("--force") ?? true)
    }

    func testRefreshInternalFailureDoesNotOfferDeadRetry() async {
        let fake = FakeClient()
        fake.statusQueue = [Envelope(
            ok: false, result: nil,
            error: PipelineErrorInfo(code: "INTERNAL", message: "status failed"))]
        let model = AppModel(client: fake, repo: URL(fileURLWithPath: "/r"),
                             sliderDebounce: .zero)

        await model.refresh()
        XCTAssertEqual(model.banner?.code, "INTERNAL")
        XCTAssertNil(model.bannerAction)

        await model.retryBannerAction()
        XCTAssertEqual(fake.statusCalls, 1)
    }

    func testReviewFileFailureDoesNotOfferDeadRetry() async {
        let persistedCropPhoto = PhotoStatus(
            stem: "P1", state: "review_required", deliveryId: "d1",
            ingestedAt: "2026-08-12T00:00:00Z", reviewRevision: "r1",
            previews: [:], previewHashes: [:], stalePreviews: [],
            adjustments: [:],
            crops: ["8x10": CropWindow(x: 0, y: 0, w: 1, h: 1,
                                        source: "persisted")],
            expressionAudit: [], published: PublishedInfo(
                version: nil, path: nil, artifactCount: nil))
        let fake = FakeClient()
        fake.statusQueue = [snap([persistedCropPhoto]), snap([persistedCropPhoto])]
        let model = AppModel(client: fake, repo: URL(fileURLWithPath: "/r"),
                             sliderDebounce: .zero,
                             reviewFileDirectory: URL(fileURLWithPath: "/dev/null"))
        await model.refresh()
        model.startDraft(stem: "P1")

        await model.approve(stem: "P1")
        XCTAssertEqual(model.banner?.code, "INTERNAL")
        XCTAssertNil(model.bannerAction)
        XCTAssertTrue(fake.mutateLog.isEmpty)

        await model.retryBannerAction()
        XCTAssertTrue(fake.mutateLog.isEmpty)
    }
}
