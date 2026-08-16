import Foundation
import XCTest
@testable import PrintworksCore

final class PreviewImageCacheTests: XCTestCase {
    func testConcurrentPreviewDecodesAreBoundedAndAllComplete() async {
        let limit = 1
        let requestCount = 4
        let probe = ConcurrencyBoundProbe(overLimitStartCount: limit + 1)
        let cache = PreviewImageCache(maxConcurrentDecodes: limit,
                                      decoder: probe.decode)
        let requests = (0..<requestCount).map { index in
            Task {
                await cache.image(
                    contentHash: "image-\(index)",
                    url: URL(fileURLWithPath: "/image-\(index).jpg"),
                    maxPixelSize: 512)
            }
        }

        let overLimitStarted = await Task.detached {
            probe.waitForOverLimitStart()
        }.value
        for _ in 0..<requestCount { probe.release.signal() }
        for request in requests { _ = await request.value }

        XCTAssertEqual(overLimitStarted, .timedOut,
                       "a decode beyond the configured limit must wait")
        XCTAssertLessThanOrEqual(probe.maxConcurrent, limit)
        XCTAssertEqual(probe.startCount, requestCount)
        XCTAssertEqual(probe.completionCount, requestCount)
    }

    func testUnrelatedPreviewDecodesCanOverlap() async {
        let probe = DecodeProbe()
        let cache = PreviewImageCache(decoder: probe.decode)
        let first = Task {
            await cache.image(
                contentHash: "first", url: URL(fileURLWithPath: "/first.jpg"),
                maxPixelSize: 512)
        }
        let second = Task {
            await cache.image(
                contentHash: "second", url: URL(fileURLWithPath: "/second.jpg"),
                maxPixelSize: 512)
        }

        let overlap = await Task.detached {
            probe.waitForBothStarted()
        }.value
        probe.release.signal()
        probe.release.signal()
        _ = await (first.value, second.value)

        XCTAssertEqual(overlap, .success,
                       "one blocked decode must not serialize another key")
    }
}

private final class ConcurrencyBoundProbe: @unchecked Sendable {
    let release = DispatchSemaphore(value: 0)
    private let overLimitStarted = DispatchSemaphore(value: 0)
    private let overLimitStartCount: Int
    private let lock = NSLock()
    private var starts = 0
    private var completions = 0
    private var active = 0
    private var peak = 0

    init(overLimitStartCount: Int) {
        self.overLimitStartCount = overLimitStartCount
    }

    var startCount: Int { lock.withLock { starts } }
    var completionCount: Int { lock.withLock { completions } }
    var maxConcurrent: Int { lock.withLock { peak } }

    func waitForOverLimitStart() -> DispatchTimeoutResult {
        overLimitStarted.wait(timeout: .now() + 1)
    }

    func decode(_ url: URL, _ maxPixelSize: Int) -> DownsampledPreview? {
        lock.withLock {
            starts += 1
            active += 1
            peak = max(peak, active)
            if starts == overLimitStartCount { overLimitStarted.signal() }
        }
        release.wait()
        lock.withLock {
            active -= 1
            completions += 1
        }
        return nil
    }
}

private final class DecodeProbe: @unchecked Sendable {
    let bothStarted = DispatchSemaphore(value: 0)
    let release = DispatchSemaphore(value: 0)
    private let lock = NSLock()
    private var starts = 0

    func waitForBothStarted() -> DispatchTimeoutResult {
        bothStarted.wait(timeout: .now() + 1)
    }

    func decode(_ url: URL, _ maxPixelSize: Int) -> DownsampledPreview? {
        lock.withLock {
            starts += 1
            if starts == 2 { bothStarted.signal() }
        }
        release.wait()
        return nil
    }
}
