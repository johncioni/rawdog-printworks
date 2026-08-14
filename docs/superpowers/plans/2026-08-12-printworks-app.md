# RAWdog Printworks App Implementation Plan (App Plan 2 of 2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the RAWdog Printworks macOS app (spec `docs/superpowers/specs/2026-08-12-macos-app-design.md` §4.1, §5–§8) on top of the JSON interface delivered by Plan 1 (`2026-08-12-pipeline-json-interface.md`).

**Architecture:** Two-layer Swift codebase: `app/PrintworksCore` — a local Swift package holding every testable unit (contract models, `PipelineClient` actor, `AppModel`, watcher, crop/debounce math) exercised by fast `swift test`; `app/RAWdogPrintworks` — a thin XcodeGen-managed app target holding SwiftUI views and wiring, verified by `xcodebuild build` plus the visual-QA gate. The app never computes pipeline logic; it renders `status --json` and shells out for every mutation.

**Tech Stack:** Swift 6.2.4, SwiftUI, macOS 15 (Sequoia) minimum, Xcode 26.3, XcodeGen (installed in Task 1), XCTest. No third-party UI dependencies.

## Global Constraints (from spec §2/§5, binding on every task)

- macOS 15 minimum; SwiftUI; no third-party UI dependencies (XcodeGen is a build-time tool, not a dependency).
- No pipeline logic in Swift, no repo writes from Swift. The only Swift-written file is the temp review-file, created **outside** the repo (`FileManager.default.temporaryDirectory`).
- Subprocess environment (spec §4.1): `currentDirectoryURL` = repo; python by absolute path from Settings; `PATH` = `/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin` exactly; argv only, never a shell.
- Every mutating action follows spawn → stream events → envelope → `status --json` refresh; the UI is never updated speculatively.
- Canonical CLI spellings (Plan 1, JSON-mode flagged forms — the app always uses these): `status --json` · `ingest --from <paths…> --delivery-id <uuid> --json` · `preview --stem S --style Y --json` · `adjust --stem S --style Y [--temperature K] [--exposure EV] [--reset] --json` · `crops --stem S --json` · `approve --stem S --review-file <path> --json` · `run [--stem S] [--force] --json`.
- On any `ok: false` envelope that carries a `result` (aggregate commands), the model processes the `result` first (publications/ingests really happened), then surfaces the error; every action ends with a `status` refresh on success AND failure paths.
- Visual language: window base `#0A0A0B`, review canvas pure black, panels `#141416`, hairlines `#232326`, accent amber `#E8A849`; `.ultraThinMaterial` sidebar; dark-only via `.preferredColorScheme(.dark)`.
- Canvas image cache is keyed by preview **content hash** from status, never mtime/URL cache.
- Quality gate before reporting any task complete: `swift test --package-path app/PrintworksCore` AND (from Task 1 on) `xcodebuild -project app/RAWdogPrintworks/RAWdogPrintworks.xcodeproj -scheme RAWdogPrintworks build` succeed.
- Final done-criteria includes visual QA screenshots (Task 11) — green tests alone are insufficient.

## File Structure

```
app/PrintworksCore/Package.swift
app/PrintworksCore/Sources/PrintworksCore/
  Contract.swift        # Codable contract types (single source of truth for names)
  PipelineClient.swift  # actor: spawn, NDJSON stream, envelope decode, FIFO
  AppModel.swift        # @Observable state tree, drafts, busy pill, actions
  RepoWatcher.swift     # kqueue DispatchSource watcher, coalescing, poll fallback
  CropMath.swift        # pure nudge/clamp math
  Debouncer.swift       # cancellable async debounce (injectable delay)
app/PrintworksCore/Tests/PrintworksCoreTests/
  ContractTests.swift PipelineClientTests.swift AppModelTests.swift
  CropMathTests.swift DebouncerTests.swift SmokeTests.swift
app/RAWdogPrintworks/project.yml            # XcodeGen spec (committed)
app/RAWdogPrintworks/RAWdogPrintworks.xcodeproj  # generated, committed
app/RAWdogPrintworks/Sources/
  PrintworksApp.swift Theme.swift MainWindow.swift SidebarView.swift
  GridView.swift ReviewView.swift CompareView.swift CropOverlayView.swift
  InspectorView.swift IngestBanner.swift SettingsSheet.swift ErrorBanner.swift
scripts/build-app.sh                        # Release build + ad-hoc codesign
```

Golden fixtures are read directly from `tests/fixtures/json_contract/` via a `#filePath`-derived repo-root path in `ContractTests.swift` — no copies, so contract drift fails the Swift tests immediately.

**Execution prerequisite:** Plan 1 Task 13 must be complete (fixtures committed) before Task 2 of this plan; Tasks 1 and 3–4 have no Plan 1 dependency.

---

### Task 1: Scaffold — PrintworksCore package + XcodeGen app target

**Files:**
- Create: `app/PrintworksCore/Package.swift`, `app/PrintworksCore/Sources/PrintworksCore/Contract.swift` (placeholder type only), `app/PrintworksCore/Tests/PrintworksCoreTests/ContractTests.swift` (one trivial test), `app/RAWdogPrintworks/project.yml`, `app/RAWdogPrintworks/Sources/PrintworksApp.swift`, `app/RAWdogPrintworks/Sources/Theme.swift`
- Modify: `.gitignore` (add `app/**/build/`, `app/**/.build/`, `app/**/xcuserdata/`)

**Interfaces:**
- Produces: `Theme` enum consumed by every view task — `Theme.windowBase` (#0A0A0B), `Theme.canvas` (pure black), `Theme.panel` (#141416), `Theme.hairline` (#232326), `Theme.accent` (#E8A849), `Theme.statusPublished` (green), `Theme.statusReview` (= accent), `Theme.statusIngested` (gray).
- Build commands used by every later task (quality gate).

- [ ] **Step 1: Install XcodeGen** — `brew install xcodegen` (verify: `xcodegen --version`).

- [ ] **Step 2: Create the package**

```swift
// app/PrintworksCore/Package.swift
// swift-tools-version:6.0
import PackageDescription

let package = Package(
    name: "PrintworksCore",
    platforms: [.macOS(.v15)],
    products: [.library(name: "PrintworksCore", targets: ["PrintworksCore"])],
    targets: [
        .target(name: "PrintworksCore"),
        .testTarget(name: "PrintworksCoreTests", dependencies: ["PrintworksCore"]),
    ]
)
```

```swift
// Sources/PrintworksCore/Contract.swift (placeholder; Task 2 fills it)
public enum Contract { public static let version = 1 }
```

```swift
// Tests/PrintworksCoreTests/ContractTests.swift
import XCTest
@testable import PrintworksCore

final class ContractTests: XCTestCase {
    func testPackageBuilds() { XCTAssertEqual(Contract.version, 1) }
}
```

Run: `swift test --package-path app/PrintworksCore` → PASS.

- [ ] **Step 3: Create the app target**

```yaml
# app/RAWdogPrintworks/project.yml
name: RAWdogPrintworks
options:
  bundleIdPrefix: com.john
  deploymentTarget:
    macOS: "15.0"
packages:
  PrintworksCore:
    path: ../PrintworksCore
targets:
  RAWdogPrintworks:
    type: application
    platform: macOS
    sources: [Sources]
    dependencies:
      - package: PrintworksCore
    info:
      path: Info.plist
      properties:
        CFBundleDisplayName: RAWdog Printworks
        LSMinimumSystemVersion: "15.0"
        LSApplicationCategoryType: public.app-category.photography
    settings:
      base:
        PRODUCT_BUNDLE_IDENTIFIER: com.john.rawdog-printworks
        CODE_SIGN_IDENTITY: "-"
        SWIFT_VERSION: "6.0"
```

```swift
// app/RAWdogPrintworks/Sources/PrintworksApp.swift
import SwiftUI
import PrintworksCore

@main
struct PrintworksApp: App {
    var body: some Scene {
        WindowGroup {
            Text("RAWdog Printworks")
                .frame(minWidth: 900, minHeight: 600)
                .background(Theme.windowBase)
                .preferredColorScheme(.dark)
        }
    }
}
```

```swift
// app/RAWdogPrintworks/Sources/Theme.swift
import SwiftUI

public enum Theme {
    public static let windowBase = Color(red: 0x0A/255, green: 0x0A/255, blue: 0x0B/255)
    public static let canvas = Color.black
    public static let panel = Color(red: 0x14/255, green: 0x14/255, blue: 0x16/255)
    public static let hairline = Color(red: 0x23/255, green: 0x23/255, blue: 0x26/255)
    public static let accent = Color(red: 0xE8/255, green: 0xA8/255, blue: 0x49/255)
    public static let statusPublished = Color(red: 0x28/255, green: 0xC8/255, blue: 0x40/255)
    public static let statusReview = accent
    public static let statusIngested = Color(red: 0x9A/255, green: 0x9A/255, blue: 0xA0/255)
}
```

- [ ] **Step 4: Generate + build**

```bash
(cd app/RAWdogPrintworks && xcodegen generate)
xcodebuild -project app/RAWdogPrintworks/RAWdogPrintworks.xcodeproj -scheme RAWdogPrintworks build
```

Expected: BUILD SUCCEEDED.

- [ ] **Step 5: Commit** (include the generated `.xcodeproj` — spec §9 commits the project)

```bash
git add app/ .gitignore
git commit -m "feat(app): scaffold PrintworksCore package + RAWdogPrintworks app target"
```

---

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
        // The NDJSON fixture is the contract for PipelineClient's streaming
        // parser: every non-final line is a ProgressEvent, the final line is
        // the envelope, and the envelope equals adjust_ok.json.
        let lines = String(decoding: try fixture("adjust_stream.ndjson"),
                           as: UTF8.self)
            .split(separator: "\n").map(String.init)
        XCTAssertFalse(lines.isEmpty)
        let decoder = ContractDecoder.make()
        for line in lines.dropLast() {
            XCTAssertNoThrow(try decoder.decode(ProgressEvent.self,
                                                from: Data(line.utf8)), line)
        }
        let final = try decoder.decode(Envelope<AdjustResult>.self,
                                       from: Data(lines.last!.utf8))
        let canonical = try decoder.decode(Envelope<AdjustResult>.self,
                                           from: fixture("adjust_ok.json"))
        XCTAssertEqual(final, canonical)
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

### Task 3: `PipelineClient` actor

**Files:**
- Create: `app/PrintworksCore/Sources/PrintworksCore/PipelineClient.swift`
- Test: `app/PrintworksCore/Tests/PrintworksCoreTests/PipelineClientTests.swift`

**Interfaces:**
- Consumes: Contract types.
- Produces:
  - `struct PipelineConfig: Sendable { repo: URL; python: URL }`
  - `enum PipelineFailure: Error, Equatable { case internalError(String) }` (process-level failures only; envelope errors are data, not thrown).
  - `struct CommandResult<R: Codable & Sendable & Equatable>: Sendable { envelope: Envelope<R>; stderrTail: String }` — `stderrTail` is the last 50 stderr lines, retained on success and failure alike (the "Show Details" disclosure needs it even when a valid error envelope arrived).
  - `actor PipelineClient`:
    - `init(config: PipelineConfig, executableOverride: URL? = nil)` — override lets tests substitute a stub script for `python`.
    - `func run<R>(_ resultType: R.Type, args: [String], onEvent: (@Sendable (ProgressEvent) -> Void)? = nil) async -> CommandResult<R>` — spawns `python -m pipeline <args>` (or the override with `<args>`), `currentDirectoryURL = config.repo`, environment `["PATH": "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin"]` merged over a minimal base (`HOME` preserved). **Stdout is parsed line-by-line as it arrives** (readabilityHandler feeding a line splitter) — a render emits progress for minutes, so events must reach `onEvent` live, not after exit. Every complete line decoding as `ProgressEvent` (has `"event"`) → `onEvent` immediately. After exit, the **last non-empty stdout line** must decode as `Envelope<R>` — anything else (no envelope, or trailing garbage after one) yields a synthetic `Envelope(ok: false, error: INTERNAL, message: stderrTail)`. Non-zero exit with a valid final-line envelope trusts the envelope.
    - `func runMutating<R>(…same signature…) async -> CommandResult<R>` — identical but strictly serialized: one mutating subprocess at a time, FIFO order; `run` (read-only: status/crops) never queues.
- Concurrency design (binding — the naïve "store a tail task that only awaits the previous tail" version does NOT serialize, because actor reentrancy lets the next `execute` start while the first subprocess runs): `runMutating` wraps the **entire execution** in a `Task`, chains it on the stored previous task, stores the new task as the tail, then awaits it:

```swift
private var tail: Task<Void, Never> = Task {}

public func runMutating<R: Codable & Sendable & Equatable>(
    _ resultType: R.Type, args: [String],
    onEvent: (@Sendable (ProgressEvent) -> Void)? = nil
) async -> CommandResult<R> {
    let prior = tail
    let work = Task { () -> CommandResult<R> in
        await prior.value                       // FIFO: wait out the whole
        return await self.execute(resultType,   // previous execution
                                  args: args, onEvent: onEvent)
    }
    tail = Task { _ = await work.value }        // tail spans the FULL execution
    return await work.value
}
```

- [ ] **Step 1: Write the failing tests** (stub scripts stand in for python)

```swift
import XCTest
@testable import PrintworksCore

final class PipelineClientTests: XCTestCase {
    private func makeStub(_ body: String) throws -> (PipelineClient, URL) {
        let dir = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
        try FileManager.default.createDirectory(at: dir,
                                                withIntermediateDirectories: true)
        let script = dir.appendingPathComponent("stub.sh")
        try ("#!/bin/sh\n" + body).write(to: script, atomically: true,
                                         encoding: .utf8)
        try FileManager.default.setAttributes([.posixPermissions: 0o755],
                                              ofItemAtPath: script.path)
        let config = PipelineConfig(repo: dir, python: script)
        return (PipelineClient(config: config, executableOverride: script), dir)
    }

    func testParsesEventsThenEnvelope() async throws {
        let (client, _) = try makeStub("""
        echo '{"event":"stage","stem":"P1","stage":"render"}'
        echo '{"event":"progress","stem":"P1","stage":"render","index":1,"total":29,"detail":"natural tif"}'
        echo '{"ok":true,"result":{"stem":"P1","state":"approved","fingerprint":"f"}}'
        """)
        nonisolated(unsafe) var events: [ProgressEvent] = []
        let result = await client.run(ApproveResult.self, args: ["approve"]) {
            events.append($0)
        }
        XCTAssertTrue(result.envelope.ok)
        XCTAssertEqual(result.envelope.result?.stem, "P1")
        XCTAssertEqual(events.count, 2)
        XCTAssertEqual(events.last?.index, 1)
    }

    func testEventsArriveLiveNotAtExit() async throws {
        let (client, _) = try makeStub("""
        echo '{"event":"stage","stem":"P1","stage":"render"}'
        sleep 0.5
        echo '{"ok":true,"result":{"stem":"P1","state":"approved","fingerprint":"f"}}'
        """)
        nonisolated(unsafe) var eventAt: Date?
        let result = await client.run(ApproveResult.self, args: ["x"]) { _ in
            if eventAt == nil { eventAt = Date() }
        }
        let doneAt = Date()
        XCTAssertTrue(result.envelope.ok)
        let leadTime = doneAt.timeIntervalSince(try XCTUnwrap(eventAt))
        XCTAssertGreaterThan(leadTime, 0.3,
            "event should arrive while the process still runs, not at exit")
    }

    func testGarbageOutputSynthesizesInternalWithStderrTail() async throws {
        let (client, _) = try makeStub("""
        echo 'Traceback (most recent call last):'
        echo '  boom' 1>&2
        exit 2
        """)
        let result = await client.run(StatusSnapshot.self, args: ["status"])
        XCTAssertFalse(result.envelope.ok)
        XCTAssertEqual(result.envelope.error?.code, "INTERNAL")
        XCTAssertTrue(result.stderrTail.contains("boom"))
    }

    func testGarbageAfterEnvelopeIsInternal() async throws {
        // Contract: the envelope is ALWAYS the last line; trailing garbage
        // means the stream is corrupt and must not be trusted.
        let (client, _) = try makeStub("""
        echo '{"ok":true,"result":{"stem":"P1","state":"approved","fingerprint":"f"}}'
        echo 'stray trailing output'
        """)
        let result = await client.run(ApproveResult.self, args: ["x"])
        XCTAssertEqual(result.envelope.error?.code, "INTERNAL")
    }

    func testNonZeroExitWithValidEnvelopeTrustsEnvelopeAndKeepsStderr() async throws {
        let (client, _) = try makeStub("""
        echo 'detail line' 1>&2
        echo '{"ok":false,"error":{"code":"LOCK_HELD","message":"busy"}}'
        exit 1
        """)
        let result = await client.run(StatusSnapshot.self, args: ["status"])
        XCTAssertEqual(result.envelope.error?.code, "LOCK_HELD")  // not INTERNAL
        XCTAssertTrue(result.stderrTail.contains("detail line"))
    }

    func testEnvironmentAndCwdPinned() async throws {
        let (client, dir) = try makeStub("""
        echo "{\\"ok\\":true,\\"result\\":{\\"repo\\":\\"$PWD|$PATH\\",\\"toolchain\\":{\\"ok\\":true,\\"failures\\":[]},\\"lock\\":{\\"held\\":false,\\"stale\\":false,\\"pid\\":null},\\"styles\\":[],\\"photos\\":[]}}"
        """)
        let result = await client.run(StatusSnapshot.self, args: ["status"])
        let repoField = try XCTUnwrap(result.envelope.result?.repo)
        XCTAssertTrue(repoField.hasPrefix(dir.resolvingSymlinksInPath().path)
                      || repoField.hasPrefix(dir.path))
        XCTAssertTrue(repoField.hasSuffix(
            "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin"))
    }

    func testMutatingCommandsAreSerializedInOrder() async throws {
        // Each invocation appends start/end markers; overlap or reordering
        // across THREE concurrent calls fails the assertion.
        let (client, dir) = try makeStub("""
        LOG="$PWD/order.log"
        echo "start-$1" >> "$LOG"
        sleep 0.15
        echo "end-$1" >> "$LOG"
        echo '{"ok":true,"result":{"stem":"P1","state":"approved","fingerprint":"f"}}'
        """)
        async let a = client.runMutating(ApproveResult.self, args: ["a"])
        async let b = client.runMutating(ApproveResult.self, args: ["b"])
        async let c = client.runMutating(ApproveResult.self, args: ["c"])
        _ = await (a, b, c)
        let log = try String(contentsOf: dir.appendingPathComponent("order.log"),
                             encoding: .utf8)
            .split(separator: "\n").map(String.init)
        XCTAssertEqual(log.count, 6)
        for pair in stride(from: 0, to: 6, by: 2) {
            XCTAssertTrue(log[pair].hasPrefix("start-"))
            XCTAssertEqual("end-" + log[pair].dropFirst(6), log[pair + 1],
                           "executions overlapped: \(log)")
        }
    }
}
```

- [ ] **Step 2: Run to verify failure** — FAIL (type missing).

- [ ] **Step 3: Implement `PipelineClient.swift`**

```swift
import Foundation

public struct PipelineConfig: Sendable {
    public let repo: URL
    public let python: URL
    public init(repo: URL, python: URL) { self.repo = repo; self.python = python }
}

public struct CommandResult<R: Codable & Sendable & Equatable>: Sendable {
    public let envelope: Envelope<R>
    public let stderrTail: String
}

public actor PipelineClient {
    private let config: PipelineConfig
    private let executableOverride: URL?
    private var tail: Task<Void, Never> = Task {}

    public init(config: PipelineConfig, executableOverride: URL? = nil) {
        self.config = config
        self.executableOverride = executableOverride
    }

    public func run<R: Codable & Sendable & Equatable>(
        _ resultType: R.Type, args: [String],
        onEvent: (@Sendable (ProgressEvent) -> Void)? = nil
    ) async -> CommandResult<R> {
        await execute(resultType, args: args, onEvent: onEvent)
    }

    public func runMutating<R: Codable & Sendable & Equatable>(
        _ resultType: R.Type, args: [String],
        onEvent: (@Sendable (ProgressEvent) -> Void)? = nil
    ) async -> CommandResult<R> {
        // FIFO over the WHOLE execution — see the Interfaces block for why
        // a tail that only awaits the previous tail does not serialize.
        let prior = tail
        let work = Task { () -> CommandResult<R> in
            await prior.value
            return await self.execute(resultType, args: args, onEvent: onEvent)
        }
        tail = Task { _ = await work.value }
        return await work.value
    }

    private func execute<R: Codable & Sendable & Equatable>(
        _ resultType: R.Type, args: [String],
        onEvent: (@Sendable (ProgressEvent) -> Void)?
    ) async -> CommandResult<R> {
        let process = Process()
        var launchError: Error?
        if let override = executableOverride {
            process.executableURL = override
            process.arguments = args
        } else {
            process.executableURL = config.python
            process.arguments = ["-m", "pipeline"] + args
        }
        process.currentDirectoryURL = config.repo
        var env = ["PATH": "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin"]
        if let home = ProcessInfo.processInfo.environment["HOME"] {
            env["HOME"] = home
        }
        env["PIPELINE_ROOT"] = config.repo.path
        process.environment = env

        let out = Pipe(); let err = Pipe()
        process.standardOutput = out
        process.standardError = err

        // Live line-parsing: events reach onEvent while the process runs
        // (renders take minutes; progress buffered until exit is useless).
        let decoder = ContractDecoder.make()
        let collector = LineCollector()   // @unchecked Sendable, lock-guarded
        out.fileHandleForReading.readabilityHandler = { handle in
            let chunk = handle.availableData
            for line in collector.completeLines(appending: chunk) {
                if line.contains("\"event\""),
                   let event = try? decoder.decode(ProgressEvent.self,
                                                   from: Data(line.utf8)) {
                    onEvent?(event)
                }
            }
        }
        let errCollector = LineCollector()
        err.fileHandleForReading.readabilityHandler = { handle in
            _ = errCollector.completeLines(appending: handle.availableData)
        }

        // terminationHandler is set BEFORE run(): Foundation invokes it
        // exactly once on termination, so no isRunning fallback is needed —
        // a fallback could double-resume the continuation.
        await withCheckedContinuation { (c: CheckedContinuation<Void, Never>) in
            process.terminationHandler = { _ in c.resume() }
            do { try process.run() } catch {
                process.terminationHandler = nil
                c.resume()
                launchError = error          // declared `var launchError: Error?` above
            }
        }
        if let launchError {
            return CommandResult(
                envelope: synthetic("could not launch: \(launchError.localizedDescription)"),
                stderrTail: "")
        }
        out.fileHandleForReading.readabilityHandler = nil
        err.fileHandleForReading.readabilityHandler = nil
        collector.finish(out.fileHandleForReading)   // drain any remainder
        errCollector.finish(err.fileHandleForReading)

        let stderrTail = errCollector.allLines.suffix(50).joined(separator: "\n")
        // Contract: the final envelope is the LAST non-empty stdout line.
        // An earlier envelope followed by anything else is a corrupt stream.
        guard let lastLine = collector.allLines.last(where: {
                  !$0.trimmingCharacters(in: .whitespaces).isEmpty
              }),
              let envelope = try? decoder.decode(Envelope<R>.self,
                                                 from: Data(lastLine.utf8))
        else {
            return CommandResult(
                envelope: synthetic(stderrTail.isEmpty ? "no envelope on stdout"
                                                       : stderrTail),
                stderrTail: stderrTail)
        }
        return CommandResult(envelope: envelope, stderrTail: stderrTail)
    }

    private func synthetic<R>(_ message: String) -> Envelope<R> {
        Envelope(ok: false, result: nil,
                 error: PipelineErrorInfo(code: "INTERNAL", message: message))
    }
}

/// Lock-guarded incremental line splitter shared by the readability handlers
/// (they run on non-actor threads). `completeLines(appending:)` returns newly
/// completed lines and retains the unterminated remainder; `allLines` is the
/// full ordered history; `finish(_:)` reads any remaining data and flushes
/// the final partial line.
final class LineCollector: @unchecked Sendable {
    private let lock = NSLock()
    private var buffer = ""
    private var lines: [String] = []

    var allLines: [String] {
        lock.lock(); defer { lock.unlock() }
        return lines
    }

    func completeLines(appending data: Data) -> [String] {
        lock.lock(); defer { lock.unlock() }
        buffer += String(decoding: data, as: UTF8.self)
        var completed: [String] = []
        while let newline = buffer.firstIndex(of: "\n") {
            completed.append(String(buffer[..<newline]))
            buffer.removeSubrange(...newline)
        }
        lines.append(contentsOf: completed)
        return completed
    }

    func finish(_ handle: FileHandle) {
        _ = completeLines(appending: handle.readDataToEndOfFile())
        lock.lock(); defer { lock.unlock() }
        if !buffer.isEmpty {
            lines.append(buffer)
            buffer = ""
        }
    }
}
```

`LineCollector` unit test: feed chunks `"ab"`, `"c\nde"`, `"f\n"` → `allLines == ["abc", "def"]` after `finish` of an empty handle; a trailing unterminated `"partial"` flushes as a final line on `finish`.

- [ ] **Step 4: Run to verify pass** — `swift test --package-path app/PrintworksCore` → PASS.

- [ ] **Step 5: Commit**

```bash
git add app/PrintworksCore
git commit -m "feat(app): PipelineClient actor — NDJSON streaming, env pinning, FIFO mutation queue"
```

---

### Task 4: CropMath + Debouncer

**Files:**
- Create: `Sources/PrintworksCore/CropMath.swift`, `Sources/PrintworksCore/Debouncer.swift`
- Test: `Tests/PrintworksCoreTests/CropMathTests.swift`, `Tests/PrintworksCoreTests/DebouncerTests.swift`

**Interfaces:**
- Produces:
  - `CropMath.nudged(_ window: CropWindow, dx: Double, dy: Double) -> CropWindow` — translates by (dx, dy) in normalized units, clamps x to [0, 1−w] and y to [0, 1−h], w/h/source unchanged (aspect is locked by construction).
  - `CropMath.aspectFitRect(image: CGSize, container: CGSize) -> CGRect` — the rectangle the image actually occupies when aspect-fit inside the container (centered, letterboxed). Task 9's overlay MUST draw and normalize drags against this rect, not the whole view, or windows misalign whenever the canvas letterboxes.
  - `RepoPaths.resolve(_ relative: String, repo: URL) -> URL` — repo-relative contract paths (e.g. `previews/P1_natural_preview.jpg`) to absolute file URLs; passes absolute inputs through unchanged. All view-layer image loading goes through this.
  - `final class Debouncer: @unchecked Sendable` — `init(delay: Duration)`, `func schedule(_ action: @escaping @Sendable () async -> Void)` (cancels any pending action), `func flush() async` (runs a pending action immediately — the approve path), `var hasPending: Bool`.

- [ ] **Step 1: Write the failing tests**

```swift
import XCTest
@testable import PrintworksCore

final class CropMathTests: XCTestCase {
    func testNudgeTranslatesAndClamps() {
        let w = CropWindow(x: 0.1, y: 0.0, w: 0.75, h: 0.96, source: "suggested")
        let moved = CropMath.nudged(w, dx: 0.05, dy: 0.1)
        XCTAssertEqual(moved.x, 0.15, accuracy: 1e-9)
        XCTAssertEqual(moved.y, 0.04, accuracy: 1e-9)   // clamped to 1-h
        let pinned = CropMath.nudged(w, dx: -1, dy: -1)
        XCTAssertEqual(pinned.x, 0)
        XCTAssertEqual(pinned.y, 0)
        XCTAssertEqual(pinned.w, 0.75)                   // size untouched
    }

    func testAspectFitRectLetterboxesAndPillarboxes() {
        // 4:3 image in a wide container → pillarboxed, full height, centered
        let wide = CropMath.aspectFitRect(image: CGSize(width: 4000, height: 3000),
                                          container: CGSize(width: 1000, height: 600))
        XCTAssertEqual(wide.height, 600)
        XCTAssertEqual(wide.width, 800)
        XCTAssertEqual(wide.minX, 100)
        XCTAssertEqual(wide.minY, 0)
        // 4:3 image in a tall container → letterboxed, full width, centered
        let tall = CropMath.aspectFitRect(image: CGSize(width: 4000, height: 3000),
                                          container: CGSize(width: 400, height: 600))
        XCTAssertEqual(tall.width, 400)
        XCTAssertEqual(tall.height, 300)
        XCTAssertEqual(tall.minY, 150)
    }
}

final class RepoPathsTests: XCTestCase {
    func testResolvesRelativeAndPassesThroughAbsolute() {
        let repo = URL(fileURLWithPath: "/Users/x/photo-edits")
        XCTAssertEqual(
            RepoPaths.resolve("previews/P1_natural_preview.jpg", repo: repo).path,
            "/Users/x/photo-edits/previews/P1_natural_preview.jpg")
        XCTAssertEqual(RepoPaths.resolve("/tmp/abs.jpg", repo: repo).path,
                       "/tmp/abs.jpg")
    }
}

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
```

- [ ] **Step 2: Run to verify failure**, **Step 3: Implement**

```swift
// CropMath.swift
import Foundation

public enum CropMath {
    public static func nudged(_ window: CropWindow, dx: Double, dy: Double)
    -> CropWindow {
        CropWindow(x: min(max(window.x + dx, 0), 1 - window.w),
                   y: min(max(window.y + dy, 0), 1 - window.h),
                   w: window.w, h: window.h, source: window.source)
    }

    public static func aspectFitRect(image: CGSize, container: CGSize) -> CGRect {
        let scale = min(container.width / image.width,
                        container.height / image.height)
        let size = CGSize(width: image.width * scale, height: image.height * scale)
        return CGRect(x: (container.width - size.width) / 2,
                      y: (container.height - size.height) / 2,
                      width: size.width, height: size.height)
    }
}

public enum RepoPaths {
    public static func resolve(_ relative: String, repo: URL) -> URL {
        relative.hasPrefix("/") ? URL(fileURLWithPath: relative)
                                : repo.appendingPathComponent(relative)
    }
}
```

```swift
// Debouncer.swift
import Foundation

public final class Debouncer: @unchecked Sendable {
    private let delay: Duration
    private let lock = NSLock()
    private var pendingTask: Task<Void, Never>?
    private var pendingAction: (@Sendable () async -> Void)?

    public init(delay: Duration) { self.delay = delay }

    public var hasPending: Bool {
        lock.lock(); defer { lock.unlock() }
        return pendingAction != nil
    }

    public func schedule(_ action: @escaping @Sendable () async -> Void) {
        lock.lock()
        pendingTask?.cancel()
        pendingAction = action
        let delay = delay
        pendingTask = Task { [weak self] in
            try? await Task.sleep(for: delay)
            guard !Task.isCancelled else { return }
            await self?.fire()
        }
        lock.unlock()
    }

    public func flush() async {
        await fire()
    }

    private func fire() async {
        lock.lock()
        let action = pendingAction
        pendingAction = nil
        pendingTask?.cancel()
        pendingTask = nil
        lock.unlock()
        await action?()
    }
}
```

Requires `CropWindow` to gain a public memberwise `init` — add it in `Contract.swift` (explicit `public init(x:y:w:h:source:)`).

- [ ] **Step 4: Run to verify pass**, **Step 5: Commit**

```bash
git add app/PrintworksCore
git commit -m "feat(app): crop nudge math + cancellable debouncer"
```

---

### Task 5: `AppModel` — state tree, drafts, actions

**Files:**
- Create: `Sources/PrintworksCore/AppModel.swift`
- Test: `Tests/PrintworksCoreTests/AppModelTests.swift`

**Interfaces:**
- Consumes: `PipelineClient` (behind a protocol so tests inject a fake), Contract types, `Debouncer`.
- Produces:
  - `protocol PipelineRunning: Sendable` — `func status() async -> CommandResult<StatusSnapshot>`; `func mutate<R>(_ type: R.Type, args: [String], onEvent: (@Sendable (ProgressEvent) -> Void)?) async -> CommandResult<R>`; `func crops(stem: String) async -> CommandResult<CropsResult>`. `PipelineClient` gets a conforming extension mapping to `run`/`runMutating` with the canonical arg spellings. The model stores each failure's `stderrTail` alongside `banner` (`bannerDetails: String?`) for the Show Details disclosure.
  - **Result-before-error rule (binding):** on any `ok: false` envelope with a non-nil `result` (aggregate `run`/`ingest`), the model applies the result's successes (progress records, notifications for `published` entries) BEFORE setting `banner`; every action's exit path — success or failure — ends with `refresh()`.
  - `struct ReviewDraft: Sendable { stem: String; baseRevision: String; checks: [String: Bool]; note: String; cropNudges: [String: CropWindow]; isStale: Bool }` — check keys: `"eyes_open"`, `"expressions_natural"`, `"no_blinks_in_crops"`.
  - `@Observable @MainActor final class AppModel`:
    - `init(client: PipelineRunning, repo: URL, sliderDebounce: Duration = .seconds(2))` — `repo` is needed for `pendingInputFiles` (Task 10) and repo-relative path resolution; exposed as `let repo: URL`.
    - Published state: `snapshot: StatusSnapshot?`, `drafts: [String: ReviewDraft]`, `banner: PipelineErrorInfo?`, `bannerDetails: String?` (stderr tail), `busyExternally: Bool`, `activeCommand: String?` (nil = idle), `activeStem: String?` (the stem the active command targets, for §6.1 deferred reconcile), `renderProgress: [String: ProgressEvent]` (latest per stem), `selectedStem: String?`, `selectedStyle: String` (default `"natural"`), `selectedDeliveryId: String??` (`.none` = browse all; `.some(nil)` = the "Earlier" group) — consumed by Task 7's sidebar; `lastPublished: [PublishedPhoto]` (successes from the most recent run result — applied even on `PARTIAL_FAILURE`, drives Task 10's notifications).
    - Slider debouncing is keyed **per (stem, style)**: `private var debouncers: [String: Debouncer]` keyed `"\(stem)|\(style)"`, each with its own pending temperature/exposure accumulator — switching photo or style must never cancel or merge another pair's pending edit. `flushPendingAdjustments(stem:) async` flushes every debouncer for that stem (all styles) — approve calls it.
    - `func reprocess(stem: String) async` / `func reprocessAll() async` — `run --stem S --force --json` / `run --force --json` through the standard action cycle (consumed by Task 7's toolbar; test asserts args).
    - `func retryBannerAction() async` — re-runs the last failed action for `RENDER_FAILED`/`VERIFY_FAILED`/`INTERNAL` banners (the model remembers the last mutating args); `.openSettings` and `.reReview` are signaled to views via `bannerAction: BannerAction?` (`enum BannerAction { case retry, openSettings, reReview }` derived from the error code per spec §7).
    - `func refresh() async` — `client.status()`; on ok: store snapshot, `busyExternally = snapshot.lock.held && activeCommand == nil`, reconcile drafts (below); on error: `banner = error`.
    - Draft reconcile: for each draft, if the photo's `reviewRevision != draft.baseRevision` and no rebase pair matched since the last refresh → `isStale = true` (contents preserved). While `activeCommand != nil && activeStem == stem`, defer reconcile for that stem (spec §6.1); reconcile once at the command's terminal refresh.
    - **One shared rebase path** used by BOTH `applyAdjust` and `rerenderPreview` (their results carry the same `reviewRevisionBefore/After` pair): `rebase(stem:, before:, after:)` — rebases iff `draft.baseRevision == before` (→ `baseRevision = after`), else marks stale.
    - `func reReview(stem: String)` — the stale-banner action: adopts the photo's current `reviewRevision` as the draft's `baseRevision`, **resets all three checks to false** (the user must re-verify against the fresh pixels), clears `isStale`, keeps the note and crop nudges.
    - `func startDraft(stem: String)` — creates a draft keyed to the photo's current `reviewRevision`, all checks false.
    - `func canApprove(stem: String) -> Bool` — draft exists, all three checks true, `!isStale`, photo `stalePreviews.isEmpty`, `activeCommand == nil`, `!busyExternally`.
    - `func setSlider(stem: String, style: String, temperature: Double?, exposure: Double?)` — stores pending values and debounces `applyAdjust`.
    - `func applyAdjust(stem: String, style: String, temperature: Double?, exposure: Double?) async` — `mutate(AdjustResult…)`; on ok, rebase the stem's draft iff `draft.baseRevision == result.reviewRevisionBefore` → `baseRevision = result.reviewRevisionAfter`; else mark stale. Then `refresh()`.
    - `func approve(stem: String) async` — flush the debouncer; build the review-file JSON (audit strings below, crops = `crops` from status merged with `cropNudges`, `expected_review_revision` = draft.baseRevision); write to `FileManager.default.temporaryDirectory`; `mutate(ApproveResult…, args: ["approve", "--stem", stem, "--review-file", path, "--json"])`; on ok chain `mutate(RunResult…, args: ["run", "--stem", stem, "--json"])` feeding `renderProgress`; delete temp file; `refresh()`; on `STALE_REVIEW` → banner + mark draft stale.
    - Audit string mapping: `"eyes open — all: pass"`, `"expressions natural: pass"`, `"no blinks in crops: pass"`, plus `"note: \(note)"` when non-empty — only checked items make `canApprove` true, so all three always serialize as `: pass`.
    - `func ingest(paths: [String]) async` — `mutate(IngestResult…, args: ["ingest", "--from"] + paths + ["--delivery-id", UUID().uuidString, "--json"])`, then `mutate(RunResult…, ["run", "--json"])`, then refresh; surfaces skips/conflicts via `banner` when non-empty (message joined).
    - `func deliveries() -> [(id: String?, photos: [PhotoStatus])]` — group by `deliveryId`, `nil` last as "Earlier", newest `ingestedAt` first.

- [ ] **Step 1: Write the failing tests** (fake client; the heart of the task)

```swift
import XCTest
@testable import PrintworksCore

/// Scriptable fake: every call pops the next canned envelope.
/// (Envelopes are wrapped in CommandResult with an empty stderrTail.)
final class FakeClient: PipelineRunning, @unchecked Sendable {
    var statusQueue: [Envelope<StatusSnapshot>] = []
    var mutateLog: [[String]] = []
    var mutateHandler: ((_ args: [String]) -> Any)!

    func status() async -> CommandResult<StatusSnapshot> {
        CommandResult(envelope: statusQueue.removeFirst(), stderrTail: "")
    }
    func crops(stem: String) async -> CommandResult<CropsResult> {
        CommandResult(envelope: Envelope(ok: true, result: CropsResult(
            stem: stem, basis: "faces", windows: [:]), error: nil),
            stderrTail: "")
    }
    func mutate<R>(_ type: R.Type, args: [String],
                   onEvent: (@Sendable (ProgressEvent) -> Void)?) async
    -> CommandResult<R> {
        mutateLog.append(args)
        return CommandResult(envelope: mutateHandler(args) as! Envelope<R>,
                             stderrTail: "")
    }
}

@MainActor
final class AppModelTests: XCTestCase {
    private func photo(stem: String, revision: String,
                       stale: [String] = []) -> PhotoStatus {
        PhotoStatus(stem: stem, state: "review_required", deliveryId: "d1",
                    ingestedAt: "2026-08-12T00:00:00Z",
                    reviewRevision: revision, previews: [:], previewHashes: [:],
                    stalePreviews: stale, adjustments: [:], crops: [:],
                    expressionAudit: [], published: PublishedInfo(
                        version: nil, path: nil, artifactCount: nil))
    }

    private func snap(_ photos: [PhotoStatus],
                      lockHeld: Bool = false) -> Envelope<StatusSnapshot> {
        Envelope(ok: true, result: StatusSnapshot(
            repo: "/r", toolchain: ToolchainStatus(ok: true, failures: []),
            lock: LockStatus(held: lockHeld, stale: false, pid: nil),
            styles: ["natural", "filmic", "bw", "vibrant"],
            photos: photos), error: nil)
    }

    func testExternalRevisionChangeMarksDraftStale() async {
        let fake = FakeClient()
        fake.statusQueue = [snap([photo(stem: "P1", revision: "r1")]),
                            snap([photo(stem: "P1", revision: "r2")])]
        let model = AppModel(client: fake, repo: URL(fileURLWithPath: "/r"), sliderDebounce: .zero)
        await model.refresh()
        model.startDraft(stem: "P1")
        await model.refresh()                       // external change r1→r2
        XCTAssertTrue(model.drafts["P1"]!.isStale)
    }

    func testAdjustRebasesDraftOnMatchingPair() async {
        let fake = FakeClient()
        fake.statusQueue = [snap([photo(stem: "P1", revision: "r1")]),
                            snap([photo(stem: "P1", revision: "r2")])]
        fake.mutateHandler = { _ in
            Envelope(ok: true, result: AdjustResult(
                stem: "P1", style: "natural", preview: "p.jpg",
                temperature: Control(value: 5600, source: "sidecar"),
                exposure: Control(value: nil, source: "camera"),
                reviewRevisionBefore: "r1", reviewRevisionAfter: "r2"),
                error: nil)
        }
        let model = AppModel(client: fake, repo: URL(fileURLWithPath: "/r"), sliderDebounce: .zero)
        await model.refresh()
        model.startDraft(stem: "P1")
        await model.applyAdjust(stem: "P1", style: "natural",
                                temperature: 5600, exposure: nil)
        XCTAssertFalse(model.drafts["P1"]!.isStale)
        XCTAssertEqual(model.drafts["P1"]!.baseRevision, "r2")
    }

    func testCanApproveGates() async {
        let fake = FakeClient()
        fake.statusQueue = [snap([photo(stem: "P1", revision: "r1")])]
        let model = AppModel(client: fake, repo: URL(fileURLWithPath: "/r"), sliderDebounce: .zero)
        await model.refresh()
        model.startDraft(stem: "P1")
        XCTAssertFalse(model.canApprove(stem: "P1"))     // unchecked boxes
        for key in ["eyes_open", "expressions_natural", "no_blinks_in_crops"] {
            model.drafts["P1"]!.checks[key] = true
        }
        XCTAssertTrue(model.canApprove(stem: "P1"))
        model.drafts["P1"]!.isStale = true
        XCTAssertFalse(model.canApprove(stem: "P1"))
    }

    func testStalePreviewsBlockApprove() async {
        let fake = FakeClient()
        fake.statusQueue = [snap([photo(stem: "P1", revision: "r1",
                                        stale: ["filmic"])])]
        let model = AppModel(client: fake, repo: URL(fileURLWithPath: "/r"), sliderDebounce: .zero)
        await model.refresh()
        model.startDraft(stem: "P1")
        for key in ["eyes_open", "expressions_natural", "no_blinks_in_crops"] {
            model.drafts["P1"]!.checks[key] = true
        }
        XCTAssertFalse(model.canApprove(stem: "P1"))
    }

    func testBusyPillFromExternalLock() async {
        let fake = FakeClient()
        fake.statusQueue = [snap([], lockHeld: true)]
        let model = AppModel(client: fake, repo: URL(fileURLWithPath: "/r"), sliderDebounce: .zero)
        await model.refresh()
        XCTAssertTrue(model.busyExternally)
    }

    func testApproveChainsRunAndSendsReviewFile() async throws {
        let fake = FakeClient()
        fake.statusQueue = [snap([photo(stem: "P1", revision: "r1")]),
                            snap([photo(stem: "P1", revision: "r9")])]
        nonisolated(unsafe) var reviewFileBody: [String: Any]?
        fake.mutateHandler = { args in
            if args.first == "approve" {
                if let i = args.firstIndex(of: "--review-file"),
                   let data = FileManager.default.contents(atPath: args[i + 1]) {
                    reviewFileBody = try? JSONSerialization.jsonObject(
                        with: data) as? [String: Any]
                }
                return Envelope(ok: true, result: ApproveResult(
                    stem: "P1", state: "approved", fingerprint: "f"),
                    error: nil) as Any
            }
            return Envelope(ok: true, result: RunResult(
                published: [PublishedPhoto(stem: "P1", version: "v004",
                                           artifactCount: 29)],
                advanced: [], failed: []), error: nil) as Any
        }
        let model = AppModel(client: fake, repo: URL(fileURLWithPath: "/r"), sliderDebounce: .zero)
        await model.refresh()
        model.startDraft(stem: "P1")
        for key in ["eyes_open", "expressions_natural", "no_blinks_in_crops"] {
            model.drafts["P1"]!.checks[key] = true
        }
        await model.approve(stem: "P1")
        XCTAssertEqual(fake.mutateLog.map(\.first), ["approve", "run"])
        let body = try XCTUnwrap(reviewFileBody)
        XCTAssertEqual(body["expected_review_revision"] as? String, "r1")
        let audit = try XCTUnwrap(body["expression_audit"] as? [String])
        XCTAssertTrue(audit.contains("eyes open — all: pass"))
    }

    func testDebouncersAreKeyedPerStemAndStyle() async {
        let fake = FakeClient()
        fake.statusQueue = Array(repeating: snap([photo(stem: "P1", revision: "r1"),
                                                  photo(stem: "P2", revision: "r1")]),
                                 count: 4)
        fake.mutateHandler = { args in
            Envelope(ok: true, result: AdjustResult(
                stem: args[args.firstIndex(of: "--stem")! + 1],
                style: args[args.firstIndex(of: "--style")! + 1],
                preview: "p.jpg",
                temperature: Control(value: 5600, source: "sidecar"),
                exposure: Control(value: nil, source: "camera"),
                reviewRevisionBefore: "r1", reviewRevisionAfter: "r1"),
                error: nil)
        }
        let model = AppModel(client: fake, repo: URL(fileURLWithPath: "/r"),
                             sliderDebounce: .zero)
        await model.refresh()
        // Two different (stem, style) pairs scheduled back-to-back: BOTH fire.
        model.setSlider(stem: "P1", style: "natural", temperature: 5600,
                        exposure: nil)
        model.setSlider(stem: "P2", style: "bw", temperature: 5400,
                        exposure: nil)
        await model.flushPendingAdjustments(stem: "P1")
        await model.flushPendingAdjustments(stem: "P2")
        let adjustTargets = fake.mutateLog.filter { $0.first == "adjust" }
            .map { "\($0[$0.firstIndex(of: "--stem")! + 1])|\($0[$0.firstIndex(of: "--style")! + 1])" }
        XCTAssertEqual(Set(adjustTargets), ["P1|natural", "P2|bw"])
    }

    func testReReviewAdoptsRevisionAndResetsChecks() async {
        let fake = FakeClient()
        fake.statusQueue = [snap([photo(stem: "P1", revision: "r1")]),
                            snap([photo(stem: "P1", revision: "r2")])]
        let model = AppModel(client: fake, repo: URL(fileURLWithPath: "/r"),
                             sliderDebounce: .zero)
        await model.refresh()
        model.startDraft(stem: "P1")
        for key in ["eyes_open", "expressions_natural", "no_blinks_in_crops"] {
            model.drafts["P1"]!.checks[key] = true
        }
        await model.refresh()                       // r1 → r2: stale
        XCTAssertTrue(model.drafts["P1"]!.isStale)
        model.reReview(stem: "P1")
        let draft = model.drafts["P1"]!
        XCTAssertFalse(draft.isStale)
        XCTAssertEqual(draft.baseRevision, "r2")
        XCTAssertTrue(draft.checks.values.allSatisfy { $0 == false })
    }

    func testPartialFailureAppliesResultBeforeBanner() async {
        let fake = FakeClient()
        fake.statusQueue = [snap([photo(stem: "P1", revision: "r1")]),
                            snap([photo(stem: "P1", revision: "r1")])]
        fake.mutateHandler = { _ in
            Envelope(ok: false, result: RunResult(
                published: [PublishedPhoto(stem: "P1", version: "v004",
                                           artifactCount: 29)],
                advanced: [], failed: [StemFailure(
                    stem: "P2", code: "VERIFY_FAILED", message: "bad")]),
                error: PipelineErrorInfo(code: "PARTIAL_FAILURE",
                                         message: "1 of 2 failed"))
        }
        let model = AppModel(client: fake, repo: URL(fileURLWithPath: "/r"),
                             sliderDebounce: .zero)
        await model.refresh()
        await model.reprocessAll()
        XCTAssertEqual(model.lastPublished.map(\.stem), ["P1"])  // result first
        XCTAssertEqual(model.banner?.code, "PARTIAL_FAILURE")    // then error
    }
}
```

- [ ] **Step 2: Run to verify failure**, **Step 3: Implement `AppModel.swift`** per the Interfaces block. Key mechanics: `@Observable @MainActor final class`; `PhotoStatus` needs a public memberwise init (add to Contract.swift alongside `CropWindow`'s — same for the other structs used by tests: `StatusSnapshot`, `ToolchainStatus`, `LockStatus`, `PublishedInfo`, `Control`, `AdjustResult`, `ApproveResult`, `RunResult`, `PublishedPhoto`, `CropsResult`); review-file serialization via `JSONSerialization` with keys `expected_review_revision`, `expression_audit`, `crops` (windows as `{"x":…,"y":…,"w":…,"h":…}` dropping `source`); crops for approve come from the photo's persisted `crops` else the `crops()` command result, overridden by `cropNudges`.

- [ ] **Step 4: Run to verify pass** — `swift test --package-path app/PrintworksCore` → PASS.

- [ ] **Step 5: Commit**

```bash
git add app/PrintworksCore
git commit -m "feat(app): AppModel — snapshot state, draft lifecycle, approve chain"
```

---

### Task 6: `RepoWatcher`

**Files:**
- Create: `Sources/PrintworksCore/RepoWatcher.swift`
- Test: `Tests/PrintworksCoreTests/RepoWatcherTests.swift`

**Interfaces:**
- Produces:
  - `final class RepoWatcher: @unchecked Sendable` — `init(repo: URL, coalesce: Duration = .milliseconds(500))`; `var changes: AsyncStream<Void>` (one element per coalesced burst); `func start()`, `func stop()`. kqueue directory sources are **non-recursive**, so the watched set explicitly enumerates every review-input directory: `Input previews sidecars recipes config config/styles config/lab-profiles config/rawtherapee-seed Output Output/photos run` (each via `DispatchSource.makeFileSystemObjectSource(fileDescriptor:eventMask:[.write, .rename, .delete])`; a directory that doesn't exist yet is skipped and retried on the next `start()`/poll). A `config/styles/*.pp3` edit or a new `Output/photos/<stem>` publish must produce an emission — both are tested.
  - **Refresh gate (AppModel-side, spec §7 watcher storms):** `AppModel.refresh()` is guarded so at most one `status` call is in flight; a change arriving mid-refresh sets a `trailingRefresh` flag that triggers exactly one follow-up refresh when the current one completes. Unit-tested in `AppModelTests` with a slow fake client: 5 rapid `refresh()` calls → exactly 2 client `status()` invocations (one active + one trailing).
  - `startPolling(interval: Duration = .seconds(5))` / `stopPolling()` — the busy-pill fallback; emits a change per tick while active. `AppModel` (Task 7 wiring) starts polling when `busyExternally`, stops otherwise.

- [ ] **Step 1: Write the failing tests**

```swift
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
        var iterator = watcher.changes.makeAsyncIterator()

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
```

- [ ] **Step 2: Run to verify failure**, **Step 3: Implement** — open each directory with `open(path, O_EVTONLY)`, one `DispatchSource` per directory on a private queue; every event sets a pending flag and (re)schedules a coalesce timer (`DispatchQueue.asyncAfter`); on fire, yield into the `AsyncStream` continuation (`bufferingPolicy: .bufferingNewest(1)`). `stop()` cancels sources and closes fds. Polling: a `Timer`-free `Task` loop sleeping `interval`, yielding a change per tick, cancelled by `stopPolling()`/`stop()`.

- [ ] **Step 4: Run to verify pass**, **Step 5: Commit**

```bash
git add app/PrintworksCore
git commit -m "feat(app): RepoWatcher — kqueue directory watching with coalescing + poll fallback"
```

---

### Task 7: Shell UI — MainWindow, Sidebar, Grid, drop target

**Files:**
- Create: `app/RAWdogPrintworks/Sources/MainWindow.swift`, `SidebarView.swift`, `GridView.swift`, `ErrorBanner.swift`
- Modify: `PrintworksApp.swift` (wire AppModel/watcher/settings), `Sources/PrintworksCore/AppModel.swift` (only if a computed helper is missing — no behavior changes)

**Interfaces:**
- Consumes: `AppModel` (Task 5), `RepoWatcher` (Task 6), `Theme` (Task 1).
- Produces: `MainWindow(model:)` — `NavigationSplitView`; sidebar lists deliveries (Browse) or the open delivery's photos (Review level) with 42 pt thumbnails + state dots; detail pane switches `GridView` ↔ `ReviewView` (Task 8 stub: `Text` placeholder until Task 8 replaces it); toolbar (delivery name, needs-review count, compact `ProgressView` when `renderProgress` non-empty, Reprocess menu → `model.reprocess(stem:)`/`reprocessAll()` which issue `run --stem S --force --json`/`run --force --json`; Grid/Review toggle); `.dropDestination(for: URL.self)` on the whole window → `model.ingest(paths:)`; empty state "Drop RAW files to start a delivery."; persistent busy pill (`Capsule` with "Pipeline busy (CLI)") when `model.busyExternally`; `ErrorBanner(model:)` overlay rendering `model.banner` with message + Show Details disclosure + per-code action button (Retry/Open Settings/Re-review per spec §7).

Key view code (complete files in the implementing commit; structure fixed here):

```swift
// MainWindow.swift (skeleton — fill bodies, keep names)
struct MainWindow: View {
    @Bindable var model: AppModel
    @State private var showingReview = false

    var body: some View {
        NavigationSplitView {
            SidebarView(model: model, showingReview: $showingReview)
                .background(.ultraThinMaterial)
        } detail: {
            ZStack(alignment: .top) {
                if model.selectedStem != nil && showingReview {
                    ReviewScreen(model: model)          // Task 8 replaces stub
                } else {
                    GridView(model: model, openReview: { stem in
                        model.selectedStem = stem; showingReview = true
                    })
                }
                if let banner = model.banner { ErrorBanner(model: model, info: banner) }
            }
            .background(Theme.windowBase)
        }
        .preferredColorScheme(.dark)
        .dropDestination(for: URL.self) { urls, _ in
            Task { await model.ingest(paths: urls.map(\.path)) }
            return true
        }
    }
}
```

Status-dot mapping (single helper used by sidebar + grid badges): `verified`→`Theme.statusPublished`/"Published", `preview_ready`/`review_required`→`Theme.statusReview`/"Needs review", `approved`/`rendered`→accent/"Rendering", else `Theme.statusIngested`/"Ingested". Grid cards: `LazyVGrid(columns: [GridItem(.adaptive(minimum: 260))])`; every image load resolves the contract's repo-relative path via `RepoPaths.resolve(path, repo: model.repo)` then `NSImage(contentsOf:)`, inside an `.id(photo.previewHashes["natural"] ?? "")`-keyed view (content-hash cache key — never URL/mtime caching); badge top-left, `ProgressView(value:)` overlay when `model.renderProgress[stem]` present, `.onTapGesture(count: 2)` → openReview. Sidebar delivery rows drive `model.selectedDeliveryId`; the toolbar Reprocess menu calls `model.reprocess(stem:)`/`reprocessAll()` (both exist from Task 5 — views add no model logic).

- [ ] **Step 1: Implement the four files** per the skeleton (no unit tests — logic already covered in core; the gate is the build).
- [ ] **Step 2: Build** — `xcodegen generate` (if project.yml changed) + `xcodebuild … build` → BUILD SUCCEEDED. Also `swift test --package-path app/PrintworksCore` still green.
- [ ] **Step 3: Manual smoke** — `open` the built app against the real repo (Settings default `~/Projects/rawdog-printworks`): grid shows P1036163/P1036170 as Published, sidebar shows "Earlier" group (legacy recipes have no delivery_id). Screenshot for the Task 11 QA set.
- [ ] **Step 4: Commit**

```bash
git add app/
git commit -m "feat(app): main window shell — sidebar, grid, drop target, busy pill, error banner"
```

---

### Task 8: ReviewView + CompareView

**Files:**
- Create: `app/RAWdogPrintworks/Sources/ReviewView.swift`, `CompareView.swift`
- Modify: `MainWindow.swift` (replace the `ReviewScreen` stub)

**Interfaces:**
- Consumes: `AppModel.selectedStem/selectedStyle`, `PhotoStatus.previews/previewHashes/stalePreviews`.
- Produces: `ReviewScreen(model:)` — large canvas on `Theme.canvas` showing the selected style's preview (`NSImage(contentsOfFile:)`, `.id(previewHash)` so a content-hash change forces reload; never `AsyncImage`/URL cache); segmented style control bound to `model.selectedStyle`; keyboard: `⌘1`–`⌘4` (`.keyboardShortcut("1", modifiers: .command)` on hidden buttons) switch style, `space` toggles `CompareView`, `c` toggles the crop overlay (Task 9), `←`/`→` move `model.selectedStem` through the open delivery; per-style "preview out of date — re-render" chip when the style ∈ `stalePreviews` → `model.rerenderPreview(stem:style:)` (`preview --stem S --style Y --json` via `mutate`); "rendering preview…" shimmer overlay while that command is `activeCommand`.
- `CompareView(model:)` — 2×2 grid of the four styles' previews with labels; click a panel → sets `selectedStyle`, dismisses compare.

- [ ] **Step 1: Implement** both views; add `rerenderPreview` to `AppModel` **with unit tests first** in `AppModelTests`: (a) asserts args `["preview", "--stem", "P1", "--style", "filmic", "--json"]` and a refresh after; (b) asserts the result's `reviewRevisionBefore/After` pair flows through the SAME shared `rebase(stem:before:after:)` path as `applyAdjust` — a matching pair rebases the draft, a non-matching one marks it stale. Canvas image loading resolves via `RepoPaths.resolve` + content-hash `.id` keying, as in Task 7.
- [ ] **Step 2: Gate** — `swift test --package-path app/PrintworksCore` PASS + `xcodebuild … build` SUCCEEDED.
- [ ] **Step 3: Manual smoke + screenshot** — review P1036163: style switching updates the canvas; space shows 4-up compare.
- [ ] **Step 4: Commit**

```bash
git add app/
git commit -m "feat(app): review screen — canvas, style switching, compare mode, stale-preview chip"
```

---

### Task 9: CropOverlayView + InspectorView

**Files:**
- Create: `app/RAWdogPrintworks/Sources/CropOverlayView.swift`, `InspectorView.swift`
- Modify: `ReviewView.swift` (overlay + inspector column), `Sources/PrintworksCore/AppModel.swift` (crops fetch + nudge storage — test-first)

**Interfaces:**
- Consumes: `CropMath.nudged`, `AppModel.drafts[...].cropNudges`, `model.crops(stem:)` (new: calls the `crops` command, caches result per stem until revision moves — unit-tested).
- Produces:
  - `CropOverlayView(windows:imageSize:onNudge:)` — draws the 8×10 window solid amber, 5×7 dashed, over the canvas. Coordinate mapping goes through `CropMath.aspectFitRect(image:container:)` — windows are drawn inside, and drag deltas normalized against, the rectangle the image ACTUALLY occupies (letterboxing means the `GeometryReader` frame is wrong for both). `DragGesture` translates via `CropMath.nudged` (aspect/size locked by construction) and reports the final window through `onNudge(cropName, window)` → stored in the draft's `cropNudges`; a small `basis` chip ("centered fallback" / "detection failed — centered") when the crops result's basis ≠ "faces"/"persisted".
  - `InspectorView(model:)` — fixed 260 pt column on `Theme.panel`: ADJUST section (Warmth slider 3000–9000 K showing "As shot" when `Control.source == "camera"` and untouched; Exposure −1.00…+1.00; both call `model.setSlider` on change — the 2 s debounce and `adjust` composition are already model-tested; Reset button → `model.resetAdjust(stem:style:)` issuing `--reset`, test-first); CROPS section (per-crop status line + "nudged" tag); EXPRESSION AUDIT checklist (three `Toggle`s + note `TextField` bound to the draft); stale-draft banner ("This photo changed on disk — re-check before approving" + Re-review button clearing `isStale` after re-confirmation per spec §6.1); Approve button (`Theme.accent`, enabled by `model.canApprove`, running `model.approve`).

- [ ] **Step 1: Model additions test-first** — `AppModelTests`: `setSlider` composes `adjust --stem P1 --style natural --temperature 5600 --json` (only changed control); `resetAdjust` sends `--reset`; `crops(stem:)` sends `["crops", "--stem", "P1", "--json"]` once and caches until `reviewRevision` changes.
- [ ] **Step 2: Implement the views.**
- [ ] **Step 3: Gate** — core tests PASS, app builds.
- [ ] **Step 4: Manual smoke + screenshots** — crop overlay on P1036163 (both windows visible, drag nudges), sliders move and write sidecars through the pipeline (verify `git status` shows only pipeline-owned files changed — i.e., sidecar/recipe/preview changes made by python, none by the app process itself).
- [ ] **Step 5: Commit**

```bash
git add app/
git commit -m "feat(app): crop overlay drag-nudge + inspector (sliders, audit, approve)"
```

---

### Task 10: Ingest banner, Settings, notifications

**Files:**
- Create: `app/RAWdogPrintworks/Sources/IngestBanner.swift`, `SettingsSheet.swift`
- Modify: `PrintworksApp.swift` (Settings scene + UserDefaults-backed config), `Sources/PrintworksCore/AppModel.swift` (pending-input detection — test-first)

**Interfaces:**
- Produces:
  - Settings: two fields (repo path default `~/Projects/rawdog-printworks`, python path default `<repo>/.venv/bin/python`) stored in `UserDefaults` keys `repoPath`/`pythonPath`. Paths are tilde-expanded (`NSString.expandingTildeInPath`) before any use — `URL(fileURLWithPath: "~/…")` does NOT expand. Validation is **live** (spec §5.5): field changes debounce (~600 ms) into a `status --json` probe via a throwaway `PipelineClient`, showing ok/error inline; Save enables only while the current pair validates; saving rebuilds the model's client + watcher.
  - `AppModel.pendingInputFiles: [String]` — computed on refresh by listing `Input/*.rw2|*.RW2` whose stems are absent from the snapshot (test with a temp dir set as repo); `IngestBanner` renders "N new RAW files — Ingest now?" → `model.ingestPending()` (plain `ingest --delivery-id <uuid> --json` + `run --json`, test-first).
  - Notification on publish: after an approve-chain or reprocess `RunResult` containing `published` entries, post `UNUserNotificationCenter` notification "P1036163 published (v004, 29 files)" (request authorization once at first use; guard `#if !DEBUG`-free — personal app, always attempt; failure to authorize is silently ignored).

- [ ] **Step 1: Model tests** (`pendingInputFiles`, `ingestPending` args) → fail → implement.
- [ ] **Step 2: Implement views + notification hook.**
- [ ] **Step 3: Gate + manual smoke** (drop a copy of a published RW2 → conflict banner from pipeline result; Settings validation passes on the real repo, fails on a bogus path). Screenshot the banner + settings sheet.
- [ ] **Step 4: Commit**

```bash
git add app/
git commit -m "feat(app): ingest banner, settings sheet with validation, publish notifications"
```

---

### Task 11: End-to-end smoke test, release build script, visual QA gate

**Files:**
- Create: `Tests/PrintworksCoreTests/SmokeTests.swift`, `scripts/build-app.sh`
- Test: itself + the visual QA checklist

**Interfaces:**
- Produces:
  - `SmokeTests` — builds a temp fixture repo (dirs from `tests/conftest.py` list; two fake photos: recipes + tiny preview JPG bytes) and a stub `python` shell script that answers `status --json` from a canned `StatusSnapshot` JSON (with `stale_previews: []`), `adjust`/`preview`/`approve`/`run` from canned envelopes (adjust/preview envelopes carry a `review_revision_before/after` pair matching the canned status revisions). Drives the REAL `PipelineClient` + `AppModel` end-to-end through the full spec-§8 flow: refresh → startDraft → `setSlider` → `flushPendingAdjustments` (debounced adjust fires, draft REBASES on the revision pair, not stale) → check all → approve → asserts the adjust/approve/run arg sequence, the review-file contents the stub received, and the final refresh landed. This is the app-side twin of Plan 1's fixtures — it catches wiring drift the unit fakes can't.
  - `scripts/build-app.sh`:

```bash
#!/bin/zsh
set -euo pipefail
cd "$(dirname "$0")/.."
(cd app/RAWdogPrintworks && xcodegen generate)
xcodebuild -project app/RAWdogPrintworks/RAWdogPrintworks.xcodeproj \
  -scheme RAWdogPrintworks -configuration Release \
  -derivedDataPath app/build build
APP="app/build/Build/Products/Release/RAWdogPrintworks.app"
codesign --force --deep --sign - "$APP"
echo "Built + ad-hoc signed: $APP"
echo "Install: cp -R \"$APP\" /Applications/"
```

  - **Visual QA gate (done-criteria, spec §8):** run the Release app against the real repo and capture screenshots of: grid, review (each of the 4 styles), compare mode, crop overlay, slider adjust with shimmer, render progress (trigger a reprocess of one photo), busy pill (hold the lock via a paused CLI `run` in another terminal), stale-draft banner (touch a sidecar mid-draft), error banner (bogus python path). Every screenshot is reviewed by eye before this task is complete; the review is recorded in the task's completion note. Green tests alone do not close this task.

- [ ] **Step 1: Write SmokeTests** (canned JSON inline in the test file; stub script pattern from Task 3) → fail (compile) → implement any missing glue. Structure (the stub dispatches on `$1`; canned payloads are string constants in the test file):

```swift
@MainActor
final class SmokeTests: XCTestCase {
    func testFullReviewFlowAgainstStubPipeline() async throws {
        let repo = try makeFixtureRepo()          // conftest dir list + 2 recipes + tiny preview JPGs
        let stub = try makeStubPython(at: repo)   // case "$1" in status) … adjust) … approve) … run) …
        // PipelineClient conforms to PipelineRunning via the Task 5
        // extension — passed directly, no adapter type exists.
        // executableOverride is REQUIRED here: without it the client runs
        // `stub -m pipeline <args>` and the stub (which dispatches on $1)
        // would see "-m" as its command.
        let client = PipelineClient(
            config: PipelineConfig(repo: repo, python: stub),
            executableOverride: stub)
        let model = AppModel(client: client,
                             repo: repo, sliderDebounce: .zero)
        await model.refresh()
        XCTAssertEqual(model.snapshot?.photos.count, 2)

        model.startDraft(stem: "P1")
        model.setSlider(stem: "P1", style: "natural", temperature: 5600,
                        exposure: nil)
        await model.flushPendingAdjustments(stem: "P1")
        // Canned adjust envelope carries review_revision_before/after matching
        // the canned status revisions → the draft REBASES, not stales.
        XCTAssertFalse(model.drafts["P1"]!.isStale)

        for key in ["eyes_open", "expressions_natural", "no_blinks_in_crops"] {
            model.drafts["P1"]!.checks[key] = true
        }
        await model.approve(stem: "P1")
        // The stub logs argv per call to <repo>/stub-calls.log; assert the
        // sequence adjust → approve (with a readable review-file whose
        // expected_review_revision matches) → run --stem P1 → final status.
        let calls = try String(contentsOf: repo.appendingPathComponent("stub-calls.log"),
                               encoding: .utf8).split(separator: "\n")
        XCTAssertTrue(calls.contains { $0.hasPrefix("adjust") })
        XCTAssertTrue(calls.contains { $0.hasPrefix("approve") })
        XCTAssertTrue(calls.contains { $0.hasPrefix("run --stem P1") })
    }
}
```
- [ ] **Step 2: Gate** — full `swift test` + `xcodebuild build` + `zsh scripts/build-app.sh` all succeed.
- [ ] **Step 3: Visual QA** — capture + review the screenshot set; fix what the eye finds; re-shoot.
- [ ] **Step 4: Commit**

```bash
git add app/ scripts/build-app.sh
git commit -m "feat(app): e2e smoke test, release build script, visual QA pass"
```

---

## Self-Review

1. **Spec coverage:** §4.1 components → Tasks 3 (PipelineClient), 5 (AppModel), 6 (RepoWatcher), 7–10 (views); §5.1 visual language → Task 1 Theme + view tasks; §5.2 window structure → Task 7; §5.3 review interactions → Tasks 8–9 (⌘1–4/space/C/arrows, sliders+debounce, checklist, approve gating incl. stale previews); §5.4 ingest → Tasks 7 (drop) + 10 (banner, conflicts surfaced from pipeline result); §5.5 settings → Task 10; §6 data flows → Tasks 5, 8–10; §6.1 drafts → Task 5 (rebase rule, stale, deferred reconcile) + Task 9 (re-confirm UI); §7 error handling → Tasks 3 (INTERNAL synth, envelope trust), 5 (banner, busy pill), 7 (ErrorBanner actions); §8 testing → fixtures (Task 2), stream/model tests (3, 5), smoke (11), visual QA (11); notifications → Task 10; ad-hoc signing → Task 11.
2. **Placeholder scan:** Task 7–10 view bodies are deliberately skeleton-plus-fixed-names (build-gated, logic pre-tested in core) — each carries the structural code and exact behavior list; no TBDs.
3. **Type consistency:** Contract type names fixed in Task 2's Interfaces and reused verbatim in Tasks 3, 5, 11 test code; `PipelineRunning` protocol (Task 5) is what views consume via `AppModel` only; check keys (`eyes_open` etc.) and audit strings match between Task 5's tests and spec §4.3's review-file example; CLI spellings match Plan 1's Global Constraints line.
