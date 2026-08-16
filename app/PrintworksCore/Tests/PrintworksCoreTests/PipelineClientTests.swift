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
        // `$PWD` reflects the kernel's canonical cwd (getcwd(3) resolves every
        // symlink, including the /var, /tmp, /etc -> /private/* ones).
        // `URL.resolvingSymlinksInPath()` deliberately leaves those specific
        // mount points unresolved (documented Foundation/NSPathUtilities
        // compatibility special-case), so it is not a reliable oracle here —
        // canonicalize with realpath(3) instead, matching what the kernel did.
        XCTAssertTrue(repoField.hasPrefix(realpath(dir.path))
                      || repoField.hasPrefix(dir.path))
        XCTAssertTrue(repoField.hasSuffix(
            "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin"))
    }

    private func realpath(_ path: String) -> String {
        guard let resolved = Foundation.realpath(path, nil) else { return path }
        defer { free(resolved) }
        return String(cString: resolved)
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

    func testCancellingRunTerminatesTheSubprocess() async throws {
        let (client, dir) = try makeStub("""
        echo started > "$PWD/started"
        trap 'echo terminated > "$PWD/terminated"; exit 0' TERM
        while [ ! -f "$PWD/release" ]; do sleep 0.02; done
        echo '{"ok":true,"result":{"stem":"P1","basis":"faces","windows":{}}}'
        """)
        defer { try? FileManager.default.removeItem(at: dir) }
        let run = Task {
            await client.run(CropsResult.self, args: ["crops", "--json"])
        }
        let started = dir.appendingPathComponent("started")
        for _ in 0..<100 where !FileManager.default.fileExists(atPath: started.path) {
            try await Task.sleep(for: .milliseconds(5))
        }
        XCTAssertTrue(FileManager.default.fileExists(atPath: started.path))

        run.cancel()
        try await Task.sleep(for: .milliseconds(250))
        let terminatedBeforeRelease = FileManager.default.fileExists(
            atPath: dir.appendingPathComponent("terminated").path)
        try Data().write(to: dir.appendingPathComponent("release"))
        _ = await run.value

        XCTAssertTrue(terminatedBeforeRelease,
                      "task cancellation must terminate the live subprocess")
    }

    func testHighVolumeBurstDeliversEveryEventInOrder() async throws {
        // Regression guard for the readabilityHandler race (Finding 1,
        // review round 1): Foundation's FileHandle.readabilityHandler runs
        // on a global, non-serial dispatch queue and can be invoked again
        // for the SAME pipe before a prior invocation returns. A fast,
        // high-volume burst — progress lines interleaved with stderr noise,
        // spanning many separate read()s since the total payload is far
        // larger than one pipe buffer — is what reproduces the race
        // (confirmed against the pre-fix code: this test failed the
        // count assertion below in every run, delivering well under 800
        // of 800 events; see task-3-report.md for the exact numbers).
        let total = 800
        let body = """
        i=1
        while [ $i -le \(total) ]; do
          echo "{\\"event\\":\\"progress\\",\\"stem\\":\\"P1\\",\\"stage\\":\\"render\\",\\"index\\":$i,\\"total\\":\(total),\\"detail\\":\\"x\\"}"
          echo "noise-$i" 1>&2
          i=$((i+1))
        done
        echo '{"ok":true,"result":{"stem":"P1","state":"approved","fingerprint":"f"}}'
        """
        let (client, _) = try makeStub(body)

        nonisolated(unsafe) var events: [ProgressEvent] = []
        let result = await client.run(ApproveResult.self, args: ["x"]) {
            events.append($0)
        }

        XCTAssertTrue(result.envelope.ok)
        XCTAssertEqual(events.count, total,
            "expected every one of \(total) progress events to arrive; got " +
            "\(events.count) — a shortfall means the readabilityHandler race " +
            "dropped events again")
        XCTAssertEqual(events.compactMap(\.index), Array(1...total),
            "events must arrive in emission order, not just in full count")
    }
}
