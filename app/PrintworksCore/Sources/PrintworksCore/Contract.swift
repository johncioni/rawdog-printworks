import Foundation

public enum Contract { public static let version = 1 }

public struct PipelineErrorInfo: Codable, Sendable, Equatable {
    public let code: String
    public let message: String

    public init(code: String, message: String) {
        self.code = code
        self.message = message
    }
}

public struct Envelope<R: Codable & Sendable & Equatable>: Codable, Sendable, Equatable {
    public let ok: Bool
    public let result: R?
    public let error: PipelineErrorInfo?

    public init(ok: Bool, result: R?, error: PipelineErrorInfo?) {
        self.ok = ok
        self.result = result
        self.error = error
    }
}

public struct ProgressEvent: Codable, Sendable, Equatable {
    public let event: String
    public let stem: String?
    public let stage: String?
    public let index: Int?
    public let total: Int?
    public let detail: String?

    public init(event: String, stem: String?, stage: String?,
                index: Int?, total: Int?, detail: String?) {
        self.event = event
        self.stem = stem
        self.stage = stage
        self.index = index
        self.total = total
        self.detail = detail
    }
}

public struct ToolchainIssue: Codable, Sendable, Equatable {
    public let name: String?
    public let problem: String?

    public init(name: String?, problem: String?) {
        self.name = name
        self.problem = problem
    }
}

public struct ToolchainStatus: Codable, Sendable, Equatable {
    public let ok: Bool
    public let failures: [ToolchainIssue]

    public init(ok: Bool, failures: [ToolchainIssue]) {
        self.ok = ok
        self.failures = failures
    }
}

public struct LockStatus: Codable, Sendable, Equatable {
    public let held: Bool
    public let stale: Bool
    public let pid: Int?

    public init(held: Bool, stale: Bool, pid: Int?) {
        self.held = held
        self.stale = stale
        self.pid = pid
    }
}

public struct Control: Codable, Sendable, Equatable {
    public let value: Double?
    public let source: String

    public init(value: Double?, source: String) {
        self.value = value
        self.source = source
    }
}

public struct StyleAdjustments: Codable, Sendable, Equatable {
    public let temperature: Control
    public let exposure: Control

    public init(temperature: Control, exposure: Control) {
        self.temperature = temperature
        self.exposure = exposure
    }
}

public struct CropWindow: Codable, Sendable, Equatable {
    public let x: Double
    public let y: Double
    public let w: Double
    public let h: Double
    public let source: String?

    public init(x: Double, y: Double, w: Double, h: Double, source: String?) {
        self.x = x
        self.y = y
        self.w = w
        self.h = h
        self.source = source
    }
}

public struct PublishedInfo: Codable, Sendable, Equatable {
    public let version: String?
    public let path: String?
    public let artifactCount: Int?

    public init(version: String?, path: String?, artifactCount: Int?) {
        self.version = version
        self.path = path
        self.artifactCount = artifactCount
    }
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

    public init(stem: String, state: String, deliveryId: String?,
                ingestedAt: String?, reviewRevision: String,
                previews: [String: String?], previewHashes: [String: String?],
                stalePreviews: [String],
                adjustments: [String: StyleAdjustments],
                crops: [String: CropWindow], expressionAudit: [String],
                published: PublishedInfo) {
        self.stem = stem
        self.state = state
        self.deliveryId = deliveryId
        self.ingestedAt = ingestedAt
        self.reviewRevision = reviewRevision
        self.previews = previews
        self.previewHashes = previewHashes
        self.stalePreviews = stalePreviews
        self.adjustments = adjustments
        self.crops = crops
        self.expressionAudit = expressionAudit
        self.published = published
    }
}

public struct StatusSnapshot: Codable, Sendable, Equatable {
    public let repo: String
    public let toolchain: ToolchainStatus
    public let lock: LockStatus
    public let styles: [String]
    public let photos: [PhotoStatus]

    public init(repo: String, toolchain: ToolchainStatus, lock: LockStatus,
                styles: [String], photos: [PhotoStatus]) {
        self.repo = repo
        self.toolchain = toolchain
        self.lock = lock
        self.styles = styles
        self.photos = photos
    }
}

public struct AdjustResult: Codable, Sendable, Equatable {
    public let stem: String
    public let style: String
    public let preview: String
    public let temperature: Control
    public let exposure: Control
    public let reviewRevisionBefore: String
    public let reviewRevisionAfter: String

    public init(stem: String, style: String, preview: String,
                temperature: Control, exposure: Control,
                reviewRevisionBefore: String, reviewRevisionAfter: String) {
        self.stem = stem
        self.style = style
        self.preview = preview
        self.temperature = temperature
        self.exposure = exposure
        self.reviewRevisionBefore = reviewRevisionBefore
        self.reviewRevisionAfter = reviewRevisionAfter
    }
}

/// `basis` is `null` when every window is persisted (no suggestion ran; Plan 1 Task 9).
public struct CropsResult: Codable, Sendable, Equatable {
    public let stem: String
    public let basis: String?
    public let windows: [String: CropWindow]

    public init(stem: String, basis: String?, windows: [String: CropWindow]) {
        self.stem = stem
        self.basis = basis
        self.windows = windows
    }
}

public struct ApproveResult: Codable, Sendable, Equatable {
    public let stem: String
    public let state: String
    public let fingerprint: String

    public init(stem: String, state: String, fingerprint: String) {
        self.stem = stem
        self.state = state
        self.fingerprint = fingerprint
    }
}

public struct FileNote: Codable, Sendable, Equatable {
    public let file: String
    public let reason: String

    public init(file: String, reason: String) {
        self.file = file
        self.reason = reason
    }
}

/// `code` carries any pipeline error code (see the ten values enumerated in
/// `PipelineErrorInfo`'s doc comment). Modeled as `String`, not a closed enum,
/// so an unrecognised future code decodes instead of throwing.
public struct FileFailure: Codable, Sendable, Equatable {
    public let file: String
    public let code: String
    public let message: String

    public init(file: String, code: String, message: String) {
        self.file = file
        self.code = code
        self.message = message
    }
}

public struct IngestResult: Codable, Sendable, Equatable {
    public let ingested: [String]
    public let skipped: [FileNote]
    public let conflicts: [FileNote]
    public let failed: [FileFailure]

    public init(ingested: [String], skipped: [FileNote],
                conflicts: [FileNote], failed: [FileFailure]) {
        self.ingested = ingested
        self.skipped = skipped
        self.conflicts = conflicts
        self.failed = failed
    }
}

public struct PublishedPhoto: Codable, Sendable, Equatable {
    public let stem: String
    public let version: String
    public let artifactCount: Int

    public init(stem: String, version: String, artifactCount: Int) {
        self.stem = stem
        self.version = version
        self.artifactCount = artifactCount
    }
}

public struct AdvancedPhoto: Codable, Sendable, Equatable {
    public let stem: String
    public let state: String

    public init(stem: String, state: String) {
        self.stem = stem
        self.state = state
    }
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

    public init(stem: String, code: String, message: String) {
        self.stem = stem
        self.code = code
        self.message = message
    }
}

public struct RunResult: Codable, Sendable, Equatable {
    public let published: [PublishedPhoto]
    public let advanced: [AdvancedPhoto]
    public let failed: [StemFailure]

    public init(published: [PublishedPhoto], advanced: [AdvancedPhoto],
                failed: [StemFailure]) {
        self.published = published
        self.advanced = advanced
        self.failed = failed
    }
}

public enum ContractDecoder {
    public static func make() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }
}
