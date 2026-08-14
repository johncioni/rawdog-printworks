import Foundation

public enum Contract { public static let version = 1 }

public struct PipelineErrorInfo: Codable, Sendable, Equatable {
    public let code: String
    public let message: String
}

public struct Envelope<R: Codable & Sendable & Equatable>: Codable, Sendable, Equatable {
    public let ok: Bool
    public let result: R?
    public let error: PipelineErrorInfo?
}

public struct ProgressEvent: Codable, Sendable, Equatable {
    public let event: String
    public let stem: String?
    public let stage: String?
    public let index: Int?
    public let total: Int?
    public let detail: String?
}

public struct ToolchainIssue: Codable, Sendable, Equatable {
    public let name: String?
    public let problem: String?
}

public struct ToolchainStatus: Codable, Sendable, Equatable {
    public let ok: Bool
    public let failures: [ToolchainIssue]
}

public struct LockStatus: Codable, Sendable, Equatable {
    public let held: Bool
    public let stale: Bool
    public let pid: Int?
}

public struct Control: Codable, Sendable, Equatable {
    public let value: Double?
    public let source: String
}

public struct StyleAdjustments: Codable, Sendable, Equatable {
    public let temperature: Control
    public let exposure: Control
}

public struct CropWindow: Codable, Sendable, Equatable {
    public let x: Double
    public let y: Double
    public let w: Double
    public let h: Double
    public let source: String?
}

public struct PublishedInfo: Codable, Sendable, Equatable {
    public let version: String?
    public let path: String?
    public let artifactCount: Int?
}

public struct PhotoStatus: Codable, Sendable, Equatable {
    public let stem: String
    public let state: String
    public let deliveryId: String?
    public let ingestedAt: String?
    public let reviewRevision: String
    public let previews: [String: String?]
    public let previewHashes: [String: String?]
    public let stalePreviews: [String]
    public let adjustments: [String: StyleAdjustments]
    public let crops: [String: CropWindow]
    public let expressionAudit: [String]
    public let published: PublishedInfo
}

public struct StatusSnapshot: Codable, Sendable, Equatable {
    public let repo: String
    public let toolchain: ToolchainStatus
    public let lock: LockStatus
    public let styles: [String]
    public let photos: [PhotoStatus]
}

public struct AdjustResult: Codable, Sendable, Equatable {
    public let stem: String
    public let style: String
    public let preview: String
    public let temperature: Control
    public let exposure: Control
    public let reviewRevisionBefore: String
    public let reviewRevisionAfter: String
}

/// `basis` is `null` when every window is persisted (no suggestion ran; Plan 1 Task 9).
public struct CropsResult: Codable, Sendable, Equatable {
    public let stem: String
    public let basis: String?
    public let windows: [String: CropWindow]
}

public struct ApproveResult: Codable, Sendable, Equatable {
    public let stem: String
    public let state: String
    public let fingerprint: String
}

public struct FileNote: Codable, Sendable, Equatable {
    public let file: String
    public let reason: String
}

/// `code` carries any pipeline error code (see the ten values enumerated in
/// `PipelineErrorInfo`'s doc comment). Modeled as `String`, not a closed enum,
/// so an unrecognised future code decodes instead of throwing.
public struct FileFailure: Codable, Sendable, Equatable {
    public let file: String
    public let code: String
    public let message: String
}

public struct IngestResult: Codable, Sendable, Equatable {
    public let ingested: [String]
    public let skipped: [FileNote]
    public let conflicts: [FileNote]
    public let failed: [FileFailure]
}

public struct PublishedPhoto: Codable, Sendable, Equatable {
    public let stem: String
    public let version: String
    public let artifactCount: Int
}

public struct AdvancedPhoto: Codable, Sendable, Equatable {
    public let stem: String
    public let state: String
}

/// `code` carries any pipeline error code the driver can attach to a
/// per-stem failure — LOCK_HELD, TOOLCHAIN_FAILED, RENDER_FAILED,
/// VERIFY_FAILED, INVALID_STATE, STALE_REVIEW, PARTIAL_FAILURE, NOT_FOUND,
/// BAD_INPUT, INTERNAL, or any future addition. Modeled as `String` (not a
/// closed enum over the values seen in any one fixture) so every current
/// code decodes and an unrecognised future code does not crash the decode.
public struct StemFailure: Codable, Sendable, Equatable {
    public let stem: String
    public let code: String
    public let message: String
}

public struct RunResult: Codable, Sendable, Equatable {
    public let published: [PublishedPhoto]
    public let advanced: [AdvancedPhoto]
    public let failed: [StemFailure]
}

public enum ContractDecoder {
    public static func make() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }
}
