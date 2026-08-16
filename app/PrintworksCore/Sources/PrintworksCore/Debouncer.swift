import Foundation

public final class Debouncer: @unchecked Sendable {
    private let delay: Duration
    private let lock = NSLock()
    private var pendingTask: Task<Void, Never>?
    private var pendingAction: (@Sendable () async -> Void)?
    private var generation: UInt64 = 0

    public init(delay: Duration) { self.delay = delay }

    public var hasPending: Bool {
        lock.lock(); defer { lock.unlock() }
        return pendingAction != nil
    }

    public func schedule(_ action: @escaping @Sendable () async -> Void) {
        lock.lock()
        pendingTask?.cancel()
        generation &+= 1
        let scheduledGeneration = generation
        pendingAction = action
        let delay = delay
        pendingTask = Task { [weak self] in
            try? await Task.sleep(for: delay)
            guard !Task.isCancelled else { return }
            await self?.fire(scheduledGeneration: scheduledGeneration)
        }
        lock.unlock()
    }

    public func flush() async {
        let (action, task): ((@Sendable () async -> Void)?, Task<Void, Never>?) =
            lock.withLock {
                generation &+= 1
                let action = pendingAction
                let task = pendingTask
                pendingAction = nil
                pendingTask = nil
                return (action, task)
            }
        task?.cancel()
        await action?()
    }

    /// The timer-fired path clears its stored task reference without cancelling
    /// that same task. The generation also prevents an old timer that wakes as
    /// `schedule` replaces it from stealing the newer action.
    private func fire(scheduledGeneration: UInt64) async {
        let action: (@Sendable () async -> Void)? = lock.withLock {
            guard scheduledGeneration == generation else { return nil }
            let action = pendingAction
            pendingAction = nil
            pendingTask = nil
            return action
        }
        await action?()
    }
}
