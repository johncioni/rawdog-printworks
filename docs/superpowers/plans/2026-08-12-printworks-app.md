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
- Canonical CLI spellings (Plan 1): `status --json` · `ingest --from <paths…> --delivery-id <uuid> --json` · `preview <stem> <style> --json` · `adjust --stem S --style Y [--temperature K] [--exposure EV] [--reset] --json` · `crops --stem S --json` · `approve <stem> --review-file <path> --json` · `run [--stem S] [--force] --json`.
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
  - `CropsResult { stem: String; basis: String; windows: [String: CropWindow] }`
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
  - `actor PipelineClient`:
    - `init(config: PipelineConfig, executableOverride: URL? = nil)` — override lets tests substitute a stub script for `python`.
    - `func run<R>(_ resultType: R.Type, args: [String], onEvent: (@Sendable (ProgressEvent) -> Void)? = nil) async -> Envelope<R>` — spawns `python -m pipeline <args>` (or the override with `<args>`), `currentDirectoryURL = config.repo`, environment `["PATH": "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin"]` merged over a minimal base (`HOME` preserved); reads stdout line-by-line; every line that decodes as `ProgressEvent` (has `"event"`) → `onEvent`; the **last** line must decode as `Envelope<R>` — if the process exits with no decodable final envelope, returns a synthetic `Envelope(ok: false, result: nil, error: .init(code: "INTERNAL", message: <last 50 stderr lines>))`. Non-zero exit with a valid envelope trusts the envelope.
    - `func runMutating<R>(…same signature…) async -> Envelope<R>` — identical but serialized: an actor-held FIFO ensures one mutating subprocess at a time (later calls await earlier completions); `run` (read-only: status/crops) never queues.
- Concurrency note: the actor holds `private var mutatingTail: Task<Void, Never>?`; `runMutating` chains on it. Stdout/stderr are drained on background threads via `FileHandle.readabilityHandler` into buffers; the actor awaits process termination via a continuation on `Process.terminationHandler`.

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
        let env = await client.run(ApproveResult.self, args: ["approve"]) {
            events.append($0)
        }
        XCTAssertTrue(env.ok)
        XCTAssertEqual(env.result?.stem, "P1")
        XCTAssertEqual(events.count, 2)
        XCTAssertEqual(events.last?.index, 1)
    }

    func testGarbageOutputSynthesizesInternal() async throws {
        let (client, _) = try makeStub("""
        echo 'Traceback (most recent call last):'
        echo '  boom' 1>&2
        exit 2
        """)
        let env = await client.run(StatusSnapshot.self, args: ["status"])
        XCTAssertFalse(env.ok)
        XCTAssertEqual(env.error?.code, "INTERNAL")
        XCTAssertTrue(env.error!.message.contains("boom"))
    }

    func testNonZeroExitWithValidEnvelopeTrustsEnvelope() async throws {
        let (client, _) = try makeStub("""
        echo '{"ok":false,"error":{"code":"LOCK_HELD","message":"busy"}}'
        exit 1
        """)
        let env = await client.run(StatusSnapshot.self, args: ["status"])
        XCTAssertEqual(env.error?.code, "LOCK_HELD")   // not INTERNAL
    }

    func testEnvironmentAndCwdPinned() async throws {
        let (client, dir) = try makeStub("""
        echo "{\\"ok\\":true,\\"result\\":{\\"repo\\":\\"$PWD|$PATH\\",\\"toolchain\\":{\\"ok\\":true,\\"failures\\":[]},\\"lock\\":{\\"held\\":false,\\"stale\\":false,\\"pid\\":null},\\"styles\\":[],\\"photos\\":[]}}"
        """)
        let env = await client.run(StatusSnapshot.self, args: ["status"])
        let repoField = try XCTUnwrap(env.result?.repo)
        XCTAssertTrue(repoField.hasPrefix(dir.resolvingSymlinksInPath().path)
                      || repoField.hasPrefix(dir.path))
        XCTAssertTrue(repoField.hasSuffix(
            "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin"))
    }

    func testMutatingCommandsAreSerialized() async throws {
        let (client, dir) = try makeStub("""
        LOCKDIR="$PWD/lockdir"
        if ! mkdir "$LOCKDIR" 2>/dev/null; then
          echo '{"ok":false,"error":{"code":"INTERNAL","message":"overlap"}}'
          exit 1
        fi
        sleep 0.2
        rmdir "$LOCKDIR"
        echo '{"ok":true,"result":{"stem":"P1","state":"approved","fingerprint":"f"}}'
        """)
        async let a = client.runMutating(ApproveResult.self, args: ["x"])
        async let b = client.runMutating(ApproveResult.self, args: ["y"])
        let (ra, rb) = await (a, b)
        XCTAssertTrue(ra.ok && rb.ok, "overlap means FIFO serialization failed")
        _ = dir
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

public actor PipelineClient {
    private let config: PipelineConfig
    private let executableOverride: URL?
    private var mutatingTail: Task<Void, Never>?

    public init(config: PipelineConfig, executableOverride: URL? = nil) {
        self.config = config
        self.executableOverride = executableOverride
    }

    public func run<R: Codable & Sendable & Equatable>(
        _ resultType: R.Type, args: [String],
        onEvent: (@Sendable (ProgressEvent) -> Void)? = nil
    ) async -> Envelope<R> {
        await execute(resultType, args: args, onEvent: onEvent)
    }

    public func runMutating<R: Codable & Sendable & Equatable>(
        _ resultType: R.Type, args: [String],
        onEvent: (@Sendable (ProgressEvent) -> Void)? = nil
    ) async -> Envelope<R> {
        let previous = mutatingTail
        let task = Task { [weak self] in
            _ = await previous?.value
            _ = self  // keep alive across the await
        }
        mutatingTail = task
        _ = await previous?.value
        defer { if mutatingTail == task { mutatingTail = nil } }
        return await execute(resultType, args: args, onEvent: onEvent)
    }

    private func execute<R: Codable & Sendable & Equatable>(
        _ resultType: R.Type, args: [String],
        onEvent: (@Sendable (ProgressEvent) -> Void)?
    ) async -> Envelope<R> {
        let process = Process()
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

        do { try process.run() } catch {
            return synthetic("could not launch: \(error.localizedDescription)")
        }
        // Drain fully; small outputs never deadlock, large ones need the reads
        // to happen off the termination wait.
        async let outData = out.fileHandleForReading.readToEndAsync()
        async let errData = err.fileHandleForReading.readToEndAsync()
        await withCheckedContinuation { (c: CheckedContinuation<Void, Never>) in
            process.terminationHandler = { _ in c.resume() }
            if !process.isRunning { c.resume() }   // already exited
        }
        let stdout = String(decoding: await outData, as: UTF8.self)
        let stderr = String(decoding: await errData, as: UTF8.self)

        let decoder = ContractDecoder.make()
        var envelope: Envelope<R>?
        for line in stdout.split(separator: "\n", omittingEmptySubsequences: true) {
            let data = Data(line.utf8)
            if line.contains("\"event\""),
               let event = try? decoder.decode(ProgressEvent.self, from: data) {
                onEvent?(event)
            } else if let env = try? decoder.decode(Envelope<R>.self, from: data) {
                envelope = env       // last decodable envelope wins (contract: last line)
            }
        }
        if let envelope { return envelope }
        let tail = stderr.split(separator: "\n").suffix(50).joined(separator: "\n")
        return synthetic(tail.isEmpty ? "no envelope on stdout" : tail)
    }

    private func synthetic<R>(_ message: String) -> Envelope<R> {
        Envelope(ok: false, result: nil,
                 error: PipelineErrorInfo(code: "INTERNAL", message: message))
    }
}

extension FileHandle {
    func readToEndAsync() async -> Data {
        await withCheckedContinuation { continuation in
            DispatchQueue.global().async {
                let data = (try? self.readToEnd()) ?? Data()
                continuation.resume(returning: data)
            }
        }
    }
}
```

Implementation note: the double-await in `runMutating` above is the intent (chain then await); simplify during implementation if the serialization test stays green — the test with the `mkdir` lock is the arbiter. If `terminationHandler` set after exit proves racy, use `process.waitUntilExit()` inside a `Task.detached` with a continuation instead.

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
public enum CropMath {
    public static func nudged(_ window: CropWindow, dx: Double, dy: Double)
    -> CropWindow {
        CropWindow(x: min(max(window.x + dx, 0), 1 - window.w),
                   y: min(max(window.y + dy, 0), 1 - window.h),
                   w: window.w, h: window.h, source: window.source)
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
  - `protocol PipelineRunning: Sendable` — `func status() async -> Envelope<StatusSnapshot>`; `func mutate<R>(_ type: R.Type, args: [String], onEvent: (@Sendable (ProgressEvent) -> Void)?) async -> Envelope<R>`; `func crops(stem: String) async -> Envelope<CropsResult>`. `PipelineClient` gets a conforming extension mapping to `run`/`runMutating` with the canonical arg spellings.
  - `struct ReviewDraft: Sendable { stem: String; baseRevision: String; checks: [String: Bool]; note: String; cropNudges: [String: CropWindow]; isStale: Bool }` — check keys: `"eyes_open"`, `"expressions_natural"`, `"no_blinks_in_crops"`.
  - `@Observable @MainActor final class AppModel`:
    - `init(client: PipelineRunning, sliderDebounce: Duration = .seconds(2))`
    - Published state: `snapshot: StatusSnapshot?`, `drafts: [String: ReviewDraft]`, `banner: PipelineErrorInfo?`, `busyExternally: Bool`, `activeCommand: String?` (nil = idle), `renderProgress: [String: ProgressEvent]` (latest per stem), `selectedStem: String?`, `selectedStyle: String` (default `"natural"`).
    - `func refresh() async` — `client.status()`; on ok: store snapshot, `busyExternally = snapshot.lock.held && activeCommand == nil`, reconcile drafts (below); on error: `banner = error`.
    - Draft reconcile: for each draft, if the photo's `reviewRevision != draft.baseRevision` and no rebase pair matched since the last refresh → `isStale = true` (contents preserved). While `activeCommand != nil` and the command targets that stem, defer reconcile (spec §6.1).
    - `func startDraft(stem: String)` — creates a draft keyed to the photo's current `reviewRevision`, all checks false.
    - `func canApprove(stem: String) -> Bool` — draft exists, all three checks true, `!isStale`, photo `stalePreviews.isEmpty`, `activeCommand == nil`, `!busyExternally`.
    - `func setSlider(stem: String, style: String, temperature: Double?, exposure: Double?)` — stores pending values and debounces `applyAdjust`.
    - `func applyAdjust(stem: String, style: String, temperature: Double?, exposure: Double?) async` — `mutate(AdjustResult…)`; on ok, rebase the stem's draft iff `draft.baseRevision == result.reviewRevisionBefore` → `baseRevision = result.reviewRevisionAfter`; else mark stale. Then `refresh()`.
    - `func approve(stem: String) async` — flush the debouncer; build the review-file JSON (audit strings below, crops = `crops` from status merged with `cropNudges`, `expected_review_revision` = draft.baseRevision); write to `FileManager.default.temporaryDirectory`; `mutate(ApproveResult…, args: ["approve", stem, "--review-file", path, "--json"])`; on ok chain `mutate(RunResult…, args: ["run", "--stem", stem, "--json"])` feeding `renderProgress`; delete temp file; `refresh()`; on `STALE_REVIEW` → banner + mark draft stale.
    - Audit string mapping: `"eyes open — all: pass"`, `"expressions natural: pass"`, `"no blinks in crops: pass"`, plus `"note: \(note)"` when non-empty — only checked items make `canApprove` true, so all three always serialize as `: pass`.
    - `func ingest(paths: [String]) async` — `mutate(IngestResult…, args: ["ingest", "--from"] + paths + ["--delivery-id", UUID().uuidString, "--json"])`, then `mutate(RunResult…, ["run", "--json"])`, then refresh; surfaces skips/conflicts via `banner` when non-empty (message joined).
    - `func deliveries() -> [(id: String?, photos: [PhotoStatus])]` — group by `deliveryId`, `nil` last as "Earlier", newest `ingestedAt` first.

- [ ] **Step 1: Write the failing tests** (fake client; the heart of the task)

```swift
import XCTest
@testable import PrintworksCore

/// Scriptable fake: every call pops the next canned envelope.
final class FakeClient: PipelineRunning, @unchecked Sendable {
    var statusQueue: [Envelope<StatusSnapshot>] = []
    var mutateLog: [[String]] = []
    var mutateHandler: ((_ args: [String]) -> Any)!

    func status() async -> Envelope<StatusSnapshot> { statusQueue.removeFirst() }
    func crops(stem: String) async -> Envelope<CropsResult> {
        Envelope(ok: true, result: CropsResult(
            stem: stem, basis: "faces", windows: [:]), error: nil)
    }
    func mutate<R>(_ type: R.Type, args: [String],
                   onEvent: (@Sendable (ProgressEvent) -> Void)?) async
    -> Envelope<R> {
        mutateLog.append(args)
        return mutateHandler(args) as! Envelope<R>
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
        let model = AppModel(client: fake, sliderDebounce: .zero)
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
        let model = AppModel(client: fake, sliderDebounce: .zero)
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
        let model = AppModel(client: fake, sliderDebounce: .zero)
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
        let model = AppModel(client: fake, sliderDebounce: .zero)
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
        let model = AppModel(client: fake, sliderDebounce: .zero)
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
        let model = AppModel(client: fake, sliderDebounce: .zero)
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
  - `final class RepoWatcher: @unchecked Sendable` — `init(repo: URL, coalesce: Duration = .milliseconds(500))`; `var changes: AsyncStream<Void>` (one element per coalesced burst); `func start()`, `func stop()`. Watches `Input previews sidecars recipes config Output run` under the repo via per-directory `DispatchSource.makeFileSystemObjectSource(fileDescriptor:eventMask:[.write, .rename, .delete])` (kqueue — directory writes fire on entry create/delete/rename; sufficient here because every pipeline mutation creates/replaces files).
  - `startPolling(interval: Duration = .seconds(5))` / `stopPolling()` — the busy-pill fallback; emits a change per tick while active. `AppModel` (Task 7 wiring) starts polling when `busyExternally`, stops otherwise.

- [ ] **Step 1: Write the failing tests**

```swift
import XCTest
@testable import PrintworksCore

final class RepoWatcherTests: XCTestCase {
    func testCoalescedChangeEmission() async throws {
        let repo = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
        for dir in ["Input", "previews", "sidecars", "recipes", "config",
                    "Output", "run"] {
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

Status-dot mapping (single helper used by sidebar + grid badges): `verified`→`Theme.statusPublished`/"Published", `preview_ready`/`review_required`→`Theme.statusReview`/"Needs review", `approved`/`rendered`→accent/"Rendering", else `Theme.statusIngested`/"Ingested". Grid cards: `LazyVGrid(columns: [GridItem(.adaptive(minimum: 260))])`, preview thumb via `NSImage(contentsOfFile:)` in an `.id(photo.previewHashes["natural"] ?? "")`-keyed view (content-hash cache key), badge top-left, `ProgressView(value:)` overlay when `model.renderProgress[stem]` present, `.onTapGesture(count: 2)` → openReview.

- [ ] **Step 1: Implement the four files** per the skeleton (no unit tests — logic already covered in core; the gate is the build).
- [ ] **Step 2: Build** — `xcodegen generate` (if project.yml changed) + `xcodebuild … build` → BUILD SUCCEEDED. Also `swift test --package-path app/PrintworksCore` still green.
- [ ] **Step 3: Manual smoke** — `open` the built app against the real repo (Settings default `~/photo-edits`): grid shows P1036163/P1036170 as Published, sidebar shows "Earlier" group (legacy recipes have no delivery_id). Screenshot for the Task 11 QA set.
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
- Produces: `ReviewScreen(model:)` — large canvas on `Theme.canvas` showing the selected style's preview (`NSImage(contentsOfFile:)`, `.id(previewHash)` so a content-hash change forces reload; never `AsyncImage`/URL cache); segmented style control bound to `model.selectedStyle`; keyboard: `⌘1`–`⌘4` (`.keyboardShortcut("1", modifiers: .command)` on hidden buttons) switch style, `space` toggles `CompareView`, `c` toggles the crop overlay (Task 9), `←`/`→` move `model.selectedStem` through the open delivery; per-style "preview out of date — re-render" chip when the style ∈ `stalePreviews` → `model.rerenderPreview(stem:style:)` (`preview <stem> <style> --json` via `mutate`); "rendering preview…" shimmer overlay while that command is `activeCommand`.
- `CompareView(model:)` — 2×2 grid of the four styles' previews with labels; click a panel → sets `selectedStyle`, dismisses compare.

- [ ] **Step 1: Implement** both views; add `rerenderPreview` to `AppModel` **with a unit test first** in `AppModelTests` (asserts args `["preview", "P1", "filmic", "--json"]` and a refresh after).
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
  - `CropOverlayView(windows:onNudge:)` — draws the 8×10 window solid amber, 5×7 dashed, over the canvas in normalized→view coordinate mapping (`GeometryReader`); `DragGesture` translates via `CropMath.nudged` (aspect/size locked by construction) and reports the final window through `onNudge(cropName, window)` → stored in the draft's `cropNudges`; a small `basis` chip ("centered fallback" / "detection failed — centered") when the crops result's basis ≠ "faces"/"persisted".
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
  - Settings: two fields (repo path default `~/photo-edits`, python path default `<repo>/.venv/bin/python`) stored in `UserDefaults` keys `repoPath`/`pythonPath`; Validate button runs `status --json` with candidate values via a throwaway `PipelineClient` and shows ok/error inline; saving rebuilds the model's client + watcher.
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
  - `SmokeTests` — builds a temp fixture repo (dirs from `tests/conftest.py` list; two fake photos: recipes + tiny preview JPG bytes) and a stub `python` shell script that answers `status --json` from a canned `StatusSnapshot` JSON (with `stale_previews: []`), `adjust`/`approve`/`run` from canned envelopes; drives the REAL `PipelineClient` + `AppModel` end-to-end: refresh → startDraft → check all → approve → asserts the approve/run arg sequence and final refresh landed. This is the app-side twin of Plan 1's fixtures — it catches wiring drift the unit fakes can't.
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

- [ ] **Step 1: Write SmokeTests** (canned JSON inline in the test file; stub script pattern from Task 3) → fail (compile) → implement any missing glue.
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
