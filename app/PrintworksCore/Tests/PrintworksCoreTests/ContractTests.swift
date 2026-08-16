import XCTest
@testable import PrintworksCore

final class ContractTests: XCTestCase {
    func testPackageBuilds() { XCTAssertEqual(Contract.version, 1) }

    private func fixture(_ name: String) throws -> Data {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()  // PrintworksCoreTests
            .deletingLastPathComponent()  // Tests
            .deletingLastPathComponent()  // PrintworksCore
            .deletingLastPathComponent()  // app
            .deletingLastPathComponent()  // repo root
            .appendingPathComponent("tests/fixtures/json_contract")
            .appendingPathComponent(name)
        return try Data(contentsOf: url)
    }

    func testDecodesEveryStatusFixture() throws {
        for name in ["status_empty.json", "status_ingested.json"] {
            let env = try ContractDecoder.make().decode(
                Envelope<StatusSnapshot>.self, from: fixture(name))
            XCTAssertTrue(env.ok, name)
            XCTAssertNotNil(env.result, name)
        }
    }

    func testStatusFieldsRoundTrip() throws {
        let env = try ContractDecoder.make().decode(
            Envelope<StatusSnapshot>.self, from: fixture("status_ingested.json"))
        let photo = try XCTUnwrap(env.result?.photos.first)
        XCTAssertFalse(photo.reviewRevision.isEmpty)
        XCTAssertEqual(Set(photo.adjustments.keys).isSubset(
            of: Set(env.result!.styles)), true)
        XCTAssertNotNil(photo.adjustments.values.first?.temperature.source)
    }

    func testCropRetryTokenTracksReadinessButNotReviewRevision() {
        func photo(state: String, revision: String,
                   previews: [String: String?] = [:]) -> PhotoStatus {
            PhotoStatus(
                stem: "P1", state: state, deliveryId: "d1", ingestedAt: nil,
                reviewRevision: revision, previews: previews, previewHashes: [:],
                stalePreviews: [], adjustments: [:], crops: [:],
                expressionAudit: [], published: PublishedInfo(
                    version: nil, path: nil, artifactCount: nil))
        }

        let waiting = photo(state: "ingested", revision: "r1")
        let revisionOnly = photo(state: "ingested", revision: "r2")
        let stateReady = photo(state: "review_required", revision: "r2")
        let previewReady = photo(
            state: "ingested", revision: "r2", previews: ["natural": "P1.jpg"])

        XCTAssertEqual(waiting.cropRetryToken, revisionOnly.cropRetryToken)
        XCTAssertNotEqual(waiting.cropRetryToken, stateReady.cropRetryToken)
        XCTAssertNotEqual(waiting.cropRetryToken, previewReady.cropRetryToken)
    }

    func testNeedsReviewCountUsesTypedAppearanceCase() {
        let states = [
            "ingested", "preview_ready", "review_required", "approved",
            "rendered", "verified",
        ]

        XCTAssertEqual(PhotoStateAppearance.needsReviewCount(states: states), 2)
        XCTAssertEqual(PhotoStateAppearance(state: "preview_ready"),
                       .needsReview)
        XCTAssertEqual(PhotoStateAppearance(state: "review_required"),
                       .needsReview)
        XCTAssertNotEqual(PhotoStateAppearance(state: "verified"),
                          .needsReview)
    }

    func testDecodesAdjustCropsApproveIngestRun() throws {
        _ = try ContractDecoder.make().decode(
            Envelope<AdjustResult>.self, from: fixture("adjust_ok.json"))
        _ = try ContractDecoder.make().decode(
            Envelope<CropsResult>.self, from: fixture("crops_suggested.json"))
        _ = try ContractDecoder.make().decode(
            Envelope<IngestResult>.self, from: fixture("ingest_result.json"))
        let run = try ContractDecoder.make().decode(
            Envelope<RunResult>.self, from: fixture("run_partial_failure.json"))
        XCTAssertFalse(run.ok)                    // PARTIAL_FAILURE
        XCTAssertNotNil(run.result)               // result attached on failure
        XCTAssertEqual(run.error?.code, "PARTIAL_FAILURE")
    }

    func testErrorEnvelopeDecodes() throws {
        let env = try ContractDecoder.make().decode(
            Envelope<StatusSnapshot>.self, from: fixture("envelope_lock_held.json"))
        XCTAssertFalse(env.ok)
        XCTAssertEqual(env.error?.code, "LOCK_HELD")
    }

    func testStaleReviewFixture() throws {
        let env = try ContractDecoder.make().decode(
            Envelope<ApproveResult>.self, from: fixture("approve_stale_review.json"))
        XCTAssertEqual(env.error?.code, "STALE_REVIEW")
    }

    func testAdjustStreamFixtureDecodesLineByLine() throws {
        // adjust emits NO progress events (verified in Plan 1 Task 13):
        // its stream fixture is the single envelope line, equal to
        // adjust_ok.json. The multi-event stream contract lives in
        // run_stream.ndjson (next test).
        let lines = String(decoding: try fixture("adjust_stream.ndjson"),
                           as: UTF8.self)
            .split(separator: "\n").map(String.init)
        XCTAssertFalse(lines.isEmpty)
        let decoder = ContractDecoder.make()
        let final = try decoder.decode(Envelope<AdjustResult>.self,
                                       from: Data(lines.last!.utf8))
        let canonical = try decoder.decode(Envelope<AdjustResult>.self,
                                           from: fixture("adjust_ok.json"))
        XCTAssertEqual(final, canonical)
    }

    func testRunStreamFixtureIsTheStreamingContract() throws {
        // run_stream.ndjson (Plan 1 Task 13, additive) carries the real
        // multi-event stream: stage + progress event lines, then the final
        // envelope — this is the fixture PipelineClient's streaming parser
        // is validated against.
        let lines = String(decoding: try fixture("run_stream.ndjson"),
                           as: UTF8.self)
            .split(separator: "\n").map(String.init)
        XCTAssertGreaterThan(lines.count, 1, "must contain events + envelope")
        let decoder = ContractDecoder.make()
        for line in lines.dropLast() {
            XCTAssertNoThrow(try decoder.decode(ProgressEvent.self,
                                                from: Data(line.utf8)), line)
        }
        XCTAssertNoThrow(try decoder.decode(Envelope<RunResult>.self,
                                            from: Data(lines.last!.utf8)))
    }

    /// `run_partial_failure.json` was updated (ahead of this task) to carry
    /// two DIFFERENT failure codes in the same `failed[]` array
    /// (VERIFY_FAILED and RENDER_FAILED), specifically so a `code` model
    /// that only recognises one value seen in one fixture gets caught here.
    func testRunPartialFailureCarriesDistinctFailureCodes() throws {
        let run = try ContractDecoder.make().decode(
            Envelope<RunResult>.self, from: fixture("run_partial_failure.json"))
        let codes = Set((run.result?.failed ?? []).map(\.code))
        XCTAssertEqual(codes, ["VERIFY_FAILED", "RENDER_FAILED"])
    }

    /// The pipeline can attach any of these ten codes to a `PipelineErrorInfo`,
    /// a `StemFailure`, or a `FileFailure` — and may add more in the future.
    /// `code` is modeled as a plain `String` (not a closed enum inferred from
    /// whichever values happen to appear in today's fixtures), so every known
    /// code decodes and an unrecognised future code does not crash the decode.
    func testAllKnownAndFutureFailureCodesDecode() throws {
        let knownCodes = [
            "LOCK_HELD", "TOOLCHAIN_FAILED", "RENDER_FAILED", "VERIFY_FAILED",
            "INVALID_STATE", "STALE_REVIEW", "PARTIAL_FAILURE", "NOT_FOUND",
            "BAD_INPUT", "INTERNAL",
        ]
        let decoder = ContractDecoder.make()
        for code in knownCodes + ["SOME_FUTURE_CODE_NOT_YET_INVENTED"] {
            let errorInfo = try decoder.decode(
                PipelineErrorInfo.self,
                from: Data(#"{"code":"\#(code)","message":"m"}"#.utf8))
            XCTAssertEqual(errorInfo.code, code)

            let stemFailure = try decoder.decode(
                StemFailure.self,
                from: Data(#"{"stem":"P1","code":"\#(code)","message":"m"}"#.utf8))
            XCTAssertEqual(stemFailure.code, code)

            let fileFailure = try decoder.decode(
                FileFailure.self,
                from: Data(#"{"file":"P1.RW2","code":"\#(code)","message":"m"}"#.utf8))
            XCTAssertEqual(fileFailure.code, code)
        }
    }
}
