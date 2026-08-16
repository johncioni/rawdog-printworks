import XCTest
@testable import PrintworksCore

final class DebouncerTests: XCTestCase {
    actor ActionRecorder {
        private var values: [Int] = []

        func record(_ value: Int) { values.append(value) }
        func snapshot() -> [Int] { values }
    }

    func testOnlyLastScheduledActionRuns() async {
        let debouncer = Debouncer(delay: .milliseconds(50))
        let recorder = ActionRecorder()
        let first = debouncer.schedule { await recorder.record(1) }
        let second = debouncer.schedule { await recorder.record(2) }

        await first.value
        await second.value

        let values = await recorder.snapshot()
        XCTAssertEqual(values, [2])
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

    func testScheduledActionDoesNotRunInCancelledTask() async {
        let debouncer = Debouncer(delay: .seconds(60))
        let recorder = ActionRecorder()

        let scheduled = debouncer.schedule { await recorder.record(1) }
        XCTAssertTrue(debouncer.hasPending)
        scheduled.cancel()
        await scheduled.value

        let values = await recorder.snapshot()
        XCTAssertEqual(values, [])
        XCTAssertFalse(debouncer.hasPending)
    }
}
