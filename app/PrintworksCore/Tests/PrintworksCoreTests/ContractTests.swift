import XCTest
@testable import PrintworksCore

final class ContractTests: XCTestCase {
    func testPackageBuilds() { XCTAssertEqual(Contract.version, 1) }
}
