### Task 2: Contract models + golden-fixture decoding

**Files:**
- Modify: `app/PrintworksCore/Sources/PrintworksCore/Contract.swift` (replace placeholder)
- Test: `app/PrintworksCore/Tests/PrintworksCoreTests/ContractTests.swift`

**Interfaces:**
- Produces (names are binding for all later tasks; all `public`, all `Codable & Sendable & Equatable`):
  - `PipelineErrorInfo { code: String; message: String }`
  - `Envelope<R: Codable & Sendable & Equatable> { ok: Bool; result: R?; error: PipelineErrorInfo? }`
  - `ProgressEvent { event: String; stem: String?; stage: String?; index: Int?; total: Int?; detail: String? }`
  - `ToolchainIssue { name: String?; problem: String? }`, `ToolchainStatus { ok: Bool; failures: [ToolchainIssue] }`
  - `LockStatus { held: Bool; stale: Bool; pid: Int? }`
  - `Control { value: Double?; source: String }`, `StyleAdjustments { temperature: Control; exposure: Control }`
  - `CropWindow { x: Double; y: Double; w: Double; h: Double; source: String? }`
  - `PublishedInfo { version: String?; path: String?; artifactCount: Int? }`
  - `PhotoStatus { stem, state: String; deliveryId, ingestedAt: String?; reviewRevision: String; previews: [String: String?]; previewHashes: [String: String?]; stalePreviews: [String]; adjustments: [String: StyleAdjustments]; crops: [String: CropWindow]; expressionAudit: [String]; published: PublishedInfo }`
  - `StatusSnapshot { repo: String; toolchain: ToolchainStatus; lock: LockStatus; styles: [String]; photos: [PhotoStatus] }`
  - `AdjustResult { stem, style, preview: String; temperature, exposure: Control; reviewRevisionBefore, reviewRevisionAfter: String }`
  - `CropsResult { stem: String; basis: String?; windows: [String: CropWindow] }` — `basis` is `null` when every window is persisted (no suggestion ran; Plan 1 Task 9)
  - `ApproveResult { stem, state, fingerprint: String }`
  - `FileNote { file: String; reason: String }`, `FileFailure { file: String; code: String; message: String }`
  - `IngestResult { ingested: [String]; skipped: [FileNote]; conflicts: [FileNote]; failed: [FileFailure] }`
  - `PublishedPhoto { stem, version: String; artifactCount: Int }`, `AdvancedPhoto { stem, state: String }`, `StemFailure { stem, code, message: String }`
  - `RunResult { published: [PublishedPhoto]; advanced: [AdvancedPhoto]; failed: [StemFailure] }`
  - `ContractDecoder.make() -> JSONDecoder` — `keyDecodingStrategy = .convertFromSnakeCase`.
  - `repoFixturesURL()` (test helper): `URL(fileURLWithPath: #filePath)` ascended to the repo root (`…/app/PrintworksCore/Tests/PrintworksCoreTests/X.swift` → 5 `deletingLastPathComponent()` calls) + `tests/fixtures/json_contract`.

- [ ] **Step 1: Write the failing tests**

```swift
import XCTest
@testable import PrintworksCore

final class ContractTests: XCTestCase {
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
}
```

- [ ] **Step 2: Run to verify failure** — `swift test --package-path app/PrintworksCore` → FAIL (types missing).

- [ ] **Step 3: Implement `Contract.swift`** — the structs exactly as the Interfaces block names them, e.g.:

```swift
import Foundation

public struct PipelineErrorInfo: Codable, Sendable, Equatable {
    public let code: String
    public let message: String
}

public struct Envelope<R: Codable & Sendable & Equatable>: Codable, Sendable, Equatable {
    public let ok: Bool
    public let result: R?
    public let error: PipelineErrorInfo?
}

public enum ContractDecoder {
    public static func make() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }
}
// …remaining structs per the Interfaces block, all Codable/Sendable/Equatable,
// let-properties, no custom CodingKeys (snake_case handled by the decoder).
```

Write every struct listed in Interfaces; no others. `previews`/`previewHashes` use `[String: String?]` — JSONDecoder decodes JSON `null` map values into `Optional.none` correctly.

- [ ] **Step 4: Run to verify pass** — `swift test --package-path app/PrintworksCore` → PASS.

- [ ] **Step 5: Commit**

```bash
git add app/PrintworksCore
git commit -m "feat(app): contract models decoding the pipeline golden fixtures"
```

---

