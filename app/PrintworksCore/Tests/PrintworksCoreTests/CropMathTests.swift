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
