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
