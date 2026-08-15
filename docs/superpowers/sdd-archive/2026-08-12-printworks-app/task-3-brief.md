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

