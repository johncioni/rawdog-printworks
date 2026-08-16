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

