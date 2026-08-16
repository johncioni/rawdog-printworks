import XCTest
@testable import PrintworksCore

final class SettingsStatusValidationTests: XCTestCase {
    func testTransientStatusErrorAllowsSaveButConfigurationFailureDoesNot() {
        let transient = CommandResult<StatusSnapshot>(
            envelope: Envelope(
                ok: false, result: nil,
                error: PipelineErrorInfo(
                    code: "INTERNAL", message: "temporary status read failed")),
            stderrTail: "")
        let invalid = CommandResult<StatusSnapshot>(
            envelope: Envelope(
                ok: false, result: nil,
                error: PipelineErrorInfo(
                    code: "TOOLCHAIN_FAILED", message: "RawTherapee missing")),
            stderrTail: "")

        XCTAssertTrue(SettingsStatusValidation.classify(transient).allowsSave)
        XCTAssertFalse(SettingsStatusValidation.classify(invalid).allowsSave)
    }
}
