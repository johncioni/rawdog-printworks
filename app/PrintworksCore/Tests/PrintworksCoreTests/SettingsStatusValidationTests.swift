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
        let launchFailure = CommandResult<StatusSnapshot>(
            envelope: Envelope(
                ok: false, result: nil,
                error: PipelineErrorInfo(
                    code: "INTERNAL",
                    message: "could not launch: Python executable missing")),
            stderrTail: "")

        let transientState = SettingsStatusValidation.classify(transient)
        XCTAssertEqual(transientState,
                       .transientError("temporary status read failed"))
        XCTAssertTrue(transientState.allowsSave)

        let invalidState = SettingsStatusValidation.classify(invalid)
        XCTAssertEqual(invalidState, .invalid("RawTherapee missing"))
        XCTAssertFalse(invalidState.allowsSave)

        let launchFailureState = SettingsStatusValidation.classify(launchFailure)
        XCTAssertEqual(
            launchFailureState,
            .invalid("could not launch: Python executable missing"))
        XCTAssertFalse(launchFailureState.allowsSave)
    }
}
