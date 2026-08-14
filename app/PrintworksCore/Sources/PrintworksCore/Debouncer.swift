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
        let action: (@Sendable () async -> Void)? = lock.withLock {
            let action = pendingAction
            pendingAction = nil
            pendingTask?.cancel()
            pendingTask = nil
            return action
        }
        await action?()
    }
}
