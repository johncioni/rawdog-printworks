import Foundation
import XCTest
@testable import PrintworksCore

final class PreviewImageCacheTests: XCTestCase {
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
