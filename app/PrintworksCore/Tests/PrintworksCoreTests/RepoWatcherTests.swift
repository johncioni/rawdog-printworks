import Darwin
import XCTest
@testable import PrintworksCore

final class RepoWatcherTests: XCTestCase {
    func testCoalescedChangeEmission() async throws {
        let repo = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
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
        let first = await withTimeout(seconds: 2) { await iterator.next() }
        XCTAssertNotNil(first)

        // Quiet period, then one more write → second emission
        try await Task.sleep(for: .milliseconds(300))
        try Data("y".utf8).write(
            to: repo.appendingPathComponent("sidecars/P1_bw.pp3"))
        let second = await withTimeout(seconds: 2) { await iterator.next() }
        XCTAssertNotNil(second)

        // Nested review-input dirs are covered (kqueue is non-recursive,
        // so these have their own sources): a style edit must emit.
        try await Task.sleep(for: .milliseconds(300))
        try Data("[Exposure]\n".utf8).write(
            to: repo.appendingPathComponent("config/styles/natural.pp3"))
        let third = await withTimeout(seconds: 2) { await iterator.next() }
        XCTAssertNotNil(third)

        // A publish (new directory under Output/photos) must emit.
        try await Task.sleep(for: .milliseconds(300))
        try FileManager.default.createDirectory(
            at: repo.appendingPathComponent("Output/photos/P1"),
            withIntermediateDirectories: true)
        let fourth = await withTimeout(seconds: 2) { await iterator.next() }
        XCTAssertNotNil(fourth)
    }

    func testPollingEmitsRepeatedlyAndStops() async {
        let repo = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
        let watcher = RepoWatcher(repo: repo)
        nonisolated(unsafe) var iterator = watcher.changes.makeAsyncIterator()

        watcher.startPolling(interval: .milliseconds(40))
        let first = await withTimeout(seconds: 1) { await iterator.next() }
        let second = await withTimeout(seconds: 1) { await iterator.next() }
        XCTAssertNotNil(first)
        XCTAssertNotNil(second)

        watcher.stopPolling()
        let afterStop = await withTimeout(seconds: 0.25) {
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
        defer { try? FileManager.default.removeItem(at: repo) }
        let watcher = RepoWatcher(repo: repo, coalesce: .milliseconds(40))
        watcher.start()
        defer { watcher.stop() }
        nonisolated(unsafe) var iterator = watcher.changes.makeAsyncIterator()

        let previews = repo.appendingPathComponent("previews")
        try FileManager.default.createDirectory(at: previews,
                                                withIntermediateDirectories: true)
        watcher.start()
        try Data("preview".utf8).write(
            to: previews.appendingPathComponent("P1_natural_preview.jpg"))

        let change = await withTimeout(seconds: 1) { await iterator.next() }
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
        let descriptors = watcher.openFileDescriptors
        XCTAssertEqual(descriptors.count, 1)

        watcher.stop()
        watcher.stop()
        for descriptor in descriptors {
            errno = 0
            XCTAssertEqual(fcntl(descriptor, F_GETFD), -1)
            XCTAssertEqual(errno, EBADF)
        }
        XCTAssertTrue(watcher.openFileDescriptors.isEmpty)

        nonisolated(unsafe) var iterator = watcher.changes.makeAsyncIterator()
        try Data("after stop".utf8).write(
            to: recipes.appendingPathComponent("P1.yaml"))
        let change = await withTimeout(seconds: 0.25) {
            await iterator.next()
        }
        XCTAssertNil(change)
    }
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
