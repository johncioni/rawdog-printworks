import Foundation
import Observation

// MARK: - Pipeline access

/// Everything `AppModel` needs from the pipeline, behind a protocol so tests
/// can inject a scripted fake. Deliberately narrow: three verbs, matching the
/// three shapes of pipeline interaction the app has — the read-only snapshot,
/// a read-only crops query, and any mutating command.
///
/// `mutate` is the ONLY door to a mutating command, and `PipelineClient`'s
/// conformance routes it through `runMutating` (the FIFO queue), so no action
/// on this model can put two mutations on the pipeline at once. `status` and
/// `crops` route through the unqueued `run` — see `AppModel.refresh()` for the
/// gate that keeps those bounded too.
public protocol PipelineRunning: Sendable {
    func status() async -> CommandResult<StatusSnapshot>
    func mutate<R: Codable & Sendable & Equatable>(
        _ type: R.Type, args: [String],
        onEvent: (@Sendable (ProgressEvent) -> Void)?
    ) async -> CommandResult<R>
    func crops(stem: String) async -> CommandResult<CropsResult>
}

/// The canonical arg spellings live here, in one place, so every caller in the
/// app issues byte-identical commands.
extension PipelineClient: PipelineRunning {
    public func status() async -> CommandResult<StatusSnapshot> {
        await run(StatusSnapshot.self, args: ["status", "--json"])
    }

    public func crops(stem: String) async -> CommandResult<CropsResult> {
        await run(CropsResult.self, args: ["crops", "--stem", stem, "--json"])
    }

    public func mutate<R: Codable & Sendable & Equatable>(
        _ type: R.Type, args: [String],
        onEvent: (@Sendable (ProgressEvent) -> Void)?
    ) async -> CommandResult<R> {
        await runMutating(type, args: args, onEvent: onEvent)
    }
}

// MARK: - Banner

/// The single action button an error banner may offer, derived from the error
/// code per spec §7. `retry` re-runs the failed action; the other two are
/// signals for the view layer (open Settings / re-open the review draft).
public enum BannerAction: String, Sendable, Equatable {
    case retry
    case openSettings
    case reReview
}

// MARK: - Review draft

/// Transient review state for one photo, keyed to the `review_revision` of the
/// snapshot it was started against (spec §6.1). Never written to the repo:
/// it becomes the review-file at Approve time and is dropped on quit.
public struct ReviewDraft: Sendable, Equatable {
    /// The three required audit checks, in the order they serialize.
    public static let checkKeys = ["eyes_open", "expressions_natural",
                                   "no_blinks_in_crops"]

    public static var emptyChecks: [String: Bool] {
        Dictionary(uniqueKeysWithValues: checkKeys.map { ($0, false) })
    }

    public var stem: String
    public var baseRevision: String
    public var checks: [String: Bool]
    public var note: String
    public var cropNudges: [String: CropWindow]
    public var isStale: Bool

    public init(stem: String, baseRevision: String,
                checks: [String: Bool]? = nil, note: String = "",
                cropNudges: [String: CropWindow] = [:], isStale: Bool = false) {
        self.stem = stem
        self.baseRevision = baseRevision
        self.checks = checks ?? ReviewDraft.emptyChecks
        self.note = note
        self.cropNudges = cropNudges
        self.isStale = isStale
    }
}

// MARK: - AppModel

/// The app's single state tree. It renders what `status --json` reports and
/// shells out for every mutation — it never recomputes pipeline state, and it
/// writes exactly one file (the temp review-file, outside the repo).
///
/// Every mutating action follows the same cycle (spec §4.1):
/// `beginCommand` → mutate (+ streamed progress) → apply result → surface any
/// error → `endCommand`, whose last act is always a `refresh()`. The UI is
/// never updated speculatively.
@Observable
@MainActor
public final class AppModel {

    // MARK: Dependencies

    /// Repo root — needed for repo-relative path resolution (`RepoPaths`) and
    /// for `pendingInputFiles` (Task 10).
    public let repo: URL

    @ObservationIgnored private let client: any PipelineRunning
    @ObservationIgnored private let sliderDebounce: Duration
    @ObservationIgnored private let reviewFileDirectory: URL

    // MARK: Published state

    public var snapshot: StatusSnapshot?
    public var drafts: [String: ReviewDraft] = [:]

    /// The current error banner (spec §7). `LOCK_HELD` never lands here — it
    /// is the busy pill instead.
    public var banner: PipelineErrorInfo?
    /// Last 50 stderr lines behind the banner's "Show Details" disclosure.
    public var bannerDetails: String?
    /// Which action button the banner offers, if any.
    public var bannerAction: BannerAction?

    /// The lock is held by something that isn't us (the CLI) → busy pill.
    public var busyExternally = false
    /// Name of the command currently running (`nil` = idle).
    public var activeCommand: String?
    /// The stem `activeCommand` targets, for §6.1's deferred reconcile.
    public var activeStem: String?
    /// Latest progress event per stem.
    public var renderProgress: [String: ProgressEvent] = [:]

    public var selectedStem: String?
    public var selectedStyle: String = "natural"
    /// `.none` = browse all deliveries; `.some(nil)` = the "Earlier" group.
    public var selectedDeliveryId: String??

    /// Successes from the most recent run result — applied even when the
    /// envelope failed with `PARTIAL_FAILURE` (drives Task 10's notifications).
    public var lastPublished: [PublishedPhoto] = []
    /// State advances from the most recent result and unresolved per-stem
    /// failures accumulated across targeted runs.
    public var lastAdvanced: [AdvancedPhoto] = []
    public var lastFailures: [String: StemFailure] = [:]
    /// Per-file failures from the most recent ingest result.
    public var lastIngestFailures: [String: FileFailure] = [:]

    /// Args of the most recently dispatched mutating command.
    public private(set) var lastMutatingArgs: [String]?

    // MARK: Private state

    /// One debouncer per (stem, style) — switching photo or style must never
    /// cancel or merge another pair's pending edit.
    @ObservationIgnored private var debouncers: [String: Debouncer] = [:]
    @ObservationIgnored private var pendingAdjustments: [String: PendingAdjust] = [:]
    @ObservationIgnored private var inFlightAdjustments: [String: InFlightAdjust] = [:]
    @ObservationIgnored private var failureStamps: [String: FailureStamp] = [:]
    @ObservationIgnored private var cropCache: [String: CachedCrops] = [:]
    @ObservationIgnored private var cropRequests: [String: CropRequest] = [:]

    /// Re-runs the last retryable failed action (`retryBannerAction`).
    @ObservationIgnored private var lastFailedAction: (@MainActor @Sendable () async -> Void)?

    /// Refresh gate (spec §7 watcher storms): at most one `status` in flight,
    /// with a single trailing refresh for anything that arrived meanwhile.
    @ObservationIgnored private var isRefreshing = false
    @ObservationIgnored private var pendingRefresh = false

    /// Progress bookkeeping: events arrive off the main actor, so each command
    /// stamps its generation and late events from a finished command are
    /// dropped rather than resurrecting a progress bar.
    @ObservationIgnored private var commandGeneration = 0
    @ObservationIgnored private var progressKeys: Set<String> = []

    private struct PendingAdjust {
        let stem: String
        let style: String
        var temperature: Double?
        var exposure: Double?
    }

    private struct InFlightAdjust {
        let id: UUID
        let stem: String
        let task: Task<Void, Never>
    }

    private struct FailureStamp: Equatable {
        let publishedVersion: String?
        let reviewRevision: String

        init(photo: PhotoStatus) {
            publishedVersion = photo.published.version
            reviewRevision = photo.reviewRevision
        }
    }

    private struct CachedCrops {
        let revision: String
        let result: CropsResult
    }

    private struct CropRequest {
        let id: UUID
        let revision: String
        let task: Task<CommandResult<CropsResult>, Never>
    }

    /// The command context in force when a status subprocess was dispatched.
    /// Reconcile must use this capture-time stamp, not whichever command flags
    /// happen to remain when that subprocess eventually returns.
    /// `activeStem` is nil when nothing was running at dispatch time.
    private struct SnapshotCapture {
        let commandGeneration: Int
        let activeStem: String?
    }

    public init(client: any PipelineRunning, repo: URL,
                sliderDebounce: Duration = .seconds(2)) {
        self.client = client
        self.repo = repo
        self.sliderDebounce = sliderDebounce
        self.reviewFileDirectory = FileManager.default.temporaryDirectory
    }

    /// Test seam for the review-file write failure path. Production always
    /// uses the public initializer and therefore the system temp directory.
    init(client: any PipelineRunning, repo: URL, sliderDebounce: Duration,
         reviewFileDirectory: URL) {
        self.client = client
        self.repo = repo
        self.sliderDebounce = sliderDebounce
        self.reviewFileDirectory = reviewFileDirectory
    }

    // MARK: - Snapshot

    /// `status --json` → snapshot → busy pill → draft reconcile.
    ///
    /// Gated so at most one `status` is in flight; calls that arrive while one
    /// is running queue exactly one trailing refresh instead of spawning a
    /// second subprocess. Without this, a watcher storm (or two actions
    /// finishing together) fans out into unbounded concurrent `run()` calls,
    /// each of which holds two reader threads for the subprocess's lifetime.
    public func refresh() async {
        if isRefreshing {
            pendingRefresh = true
            return
        }
        isRefreshing = true
        defer { isRefreshing = false }
        repeat {
            pendingRefresh = false
            await performRefresh()
        } while pendingRefresh
    }

    private func performRefresh() async {
        let capture = SnapshotCapture(
            commandGeneration: commandGeneration,
            activeStem: activeCommand == nil ? nil : activeStem)
        let result = await client.status()
        guard result.envelope.ok, let snapshot = result.envelope.result else {
            surface(result.envelope.error
                    ?? PipelineErrorInfo(code: "INTERNAL",
                                         message: "status returned no result"),
                    details: result.stderrTail)
            return
        }
        self.snapshot = snapshot
        for photo in snapshot.photos where lastFailures[photo.stem] != nil {
            let current = FailureStamp(photo: photo)
            guard let failedAt = failureStamps[photo.stem] else {
                failureStamps[photo.stem] = current
                continue
            }
            if current != failedAt {
                lastFailures.removeValue(forKey: photo.stem)
                failureStamps.removeValue(forKey: photo.stem)
            }
        }
        busyExternally = snapshot.lock.held && activeCommand == nil
        reconcileDrafts(snapshot, capturedDuring: capture)
    }

    public func photo(_ stem: String) -> PhotoStatus? {
        snapshot?.photos.first { $0.stem == stem }
    }

    /// Photos belonging to one delivery, preserving the pipeline snapshot's
    /// order. A nil ID denotes the delivery-less "Earlier" group.
    public func photos(inDeliveryOf deliveryID: String?) -> [PhotoStatus] {
        (snapshot?.photos ?? []).filter { $0.deliveryId == deliveryID }
    }

    /// Read-only crop suggestions/persisted windows, cached only while the
    /// photo's review revision is unchanged.
    public func crops(stem: String) async -> CropsResult? {
        guard let revision = photo(stem)?.reviewRevision else { return nil }
        if let cached = cropCache[stem], cached.revision == revision {
            return cached.result
        }

        let request: CropRequest
        if let pending = cropRequests[stem], pending.revision == revision {
            request = pending
        } else {
            let id = UUID()
            let client = client
            let task = Task { await client.crops(stem: stem) }
            request = CropRequest(id: id, revision: revision, task: task)
            cropRequests[stem] = request
        }

        let response = await request.task.value
        if cropRequests[stem]?.id == request.id {
            cropRequests.removeValue(forKey: stem)
        }
        guard response.envelope.ok, let result = response.envelope.result else {
            surface(response.envelope.error
                    ?? PipelineErrorInfo(code: "INTERNAL",
                                         message: "crops returned no result"),
                    details: response.stderrTail)
            return nil
        }
        guard photo(stem)?.reviewRevision == revision else {
            return await crops(stem: stem)
        }
        cropCache[stem] = CachedCrops(revision: revision, result: result)
        return result
    }

    /// Deliveries newest first, with the delivery-less legacy photos ("Earlier")
    /// always last. Photo order inside a group is the snapshot's own order.
    public func deliveries() -> [(id: String?, photos: [PhotoStatus])] {
        guard let photos = snapshot?.photos else { return [] }
        var order: [String] = []
        var groups: [String: [PhotoStatus]] = [:]
        var earlier: [PhotoStatus] = []
        for photo in photos {
            guard let id = photo.deliveryId else {
                earlier.append(photo)
                continue
            }
            if groups[id] == nil { order.append(id) }
            groups[id, default: []].append(photo)
        }
        // `ingested_at` is RFC 3339 UTC with a fixed shape, so lexicographic
        // ordering is chronological ordering.
        let sorted = order.sorted { lhs, rhs in
            let left = groups[lhs]?.compactMap(\.ingestedAt).max() ?? ""
            let right = groups[rhs]?.compactMap(\.ingestedAt).max() ?? ""
            return left == right ? lhs < rhs : left > right
        }
        var result: [(id: String?, photos: [PhotoStatus])] =
            sorted.map { (id: $0, photos: groups[$0] ?? []) }
        if !earlier.isEmpty { result.append((id: nil, photos: earlier)) }
        return result
    }

    // MARK: - Drafts

    public func startDraft(stem: String) {
        guard let photo = photo(stem) else { return }
        drafts[stem] = ReviewDraft(stem: stem,
                                   baseRevision: photo.reviewRevision)
    }

    /// The stale-banner action: adopt the photo's current revision, reset all
    /// three checks (the user must re-verify against the fresh pixels), keep
    /// the note and crop nudges.
    public func reReview(stem: String) {
        guard var draft = drafts[stem], let photo = photo(stem) else { return }
        draft.baseRevision = photo.reviewRevision
        draft.checks = ReviewDraft.emptyChecks
        draft.isStale = false
        drafts[stem] = draft
    }

    public func setDraftCheck(stem: String, key: String, isChecked: Bool) {
        guard ReviewDraft.checkKeys.contains(key) else { return }
        if drafts[stem] == nil { startDraft(stem: stem) }
        drafts[stem]?.checks[key] = isChecked
    }

    public func setDraftNote(stem: String, note: String) {
        if drafts[stem] == nil { startDraft(stem: stem) }
        drafts[stem]?.note = note
    }

    public func setCropNudge(stem: String, cropName: String,
                             window: CropWindow) {
        if drafts[stem] == nil { startDraft(stem: stem) }
        drafts[stem]?.cropNudges[cropName] = window
    }

    /// The ONE shared rebase path, used by both `applyAdjust` and
    /// `rerenderPreview` (spec §6.1). The draft rebases only if its key equals
    /// the command's `before`; any other movement marks it stale.
    ///
    /// The second half of the rule — "and the refreshed state equals `after`" —
    /// is enforced by `reconcileDrafts` at the command's terminal refresh:
    /// after a matching rebase `baseRevision == after`, so a refreshed state
    /// that is anything but `after` fails the revision comparison and stales
    /// the draft. An interleaved external edit hiding behind our own command
    /// therefore cannot survive as a valid draft.
    public func rebase(stem: String, before: String, after: String) {
        guard var draft = drafts[stem] else { return }
        if draft.baseRevision == before {
            draft.baseRevision = after
        } else {
            draft.isStale = true
        }
        drafts[stem] = draft
    }

    /// While one of our own commands is in flight for a stem, staleness
    /// evaluation for that stem is deferred (spec §6.1) so a watcher refresh
    /// during the command's intermediate states can't flap the draft;
    /// reconciliation happens once, at the terminal refresh (which runs with
    /// `activeCommand` already cleared).
    private func reconcileDrafts(_ snapshot: StatusSnapshot,
                                 capturedDuring capture: SnapshotCapture) {
        // A command began after this status was dispatched, so the snapshot
        // predates whatever that command did — including its rebase. Judging a
        // rebased draft against a pre-command revision would stale it forever
        // (reconcile only ever SETS `isStale`). The command's own terminal
        // refresh, or the trailing refresh the gate queued behind this one,
        // reconciles with a snapshot that is actually current.
        guard capture.commandGeneration == commandGeneration else { return }
        for (stem, draft) in drafts {
            if capture.activeStem == stem { continue }
            guard let photo = snapshot.photos.first(where: { $0.stem == stem })
            else { continue }
            if photo.reviewRevision != draft.baseRevision, !draft.isStale {
                drafts[stem]?.isStale = true
            }
        }
    }

    public func canApprove(stem: String) -> Bool {
        guard let draft = drafts[stem], !draft.isStale,
              let photo = photo(stem), photo.stalePreviews.isEmpty,
              activeCommand == nil, !busyExternally
        else { return false }
        return ReviewDraft.checkKeys.allSatisfy { draft.checks[$0] == true }
    }

    // MARK: - Sliders

    private static func debouncerKey(stem: String, style: String) -> String {
        "\(stem)|\(style)"
    }

    /// Stores the pending value for this (stem, style) and debounces the
    /// `adjust`. Each pair accumulates its own temperature/exposure: a nil
    /// argument leaves that control's pending value untouched.
    public func setSlider(stem: String, style: String,
                          temperature: Double?, exposure: Double?) {
        let key = Self.debouncerKey(stem: stem, style: style)
        var pending = pendingAdjustments[key]
            ?? PendingAdjust(stem: stem, style: style,
                             temperature: nil, exposure: nil)
        if let temperature { pending.temperature = temperature }
        if let exposure { pending.exposure = exposure }
        pendingAdjustments[key] = pending

        let debouncer = debouncers[key] ?? Debouncer(delay: sliderDebounce)
        debouncers[key] = debouncer
        debouncer.schedule { [weak self] in
            await self?.firePendingAdjust(key: key)
        }
    }

    /// Flushes every pending slider edit for this stem — all styles, since a
    /// pending edit on a style the user isn't looking at still belongs to the
    /// photo being approved.
    public func flushPendingAdjustments(stem: String) async {
        var keys = Set(pendingAdjustments.compactMap { key, value in
            value.stem == stem ? key : nil
        })
        keys.formUnion(inFlightAdjustments.compactMap { key, value in
            value.stem == stem ? key : nil
        })
        for key in keys.sorted() {
            await debouncers[key]?.flush()
            // If the debounce timer already took its action, `flush()` has
            // nothing to run. Await the tracked task that action created.
            await firePendingAdjust(key: key)
        }
    }

    private func firePendingAdjust(key: String) async {
        guard let pending = pendingAdjustments.removeValue(forKey: key) else {
            guard let inFlight = inFlightAdjustments[key] else { return }
            await inFlight.task.value
            if inFlightAdjustments[key]?.id == inFlight.id {
                inFlightAdjustments.removeValue(forKey: key)
            }
            return
        }

        // Queue a second batch for this key behind the first when the user
        // moved the same slider again while its previous adjust was running.
        let predecessor = inFlightAdjustments[key]?.task
        let id = UUID()
        let task = Task { @MainActor [weak self] in
            await predecessor?.value
            guard let self else { return }
            await self.applyAdjust(stem: pending.stem, style: pending.style,
                                   temperature: pending.temperature,
                                   exposure: pending.exposure)
        }
        inFlightAdjustments[key] = InFlightAdjust(
            id: id, stem: pending.stem, task: task)
        await task.value
        if inFlightAdjustments[key]?.id == id {
            inFlightAdjustments.removeValue(forKey: key)
        }
    }

    // MARK: - Actions

    /// `adjust --stem S --style Y [--temperature K] [--exposure EV] --json`
    /// — only the controls that actually changed are sent.
    public func applyAdjust(stem: String, style: String,
                            temperature: Double?, exposure: Double?) async {
        beginCommand("adjust", stem: stem)
        var args = ["adjust", "--stem", stem, "--style", style]
        if let temperature {
            args += ["--temperature", Self.number(temperature, decimals: 0)]
        }
        if let exposure {
            args += ["--exposure", Self.number(exposure, decimals: 2)]
        }
        args.append("--json")

        let result = await send(AdjustResult.self, args: args)
        if result.envelope.ok, let adjusted = result.envelope.result {
            rebase(stem: stem, before: adjusted.reviewRevisionBefore,
                   after: adjusted.reviewRevisionAfter)
        }
        // A failed adjust is NOT force-staled here: the terminal refresh
        // compares the refreshed revision against the draft, so a failure that
        // moved the sidecar stales the draft and one that changed nothing
        // leaves it alone — disk truth, not a guess.
        surface(result.envelope.error, details: result.stderrTail,
                retry: { [weak self] in
                    await self?.applyAdjust(stem: stem, style: style,
                                            temperature: temperature,
                                            exposure: exposure)
                })
        await endCommand()
    }

    /// Cancels any not-yet-issued edit for this pair, then restores the
    /// pipeline-owned adjustment bundle with `adjust --reset`.
    public func resetAdjust(stem: String, style: String) async {
        let key = Self.debouncerKey(stem: stem, style: style)
        pendingAdjustments.removeValue(forKey: key)
        await debouncers[key]?.flush()
        debouncers.removeValue(forKey: key)
        await firePendingAdjust(key: key)

        beginCommand("adjust", stem: stem)
        let result = await send(
            AdjustResult.self,
            args: ["adjust", "--stem", stem, "--style", style, "--reset",
                   "--json"])
        if result.envelope.ok, let adjusted = result.envelope.result {
            rebase(stem: stem, before: adjusted.reviewRevisionBefore,
                   after: adjusted.reviewRevisionAfter)
        }
        surface(result.envelope.error, details: result.stderrTail,
                retry: { [weak self] in
                    await self?.resetAdjust(stem: stem, style: style)
                })
        await endCommand()
    }

    /// `preview --stem S --style Y --json` — the stale-preview chip's action.
    /// Shares the rebase path with `applyAdjust`: the result carries the same
    /// `review_revision_before`/`after` pair.
    public func rerenderPreview(stem: String, style: String) async {
        beginCommand("preview", stem: stem)
        let result = await send(
            AdjustResult.self,
            args: ["preview", "--stem", stem, "--style", style, "--json"])
        if result.envelope.ok, let rendered = result.envelope.result {
            rebase(stem: stem, before: rendered.reviewRevisionBefore,
                   after: rendered.reviewRevisionAfter)
        }
        surface(result.envelope.error, details: result.stderrTail,
                retry: { [weak self] in
                    await self?.rerenderPreview(stem: stem, style: style)
                })
        await endCommand()
    }

    /// Flush pending slider edits → write the review-file to the system temp
    /// directory (never the repo) → `approve` → on success `run --stem` →
    /// delete the temp file → refresh.
    public func approve(stem: String) async {
        // The flush's `adjust` can rebase the draft, so the draft is re-read
        // afterwards: `expected_review_revision` must be the revision the
        // review-file is actually built against.
        await flushPendingAdjustments(stem: stem)
        guard let draft = drafts[stem] else { return }

        beginCommand("approve", stem: stem)
        let windows = await approveCropWindows(stem: stem, draft: draft)
        guard let reviewFile = writeReviewFile(draft: draft, windows: windows)
        else {
            surface(PipelineErrorInfo(code: "INTERNAL",
                                      message: "could not write the review file"),
                    details: "")
            await endCommand()
            return
        }
        // Deleted on every exit path, per §4.3 ("deleted after the envelope").
        defer { try? FileManager.default.removeItem(at: reviewFile) }

        let approved = await send(
            ApproveResult.self,
            args: ["approve", "--stem", stem, "--review-file",
                   reviewFile.path, "--json"])

        if approved.envelope.ok, approved.envelope.result != nil {
            activeCommand = "run"
            let run = await send(RunResult.self,
                                 args: ["run", "--stem", stem, "--json"],
                                 streamProgress: true)
            applyRunResult(run.envelope.result)          // result before error
            surface(run.envelope.error, details: run.stderrTail,
                    retry: { [weak self] in await self?.runStem(stem) })
        } else {
            if approved.envelope.error?.code == "STALE_REVIEW" {
                drafts[stem]?.isStale = true
            }
            surface(approved.envelope.error, details: approved.stderrTail,
                    retry: { [weak self] in await self?.approve(stem: stem) })
        }
        await endCommand()
    }

    /// Crops for the review-file: the photo's persisted windows if it has
    /// them, else what `crops --stem` suggests, with the draft's nudges
    /// applied on top.
    private func approveCropWindows(stem: String,
                                    draft: ReviewDraft) async -> [String: CropWindow] {
        var windows = photo(stem)?.crops ?? [:]
        if windows.isEmpty {
            if let fetched = await crops(stem: stem) { windows = fetched.windows }
        }
        windows.merge(draft.cropNudges) { _, nudge in nudge }
        return windows
    }

    /// The review-file is the ONLY file this app writes, and it goes to the
    /// system temp directory — never into the repo.
    private func writeReviewFile(draft: ReviewDraft,
                                 windows: [String: CropWindow]) -> URL? {
        let body: [String: Any] = [
            "expected_review_revision": draft.baseRevision,
            "expression_audit": auditStrings(draft),
            // `source` is status/crops output, not review-file input.
            "crops": windows.mapValues {
                ["x": $0.x, "y": $0.y, "w": $0.w, "h": $0.h]
            },
        ]
        let url = reviewFileDirectory
            .appendingPathComponent("printworks-review-\(UUID().uuidString).json")
        guard let data = try? JSONSerialization.data(withJSONObject: body,
                                                     options: [.sortedKeys]),
              (try? data.write(to: url, options: .atomic)) != nil
        else { return nil }
        return url
    }

    /// The exact audit strings already durable in `recipes/*.yaml`. All three
    /// checks are required by `canApprove`, so they always serialize as pass.
    private func auditStrings(_ draft: ReviewDraft) -> [String] {
        var lines = ["eyes open — all: pass",
                     "expressions natural: pass",
                     "no blinks in crops: pass"]
        if !draft.note.isEmpty { lines.append("note: \(draft.note)") }
        return lines
    }

    /// `ingest --from … --delivery-id <uuid> --json`, then `run --json` so the
    /// new photos get previews and land at `review_required`.
    public func ingest(paths: [String]) async {
        guard !paths.isEmpty else { return }
        beginCommand("ingest", stem: nil)
        let args = ["ingest", "--from"] + paths
            + ["--delivery-id", UUID().uuidString, "--json"]
        let ingested = await send(IngestResult.self, args: args,
                                  streamProgress: true)
        applyIngestResult(ingested.envelope.result)

        // Result before error: skips/conflicts are collected from the result
        // even when the envelope failed with PARTIAL_FAILURE.
        var notices: [String] = []
        if let result = ingested.envelope.result {
            notices += result.skipped.map { "\($0.file): \($0.reason)" }
            notices += result.conflicts.map { "\($0.file): \($0.reason)" }
        }

        // Chain `run` only when something actually landed — a failed or
        // fully-deduped ingest has nothing to render, and chaining anyway
        // would just take the lock again to report the same failure twice.
        var runError: PipelineErrorInfo?
        var runDetails = ""
        if let result = ingested.envelope.result, !result.ingested.isEmpty {
            activeCommand = "run"
            let run = await send(RunResult.self, args: ["run", "--json"],
                                 streamProgress: true)
            applyRunResult(run.envelope.result)
            runError = run.envelope.error
            runDetails = run.stderrTail
        }

        if let error = ingested.envelope.error {
            surface(error, details: ingested.stderrTail,
                    retry: { [weak self] in await self?.ingest(paths: paths) })
        } else if let error = runError {
            surface(error, details: runDetails,
                    retry: { [weak self] in await self?.runAll() })
        } else if !notices.isEmpty {
            // Not a pipeline failure — a report the user has to act on in the
            // CLI. Carries its own code so §7's action mapping offers no button.
            surface(PipelineErrorInfo(code: "INGEST_NOTICE",
                                      message: notices.joined(separator: "\n")),
                    details: "")
        }
        await endCommand()
    }

    /// Reprocess menu: `run --stem S --force --json`.
    public func reprocess(stem: String) async {
        await runCycle(stem: stem,
                       args: ["run", "--stem", stem, "--force", "--json"],
                       retry: { [weak self] in await self?.reprocess(stem: stem) })
    }

    /// Reprocess menu: `run --force --json`.
    public func reprocessAll() async {
        await runCycle(stem: nil, args: ["run", "--force", "--json"],
                       retry: { [weak self] in await self?.reprocessAll() })
    }

    /// Plain `run --stem S --json` — the Retry behind a failed render.
    public func retryRender(stem: String) async {
        await runStem(stem)
    }

    private func runAll() async {
        await runCycle(stem: nil, args: ["run", "--json"],
                       retry: { [weak self] in await self?.runAll() })
    }

    private func runStem(_ stem: String) async {
        await runCycle(stem: stem, args: ["run", "--stem", stem, "--json"],
                       retry: { [weak self] in await self?.runStem(stem) })
    }

    private func runCycle(stem: String?, args: [String],
                          retry: @escaping @MainActor @Sendable () async -> Void) async {
        beginCommand("run", stem: stem)
        let result = await send(RunResult.self, args: args, streamProgress: true)
        applyRunResult(result.envelope.result)           // result before error
        surface(result.envelope.error, details: result.stderrTail, retry: retry)
        await endCommand()
    }

    private func applyRunResult(_ result: RunResult?) {
        guard let result else { return }
        lastPublished = result.published
        lastAdvanced = result.advanced
        for stem in result.published.map(\.stem) + result.advanced.map(\.stem) {
            lastFailures.removeValue(forKey: stem)
            failureStamps.removeValue(forKey: stem)
        }
        for failure in result.failed {
            lastFailures[failure.stem] = failure
            if let photo = photo(failure.stem) {
                failureStamps[failure.stem] = FailureStamp(photo: photo)
            } else {
                failureStamps.removeValue(forKey: failure.stem)
            }
        }
    }

    private func applyIngestResult(_ result: IngestResult?) {
        guard let result else { return }
        lastIngestFailures = result.failed.reduce(into: [:]) {
            failures, failure in
            failures[failure.file] = failure
        }
    }

    // MARK: - Banner

    /// Re-runs the last failed action for a Retry-coded banner.
    public func retryBannerAction() async {
        guard bannerAction == .retry, let retry = lastFailedAction else { return }
        clearBanner()
        await retry()
    }

    public func dismissBanner() {
        clearBanner()
    }

    private func clearBanner() {
        banner = nil
        bannerDetails = nil
        bannerAction = nil
    }

    /// The uniform failure surface (spec §7). `LOCK_HELD` is the busy pill,
    /// never a banner — the terminal refresh then re-derives the pill from
    /// disk truth.
    private func surface(_ error: PipelineErrorInfo?, details: String,
                         retry: (@MainActor @Sendable () async -> Void)? = nil) {
        guard let error else { return }
        if error.code == "LOCK_HELD" {
            busyExternally = true
            return
        }
        banner = error
        bannerDetails = details.isEmpty ? nil : details
        bannerAction = Self.bannerAction(for: error.code)
        if bannerAction == .retry, retry == nil { bannerAction = nil }
        lastFailedAction = bannerAction == .retry ? retry : nil
    }

    private static func bannerAction(for code: String) -> BannerAction? {
        switch code {
        case "RENDER_FAILED", "VERIFY_FAILED", "INTERNAL": return .retry
        case "TOOLCHAIN_FAILED": return .openSettings
        case "STALE_REVIEW": return .reReview
        default: return nil
        }
    }

    // MARK: - Command cycle

    private func beginCommand(_ name: String, stem: String?) {
        commandGeneration &+= 1
        activeCommand = name
        activeStem = stem
        clearBanner()
    }

    /// Every action's exit path — success or failure — ends here, and this
    /// always ends with a refresh. `activeCommand` is cleared first so the
    /// terminal refresh is the one that reconciles this stem's draft.
    private func endCommand() async {
        activeCommand = nil
        activeStem = nil
        for key in progressKeys { renderProgress.removeValue(forKey: key) }
        progressKeys.removeAll()
        await refresh()
    }

    private func send<R: Codable & Sendable & Equatable>(
        _ type: R.Type, args: [String], streamProgress: Bool = false
    ) async -> CommandResult<R> {
        lastMutatingArgs = args
        let handler = streamProgress
            ? progressHandler(defaultStem: activeStem) : nil
        return await client.mutate(type, args: args, onEvent: handler)
    }

    private func progressHandler(defaultStem: String?)
    -> (@Sendable (ProgressEvent) -> Void) {
        let generation = commandGeneration
        return { [weak self] event in
            Task { @MainActor [weak self] in
                guard let self, generation == self.commandGeneration,
                      let key = event.stem ?? defaultStem else { return }
                self.renderProgress[key] = event
                self.progressKeys.insert(key)
            }
        }
    }

    private static func number(_ value: Double, decimals: Int) -> String {
        String(format: "%.\(decimals)f", value)
    }
}
