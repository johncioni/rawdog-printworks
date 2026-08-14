import XCTest
@testable import PrintworksCore

final class DebouncerTests: XCTestCase {
    func testOnlyLastScheduledActionRuns() async throws {
        let debouncer = Debouncer(delay: .milliseconds(50))
        nonisolated(unsafe) var fired: [Int] = []
        debouncer.schedule { fired.append(1) }
        debouncer.schedule { fired.append(2) }
        try await Task.sleep(for: .milliseconds(150))
        XCTAssertEqual(fired, [2])
    }

    func testFlushRunsPendingImmediately() async throws {
        let debouncer = Debouncer(delay: .seconds(60))
        nonisolated(unsafe) var fired = 0
        debouncer.schedule { fired += 1 }
        XCTAssertTrue(debouncer.hasPending)
        await debouncer.flush()
        XCTAssertEqual(fired, 1)
        XCTAssertFalse(debouncer.hasPending)
    }
}
