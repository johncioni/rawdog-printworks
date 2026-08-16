import Foundation

public enum SettingsStatusValidation: Sendable, Equatable {
    case valid
    case invalid(String)
    case transientError(String)

    public var allowsSave: Bool {
        switch self {
        case .valid, .transientError: true
        case .invalid: false
        }
    }

    public static func classify(
        _ result: CommandResult<StatusSnapshot>
    ) -> SettingsStatusValidation {
        if result.envelope.ok, result.envelope.result != nil {
            return .valid
        }
        let error = result.envelope.error
            ?? PipelineErrorInfo(code: "INTERNAL",
                                 message: "Status returned no result.")
        switch error.code {
        case "TOOLCHAIN_FAILED", "NOT_FOUND", "BAD_INPUT":
            return .invalid(error.message)
        case "INTERNAL" where error.message.hasPrefix("could not launch:"):
            return .invalid(error.message)
        default:
            return .transientError(error.message)
        }
    }
}
