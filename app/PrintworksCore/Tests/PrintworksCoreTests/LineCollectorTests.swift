import XCTest
@testable import PrintworksCore

/// Direct tests of `LineCollector`'s chunk-reassembly logic, independent of
/// any FileHandle/process plumbing — per the brief's Step 3 prose ("feed
/// chunks 'ab', 'c\nde', 'f\n' -> allLines == ['abc', 'def'] after finish
/// of an empty handle; a trailing unterminated 'partial' flushes as a
/// final line on finish"), which was never written as an actual test.
final class LineCollectorTests: XCTestCase {
    func testReassemblesLinesAcrossChunkBoundaries() {
        let collector = LineCollector()
        _ = collector.completeLines(appending: Data("ab".utf8))
        _ = collector.completeLines(appending: Data("c\nde".utf8))
        _ = collector.completeLines(appending: Data("f\n".utf8))
        XCTAssertEqual(collector.allLines, ["abc", "def"])
    }

    func testFlushRemainderEmitsTrailingPartialLine() {
        // Matches the brief's "a trailing unterminated 'partial' flushes as
        // a final line on finish" case. `flushRemainder()` (formerly
        // `finish(_ handle:)`) no longer takes a FileHandle: review round 1
        // Finding 1's fix moved pipe-reading out of LineCollector entirely
        // (into PipelineClient.drain, the pipe's single sequential reader),
        // so this is now a pure buffering test with no I/O involved — the
        // reader is responsible for calling `flushRemainder()` once, after
        // it observes EOF.
        let collector = LineCollector()
        _ = collector.completeLines(appending: Data("partial".utf8))
        collector.flushRemainder()
        XCTAssertEqual(collector.allLines, ["partial"])
    }
}
