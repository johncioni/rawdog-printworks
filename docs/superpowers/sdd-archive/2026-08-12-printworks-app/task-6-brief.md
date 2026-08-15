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

