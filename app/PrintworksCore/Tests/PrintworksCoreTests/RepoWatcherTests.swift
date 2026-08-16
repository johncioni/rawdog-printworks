import XCTest
@testable import PrintworksCore

final class RepoWatcherTests: XCTestCase {
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

    func testEffectiveCoalesceDelayReflectsDefaultAndInjectedDuration() {
        let repo = URL(fileURLWithPath: "/unused")

        XCTAssertEqual(RepoWatcher(repo: repo).effectiveCoalesceDelay, 0.5)
        XCTAssertEqual(
            RepoWatcher(repo: repo, coalesce: .milliseconds(200))
                .effectiveCoalesceDelay,
            0.2)
    }

    func testCoalescedChangeEmission() async throws {
        let repo = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
        defer { try? FileManager.default.removeItem(at: repo) }
        for dir in ["Input", "previews", "sidecars", "recipes",
                    "config/styles", "config/lab-profiles",
                    "config/rawtherapee-seed", "Output/photos", "run"] {
            try FileManager.default.createDirectory(
                at: repo.appendingPathComponent(dir),
                withIntermediateDirectories: true)
        }
        let watcher = RepoWatcher(repo: repo, coalesce: .milliseconds(100))
        watcher.start()
        defer { watcher.stop() }
        nonisolated(unsafe) var iterator = watcher.changes.makeAsyncIterator()

        // Burst of writes → exactly one coalesced emission
        for i in 0..<5 {
            try Data("x\(i)".utf8).write(
                to: repo.appendingPathComponent("recipes/P\(i).yaml"))
        }
        let first: Void? = await withTimeout(seconds: 2) { await iterator.next() }
        XCTAssertNotNil(first)

        // Quiet period, then one more write → second emission
        try await Task.sleep(for: .milliseconds(300))
        try Data("y".utf8).write(
            to: repo.appendingPathComponent("sidecars/P1_bw.pp3"))
        let second: Void? = await withTimeout(seconds: 2) { await iterator.next() }
        XCTAssertNotNil(second)

        // Nested review-input dirs are covered (kqueue is non-recursive,
        // so these have their own sources): a style edit must emit.
        try await Task.sleep(for: .milliseconds(300))
        try Data("[Exposure]\n".utf8).write(
            to: repo.appendingPathComponent("config/styles/natural.pp3"))
        let third: Void? = await withTimeout(seconds: 2) { await iterator.next() }
        XCTAssertNotNil(third)

        // A publish (new directory under Output/photos) must emit.
        try await Task.sleep(for: .milliseconds(300))
        try FileManager.default.createDirectory(
            at: repo.appendingPathComponent("Output/photos/P1"),
            withIntermediateDirectories: true)
        let fourth: Void? = await withTimeout(seconds: 2) { await iterator.next() }
        XCTAssertNotNil(fourth)
    }

    func testBurstIsEmittedExactlyOnceAfterCoalesceDelay() async throws {
        let repo = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
        let recipes = repo.appendingPathComponent("recipes")
        try FileManager.default.createDirectory(at: recipes,
                                                withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: repo) }

        let watcher = RepoWatcher(repo: repo, coalesce: .milliseconds(200))
        let counter = ChangeCounter()
        let changes = watcher.changes
        let earlyChanges = watcher.changes
        let consumer = Task {
            for await _ in changes {
                await counter.increment()
            }
        }
        watcher.start()

        for index in 0..<30 {
            try Data("event-\(index)".utf8).write(
                to: recipes.appendingPathComponent("P\(index).yaml"))
            try await Task.sleep(for: .milliseconds(10))
        }

        // Race the change stream against a positive window-elapsed signal.
        // A bare sleep followed by a counter read can pass when both the
        // producer and consumer are delayed by a busy scheduler.
        let earlyResult = await firstChangeOrWindowElapsed(
            earlyChanges,
            window: .milliseconds(50)
        )
        XCTAssertEqual(earlyResult, .windowElapsed,
                       "a trailing coalesce must not emit immediately")
        let beforeDelay = await counter.current()
        XCTAssertEqual(beforeDelay, 0,
                       "a trailing coalesce must not emit immediately")

        // Asserting ARRIVAL must not be a fixed wait. The emission is bounded
        // by RepoWatcher's own contract — no later than the first change plus
        // maxCoalesceWait (2s) — not by 350ms from the last write. Under load,
        // kqueue delivery and asyncAfter both slip, so a fixed margin fails on
        // a busy machine while the watcher is behaving correctly. Poll instead.
        let deadline = ContinuousClock.now + .seconds(5)
        while await counter.current() < 1, ContinuousClock.now < deadline {
            try await Task.sleep(for: .milliseconds(20))
        }
        let afterDelay = await counter.current()
        XCTAssertEqual(afterDelay, 1,
                       "30 raw writes must collapse to one emission")

        // ...and stay collapsed: no second emission trails the first.
        try await Task.sleep(for: .milliseconds(400))
        let settled = await counter.current()
        XCTAssertEqual(settled, 1,
                       "the burst must emit exactly once, not repeatedly")

        consumer.cancel()
        await consumer.value
        watcher.stop()
    }

    func testEveryWatchedDirectoryEmits() async throws {
        let repo = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
        for directory in Self.watchedDirectories {
            try FileManager.default.createDirectory(
                at: repo.appendingPathComponent(directory),
                withIntermediateDirectories: true)
        }
        defer { try? FileManager.default.removeItem(at: repo) }

        let watcher = RepoWatcher(repo: repo, coalesce: .milliseconds(40))
        watcher.start()
        defer { watcher.stop() }
        nonisolated(unsafe) var iterator = watcher.changes.makeAsyncIterator()

        for (index, directory) in Self.watchedDirectories.enumerated() {
            try Data("probe-\(index)".utf8).write(
                to: repo.appendingPathComponent(directory)
                    .appendingPathComponent("watch-probe-\(index)"))
            let change: Void? = await withTimeout(seconds: 1) {
                await iterator.next()
            }
            XCTAssertNotNil(change, "no emission for \(directory)")
        }
    }

    func testCancellingOneConsumerDoesNotFinishAnother() async throws {
        let repo = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
        let recipes = repo.appendingPathComponent("recipes")
        try FileManager.default.createDirectory(at: recipes,
                                                withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: repo) }

        let watcher = RepoWatcher(repo: repo, coalesce: .milliseconds(40))
        watcher.start()
        defer { watcher.stop() }

        let firstChanges = watcher.changes
        nonisolated(unsafe) var secondIterator =
            watcher.changes.makeAsyncIterator()
        let firstConsumer = Task {
            for await _ in firstChanges {}
        }
        try await Task.sleep(for: .milliseconds(50))
        firstConsumer.cancel()
        await firstConsumer.value

        try Data("after cancellation".utf8).write(
            to: recipes.appendingPathComponent("P1.yaml"))
        let change: Void? = await withTimeout(seconds: 1) {
            await secondIterator.next()
        }
        XCTAssertNotNil(change,
                        "one consumer cancellation must not finish later streams")
    }

    func testStopFinishesConsumerAndFreshStreamWorksAfterRestart() async throws {
        let repo = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
        let recipes = repo.appendingPathComponent("recipes")
        try FileManager.default.createDirectory(at: recipes,
                                                withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: repo) }

        let watcher = RepoWatcher(repo: repo, coalesce: .milliseconds(40))
        watcher.start()
        let loopExited = expectation(description: "consumer loop exited")
        let firstChanges = watcher.changes
        let consumer = Task {
            for await _ in firstChanges {}
            loopExited.fulfill()
        }
        try await Task.sleep(for: .milliseconds(50))

        watcher.stop()
        await fulfillment(of: [loopExited], timeout: 0.5)
        consumer.cancel()
        await consumer.value

        watcher.start()
        defer { watcher.stop() }
        nonisolated(unsafe) var restartedIterator =
            watcher.changes.makeAsyncIterator()
        try Data("after restart".utf8).write(
            to: recipes.appendingPathComponent("P2.yaml"))
        let restartedChange: Void? = await withTimeout(seconds: 1) {
            await restartedIterator.next()
        }
        XCTAssertNotNil(restartedChange,
                        "a fresh stream must deliver after stop/start")
    }

    func testPollingEmitsRepeatedlyAndStops() async {
        let repo = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
        let watcher = RepoWatcher(repo: repo)
        nonisolated(unsafe) var iterator = watcher.changes.makeAsyncIterator()

        watcher.startPolling(interval: .milliseconds(40))
        let first: Void? = await withTimeout(seconds: 1) { await iterator.next() }
        let second: Void? = await withTimeout(seconds: 1) { await iterator.next() }
        XCTAssertNotNil(first)
        XCTAssertNotNil(second)

        watcher.stopPolling()
        let afterStop: Void? = await withTimeout(seconds: 0.25) {
            await iterator.next()
        }
        XCTAssertNil(afterStop)
        watcher.stop()
    }

    func testMissingDirectoryIsRetriedOnLaterStart() async throws {
        let repo = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: repo,
                                                withIntermediateDirectories: true)
        try FileManager.default.createDirectory(
            at: repo.appendingPathComponent("recipes"),
            withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: repo) }
        let watcher = RepoWatcher(repo: repo, coalesce: .milliseconds(40))
        watcher.start()
        XCTAssertEqual(watcher.openFileDescriptors.count, 1)
        defer { watcher.stop() }
        nonisolated(unsafe) var iterator = watcher.changes.makeAsyncIterator()

        let previews = repo.appendingPathComponent("previews")
        try FileManager.default.createDirectory(at: previews,
                                                withIntermediateDirectories: true)
        watcher.start()
        XCTAssertEqual(watcher.openFileDescriptors.count, 2)
        try Data("preview".utf8).write(
            to: previews.appendingPathComponent("P1_natural_preview.jpg"))

        let change: Void? = await withTimeout(seconds: 1) { await iterator.next() }
        XCTAssertNotNil(change)
    }

    func testStopIsIdempotentClosesDescriptorsAndStopsEmissions() async throws {
        let repo = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
        let recipes = repo.appendingPathComponent("recipes")
        try FileManager.default.createDirectory(at: recipes,
                                                withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: repo) }
        let watcher = RepoWatcher(repo: repo, coalesce: .milliseconds(40))
        watcher.start()
        XCTAssertEqual(watcher.openFileDescriptors.count, 1)

        watcher.stop()
        watcher.stop()
        XCTAssertTrue(watcher.openFileDescriptors.isEmpty)

        nonisolated(unsafe) var iterator = watcher.changes.makeAsyncIterator()
        try Data("after stop".utf8).write(
            to: recipes.appendingPathComponent("P1.yaml"))
        let change: Void? = await withTimeout(seconds: 0.25) {
            await iterator.next()
        }
        XCTAssertNil(change)
    }

    func testStopReturnsWhenCalledFromPrivateQueue() async throws {
        let repo = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(
            at: repo.appendingPathComponent("recipes"),
            withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: repo) }

        let watcher = RepoWatcher(repo: repo)
        watcher.start()
        XCTAssertEqual(watcher.openFileDescriptors.count, 1)
        let returned = expectation(description: "stop returned on private queue")

        watcher._runOnPrivateQueueForTesting {
            watcher.stop()
            returned.fulfill()
        }

        await fulfillment(of: [returned], timeout: 0.5)
        let closed = await waitUntil(seconds: 1) {
            watcher.openFileDescriptors.isEmpty
        }
        XCTAssertTrue(closed, "stop should release every watched descriptor")
    }

    func testStartAlreadyInFlightCannotOutliveConcurrentStop() async throws {
        let repo = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
        for directory in Self.watchedDirectories {
            try FileManager.default.createDirectory(
                at: repo.appendingPathComponent(directory),
                withIntermediateDirectories: true)
        }
        defer { try? FileManager.default.removeItem(at: repo) }

        let watcher = RepoWatcher(repo: repo)
        let entered = DispatchSemaphore(value: 0)
        let resumeStart = DispatchSemaphore(value: 0)
        let startTask = Task.detached {
            watcher._startForTesting {
                entered.signal()
                resumeStart.wait()
            }
        }

        XCTAssertEqual(entered.wait(timeout: .now() + 1), .success)
        watcher.stop()
        resumeStart.signal()
        await startTask.value

        XCTAssertTrue(watcher.openFileDescriptors.isEmpty,
                      "a start already in flight must be invalidated by stop")
        watcher.stop()
    }

    func testSustainedChangesEmitBeforeActivityStops() async throws {
        let repo = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
        let run = repo.appendingPathComponent("run")
        try FileManager.default.createDirectory(at: run,
                                                withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: repo) }

        let watcher = RepoWatcher(repo: repo, coalesce: .milliseconds(500))
        let counter = ChangeCounter()
        let changes = watcher.changes
        let consumer = Task {
            for await _ in changes {
                await counter.increment()
            }
        }
        watcher.start()

        for index in 0..<30 {
            try Data("tick-\(index)".utf8).write(
                to: run.appendingPathComponent("tick-\(index)"))
            try await Task.sleep(for: .milliseconds(200))
        }

        let duringActivity = await counter.current()
        XCTAssertGreaterThanOrEqual(
            duringActivity, 2,
            "bounded coalescing must refresh during sustained activity")

        consumer.cancel()
        await consumer.value
        watcher.stop()
    }

    func testVanishedDirectoryIsDiscardedAndRetriedOnlyWhenRequested() async throws {
        let repo = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
        let recipes = repo.appendingPathComponent("recipes")
        try FileManager.default.createDirectory(at: recipes,
                                                withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: repo) }

        let watcher = RepoWatcher(repo: repo, coalesce: .milliseconds(40))
        watcher.start()
        defer { watcher.stop() }
        nonisolated(unsafe) var deletionIterator =
            watcher.changes.makeAsyncIterator()

        try FileManager.default.removeItem(at: recipes)
        let deletionChange: Void? = await withTimeout(seconds: 1) {
            await deletionIterator.next()
        }
        XCTAssertNotNil(deletionChange)
        let discarded = await waitUntil(seconds: 1) {
            watcher.openFileDescriptors.isEmpty
        }
        XCTAssertTrue(discarded, "the vanished directory watch was retained")

        try FileManager.default.createDirectory(at: recipes,
                                                withIntermediateDirectories: true)
        nonisolated(unsafe) var idleIterator =
            watcher.changes.makeAsyncIterator()
        try Data("idle".utf8).write(
            to: recipes.appendingPathComponent("idle.yaml"))
        let idleChange: Void? = await withTimeout(seconds: 0.25) {
            await idleIterator.next()
        }
        XCTAssertNil(idleChange,
                     "idle re-attachment is intentionally not automatic")

        watcher.start()
        nonisolated(unsafe) var retriedIterator =
            watcher.changes.makeAsyncIterator()
        try Data("retried".utf8).write(
            to: recipes.appendingPathComponent("retried.yaml"))
        let retriedChange: Void? = await withTimeout(seconds: 1) {
            await retriedIterator.next()
        }
        XCTAssertNotNil(retriedChange,
                        "explicit start should re-attach the recreated directory")
    }
}

private actor ChangeCounter {
    private var count = 0

    func increment() {
        count += 1
    }

    func current() -> Int {
        count
    }
}

private enum ChangeWindowResult: Equatable, Sendable {
    case change
    case streamFinished
    case windowElapsed
}

private func firstChangeOrWindowElapsed(
    _ changes: AsyncStream<Void>,
    window: Duration
) async -> ChangeWindowResult {
    await withTaskGroup(of: ChangeWindowResult.self) { group in
        group.addTask {
            var iterator = changes.makeAsyncIterator()
            return await iterator.next() == nil ? .streamFinished : .change
        }
        group.addTask {
            try? await Task.sleep(for: window)
            return .windowElapsed
        }
        let result = await group.next() ?? .streamFinished
        group.cancelAll()
        return result
    }
}

private func waitUntil(seconds: Double,
                       condition: () -> Bool) async -> Bool {
    let attempts = max(1, Int(seconds / 0.01))
    for _ in 0..<attempts {
        if condition() { return true }
        try? await Task.sleep(for: .milliseconds(10))
    }
    return condition()
}

func withTimeout<T: Sendable>(seconds: Double,
                              _ body: @escaping @Sendable () async -> T?)
async -> T? {
    await withTaskGroup(of: T?.self) { group in
        group.addTask { await body() }
        group.addTask {
            try? await Task.sleep(for: .seconds(seconds)); return nil
        }
        let result = await group.next() ?? nil
        group.cancelAll()
        return result
    }
}
