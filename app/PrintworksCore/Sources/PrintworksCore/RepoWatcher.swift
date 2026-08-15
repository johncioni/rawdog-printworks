import Darwin
import Foundation

public final class RepoWatcher: @unchecked Sendable {
    private static let maxCoalesceWait = 2.0

    private static let watchedDirectories = [
        "Input",
        "previews",
        "sidecars",
        "recipes",
        "config",
        "config/styles",
        "config/lab-profiles",
        "config/rawtherapee-seed",
        "Output",
        "Output/photos",
        "run",
    ]

    private final class DirectoryWatch: @unchecked Sendable {
        let source: DispatchSourceFileSystemObject
        let fileDescriptor: Int32
        let closed = DispatchSemaphore(value: 0)
        var isCancelling = false

        init(source: DispatchSourceFileSystemObject, fileDescriptor: Int32) {
            self.source = source
            self.fileDescriptor = fileDescriptor
        }
    }

    private let repo: URL
    private let coalesceDelay: Double
    private let queue = DispatchQueue(label: "com.rawdog.printworks.repo-watcher",
                                      qos: .utility)
    private let queueKey = DispatchSpecificKey<Void>()
    private let lock = NSLock()

    private var watches: [String: DirectoryWatch] = [:]
    private var lifecycleGeneration: UInt64 = 0
    private var stopsInFlight = 0
    private var pendingChange = false
    private var firstPendingChangeAt: DispatchTime?
    private var coalesceGeneration: UInt64 = 0
    private var pendingCoalesce: DispatchWorkItem?
    private var pollingGeneration: UInt64 = 0
    private var pollingTask: Task<Void, Never>?
    private var continuations: [UInt64: AsyncStream<Void>.Continuation] = [:]
    private var nextConsumerID: UInt64 = 0

    public var changes: AsyncStream<Void> {
        AsyncStream(bufferingPolicy: .bufferingNewest(1)) { [weak self] continuation in
            guard let self else {
                continuation.finish()
                return
            }
            let consumerID = lock.withLock {
                nextConsumerID &+= 1
                continuations[nextConsumerID] = continuation
                return nextConsumerID
            }
            continuation.onTermination = { [weak self] _ in
                self?.removeContinuation(consumerID)
            }
        }
    }

    public init(repo: URL, coalesce: Duration = .milliseconds(500)) {
        self.repo = repo
        self.coalesceDelay = Self.seconds(coalesce)
        queue.setSpecific(key: queueKey, value: ())
    }

    deinit {
        stop()
    }

    /// Starts sources for every currently present review-input directory.
    /// Calling this again is intentional: existing sources are retained while
    /// paths that were absent during an earlier call are retried.
    public func start() {
        start(afterEntry: nil)
    }

    private func start(afterEntry: (@Sendable () -> Void)?) {
        let generation: UInt64? = lock.withLock {
            guard stopsInFlight == 0 else { return nil }
            return lifecycleGeneration
        }
        guard let generation else { return }

        afterEntry?()
        for relativePath in Self.watchedDirectories {
            startWatching(relativePath,
                          requiredLifecycleGeneration: generation)
        }
    }

    #if DEBUG
    func _startForTesting(afterEntry: @escaping @Sendable () -> Void) {
        start(afterEntry: afterEntry)
    }

    func _runOnPrivateQueueForTesting(
        _ operation: @escaping @Sendable () -> Void
    ) {
        queue.async(execute: operation)
    }
    #endif

    /// Cancels every source, cancels polling, invalidates queued coalescing,
    /// and finishes current consumers. Off the source queue it also waits for
    /// cancellation handlers to close descriptors; on that queue the handlers
    /// drain immediately after this call returns, avoiding self-deadlock.
    public func stop() {
        let onOwnQueue = DispatchQueue.getSpecific(key: queueKey) != nil
        let stopped = lock.withLock {
            lifecycleGeneration &+= 1
            stopsInFlight += 1
            pollingGeneration &+= 1
            coalesceGeneration &+= 1
            pendingChange = false
            firstPendingChangeAt = nil

            let state = (
                pollingTask,
                pendingCoalesce,
                Array(watches.values),
                Array(continuations.values)
            )
            pollingTask = nil
            pendingCoalesce = nil
            watches.removeAll()
            continuations.removeAll()
            return state
        }

        stopped.0?.cancel()
        stopped.1?.cancel()
        for watch in stopped.2 {
            watch.source.cancel()
        }
        if !onOwnQueue {
            for watch in stopped.2 {
                watch.closed.wait()
            }
        }
        for continuation in stopped.3 {
            continuation.finish()
        }
        lock.withLock {
            stopsInFlight -= 1
        }
    }

    /// Emits a change each interval until cancelled. Each tick also retries
    /// sources for directories that did not exist at the preceding start.
    public func startPolling(interval: Duration = .seconds(5)) {
        lock.lock()
        guard pollingTask == nil else {
            lock.unlock()
            return
        }
        pollingGeneration &+= 1
        let generation = pollingGeneration
        pollingTask = Task { [weak self] in
            while !Task.isCancelled {
                do {
                    try await Task.sleep(for: interval)
                } catch {
                    break
                }
                guard let self, !Task.isCancelled else { break }
                self.retryMissingDirectories(pollingGeneration: generation)
                self.emitPoll(generation: generation)
            }
        }
        lock.unlock()
    }

    public func stopPolling() {
        let task = lock.withLock {
            pollingGeneration &+= 1
            let task = pollingTask
            pollingTask = nil
            return task
        }
        task?.cancel()
    }

    /// Visible to `@testable` tests so descriptor closure can be asserted at
    /// the OS boundary with `fcntl(F_GETFD)` after `stop()` returns.
    var openFileDescriptors: [Int32] {
        lock.withLock { watches.values.map(\.fileDescriptor) }
    }

    private func retryMissingDirectories(pollingGeneration: UInt64) {
        for relativePath in Self.watchedDirectories {
            startWatching(relativePath,
                          requiredPollingGeneration: pollingGeneration)
        }
    }

    private func startWatching(
        _ relativePath: String,
        requiredLifecycleGeneration: UInt64? = nil,
        requiredPollingGeneration: UInt64? = nil
    ) {
        lock.lock()
        if stopsInFlight != 0 {
            lock.unlock()
            return
        }
        if let requiredLifecycleGeneration,
           requiredLifecycleGeneration != lifecycleGeneration {
            lock.unlock()
            return
        }
        if let requiredPollingGeneration,
           (requiredPollingGeneration != pollingGeneration
            || pollingTask == nil) {
            lock.unlock()
            return
        }
        guard watches[relativePath] == nil else {
            lock.unlock()
            return
        }

        let directory = repo.appendingPathComponent(relativePath)
        let descriptor = directory.path.withCString {
            Darwin.open($0, O_EVTONLY)
        }
        guard descriptor >= 0 else {
            lock.unlock()
            return
        }

        let source = DispatchSource.makeFileSystemObjectSource(
            fileDescriptor: descriptor,
            eventMask: [.write, .rename, .delete],
            queue: queue)
        let watch = DirectoryWatch(source: source, fileDescriptor: descriptor)
        source.setEventHandler { [weak self] in
            self?.directoryChanged(relativePath)
        }
        source.setCancelHandler { [weak self] in
            Darwin.close(descriptor)
            self?.finishedCancelling(watch, relativePath: relativePath)
            watch.closed.signal()
        }
        watches[relativePath] = watch
        source.resume()
        lock.unlock()
    }

    private func directoryChanged(_ relativePath: String) {
        scheduleCoalescedChange()

        // A source tracks the directory vnode that was opened. Once that
        // directory is removed or renamed, discard the source so the next
        // explicit start or polling tick can attach to a recreated path.
        let path = repo.appendingPathComponent(relativePath).path
        if !FileManager.default.fileExists(atPath: path) {
            cancelWatch(relativePath)
        }
    }

    private func cancelWatch(_ relativePath: String) {
        let watch: DirectoryWatch? = lock.withLock {
            guard let watch = watches[relativePath], !watch.isCancelling else {
                return nil
            }
            watch.isCancelling = true
            return watch
        }
        watch?.source.cancel()
    }

    private func finishedCancelling(
        _ watch: DirectoryWatch,
        relativePath: String
    ) {
        lock.withLock {
            if watches[relativePath] === watch {
                watches.removeValue(forKey: relativePath)
            }
        }
    }

    private func scheduleCoalescedChange() {
        lock.lock()
        guard !watches.isEmpty else {
            lock.unlock()
            return
        }
        let now = DispatchTime.now()
        if !pendingChange {
            firstPendingChangeAt = now
        }
        pendingChange = true
        coalesceGeneration &+= 1
        let generation = coalesceGeneration
        pendingCoalesce?.cancel()
        let work = DispatchWorkItem { [weak self] in
            self?.emitCoalesced(generation: generation)
        }
        pendingCoalesce = work
        let trailingDeadline = now + coalesceDelay
        let maximumDeadline = (firstPendingChangeAt ?? now)
            + Self.maxCoalesceWait
        let deadline = min(trailingDeadline, maximumDeadline)
        lock.unlock()

        queue.asyncAfter(deadline: deadline, execute: work)
    }

    private func emitCoalesced(generation: UInt64) {
        let currentContinuations: [AsyncStream<Void>.Continuation]? = lock.withLock {
            guard generation == coalesceGeneration, pendingChange else {
                return nil
            }
            pendingChange = false
            firstPendingChangeAt = nil
            pendingCoalesce = nil
            return Array(continuations.values)
        }
        guard let currentContinuations else { return }
        for continuation in currentContinuations {
            continuation.yield(())
        }
    }

    private func emitPoll(generation: UInt64) {
        let currentContinuations: [AsyncStream<Void>.Continuation]? = lock.withLock {
            guard generation == pollingGeneration, pollingTask != nil else {
                return nil
            }
            return Array(continuations.values)
        }
        guard let currentContinuations else { return }
        for continuation in currentContinuations {
            continuation.yield(())
        }
    }

    private func removeContinuation(_ consumerID: UInt64) {
        lock.withLock {
            _ = continuations.removeValue(forKey: consumerID)
        }
    }

    private static func seconds(_ duration: Duration) -> Double {
        let components = duration.components
        let value = Double(components.seconds)
            + Double(components.attoseconds) / 1_000_000_000_000_000_000
        return max(0, value)
    }
}
