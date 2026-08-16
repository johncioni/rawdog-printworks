import Foundation

public struct PipelineConfig: Sendable {
    public let repo: URL
    public let python: URL
    public init(repo: URL, python: URL) { self.repo = repo; self.python = python }
}

public enum PipelineFailure: Error, Equatable {
    case internalError(String)
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
        let cancellation = ProcessCancellation(process: process)
        return await withTaskCancellationHandler {
            await execute(resultType, args: args, onEvent: onEvent,
                          process: process, cancellation: cancellation)
        } onCancel: {
            cancellation.cancel()
        }
    }

    private func execute<R: Codable & Sendable & Equatable>(
        _ resultType: R.Type, args: [String],
        onEvent: (@Sendable (ProgressEvent) -> Void)?, process: Process,
        cancellation: ProcessCancellation
    ) async -> CommandResult<R> {
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

        // Termination signal: a single-shot event, safe regardless of
        // whether the process terminates before or after `wait()` below
        // starts observing it. terminationHandler is attached BEFORE
        // run() so a very short-lived process can't fire it before
        // anything is listening.
        let termination = TerminationSignal()
        process.terminationHandler = { _ in termination.markTerminated() }
        do {
            try process.run()
            cancellation.didStart()
        } catch {
            process.terminationHandler = nil
            return CommandResult(
                envelope: synthetic("could not launch: \(error.localizedDescription)"),
                stderrTail: "")
        }

        // Live line-parsing: events reach onEvent while the process runs
        // (renders take minutes; progress buffered until exit is useless).
        //
        // Concurrency history (review round 1, Finding 1 — CRITICAL):
        // the original implementation used Foundation's
        // `FileHandle.readabilityHandler`, which runs on a global,
        // non-serial dispatch queue and — confirmed by a stress test
        // (hundreds of rapid progress lines) and by ThreadSanitizer, not
        // a hypothetical — CAN invoke the SAME pipe's handler concurrently
        // on two threads. Reading `availableData` outside a lock and only
        // appending it under one meant two racing invocations could
        // append their chunks in whichever order won the lock rather than
        // the order the bytes were actually read, splicing a line's JSON
        // mid-string; `try? decoder.decode` then silently swallowed the
        // parse failure and the event vanished with no signal.
        //
        // A first fix wrapped each handler firing in `DispatchQueue.sync`
        // on a dedicated serial queue per pipe. That closed most of the
        // loss but not all of it under sustained stress: a residual
        // shortfall (about 1 run in 8, concentrated in the last few lines
        // near process exit) persisted. That residual is a shutdown-window
        // race — an already in-flight handler invocation racing the final
        // drain against Foundation's own internal source-cancellation
        // timing — that synchronizing the *handler* alone cannot fully
        // close, because `readabilityHandler`'s concurrent-invocation
        // behavior is undocumented and not fully under our control.
        //
        // This version removes `readabilityHandler` entirely. Each pipe
        // gets exactly ONE reader: `drain` below, a single background loop
        // that blocks on `availableData` until EOF. With only one caller
        // ever touching a given pipe's `LineCollector`, concurrent access
        // isn't merely synchronized — it's structurally impossible, so
        // there is nothing left to race, no matter how Foundation
        // internally schedules anything.
        let decoder = ContractDecoder.make()
        let collector = LineCollector()
        let errCollector = LineCollector()

        async let stdoutDone: Void = drain(out.fileHandleForReading, into: collector) { line in
            if line.contains("\"event\""),
               let event = try? decoder.decode(ProgressEvent.self,
                                               from: Data(line.utf8)) {
                onEvent?(event)
            }
        }
        async let stderrDone: Void = drain(err.fileHandleForReading, into: errCollector, onLine: nil)
        async let terminated: Void = termination.wait()
        _ = await (stdoutDone, stderrDone, terminated)

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

    /// Reads `handle` to EOF on a dedicated background thread, one blocking
    /// `availableData` call at a time, feeding each newly-completed line to
    /// `onLine` as soon as it is split off. This is the pipe's ONLY reader —
    /// never raced by a second concurrent invocation the way
    /// `FileHandle.readabilityHandler` could be — so `collector` needs no
    /// synchronization of its own beyond what one sequential caller
    /// requires. `availableData` returning empty `Data` is EOF (the writer
    /// closed its end, which happens at/after process exit since we hold
    /// no duplicate write descriptor of our own).
    private func drain(
        _ handle: FileHandle, into collector: LineCollector,
        onLine: (@Sendable (String) -> Void)?
    ) async {
        await withCheckedContinuation { (c: CheckedContinuation<Void, Never>) in
            DispatchQueue.global(qos: .utility).async {
                while true {
                    let chunk = handle.availableData
                    if chunk.isEmpty { break }
                    for line in collector.completeLines(appending: chunk) {
                        onLine?(line)
                    }
                }
                collector.flushRemainder()
                c.resume()
            }
        }
    }

    private func synthetic<R>(_ message: String) -> Envelope<R> {
        Envelope(ok: false, result: nil,
                 error: PipelineErrorInfo(code: "INTERNAL", message: message))
    }
}

/// Bridges structured-concurrency cancellation to Foundation.Process while
/// closing the race where cancellation arrives just before `process.run()`.
private final class ProcessCancellation: @unchecked Sendable {
    private let lock = NSLock()
    private let process: Process
    private var started = false
    private var cancellationRequested = false

    init(process: Process) {
        self.process = process
    }

    func didStart() {
        let shouldTerminate = lock.withLock {
            started = true
            return cancellationRequested
        }
        if shouldTerminate, process.isRunning {
            process.terminate()
        }
    }

    func cancel() {
        let shouldTerminate = lock.withLock {
            cancellationRequested = true
            return started
        }
        if shouldTerminate, process.isRunning {
            process.terminate()
        }
    }
}

/// Single-shot "has X happened yet" signal, safe regardless of whether
/// `markTerminated()` or `wait()` happens first. Needed because
/// `Process.terminationHandler` can fire before our code gets around to
/// awaiting it (very short-lived stub scripts race this in practice); firing
/// into a not-yet-created continuation would otherwise be lost, hanging
/// `wait()` forever.
final class TerminationSignal: @unchecked Sendable {
    private let lock = NSLock()
    private var alreadyTerminated = false
    private var continuation: CheckedContinuation<Void, Never>?

    func markTerminated() {
        lock.lock()
        if let continuation {
            self.continuation = nil
            lock.unlock()
            continuation.resume()
        } else {
            alreadyTerminated = true
            lock.unlock()
        }
    }

    func wait() async {
        await withCheckedContinuation { (c: CheckedContinuation<Void, Never>) in
            lock.lock()
            if alreadyTerminated {
                lock.unlock()
                c.resume()
            } else {
                continuation = c
                lock.unlock()
            }
        }
    }
}

/// Incremental line splitter for one pipe's stdout/stderr stream, driven by
/// exactly one sequential reader (`PipelineClient.drain`) — see that
/// function's doc comment for why a single-reader design, not a lock, is
/// what keeps this type's mutable state safe. `completeLines(appending:)`
/// returns newly completed lines and retains the unterminated remainder;
/// `allLines` is the full ordered history; `flushRemainder()` moves
/// whatever's left in the buffer (a final line with no trailing newline)
/// into `allLines` — call it once, after the reader sees EOF.
final class LineCollector: @unchecked Sendable {
    private var buffer = ""
    private var lines: [String] = []

    var allLines: [String] { lines }

    func completeLines(appending data: Data) -> [String] {
        buffer += String(decoding: data, as: UTF8.self)
        var completed: [String] = []
        while let newline = buffer.firstIndex(of: "\n") {
            completed.append(String(buffer[..<newline]))
            buffer.removeSubrange(...newline)
        }
        lines.append(contentsOf: completed)
        return completed
    }

    func flushRemainder() {
        if !buffer.isEmpty {
            lines.append(buffer)
            buffer = ""
        }
    }
}
