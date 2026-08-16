import Foundation
import XCTest
@testable import PrintworksCore

@MainActor
final class SmokeTests: XCTestCase {
    private static let initialStatusJSON = #"{"ok":true,"result":{"repo":"/fixture","toolchain":{"ok":true,"failures":[]},"lock":{"held":false,"stale":false,"pid":null},"styles":["natural"],"photos":[{"stem":"P1","state":"review_required","delivery_id":"fixture-delivery","ingested_at":"2026-08-12T12:00:00Z","review_revision":"r1","previews":{"natural":"previews/P1-natural.jpg"},"preview_hashes":{"natural":"p1-r1"},"stale_previews":[],"adjustments":{},"crops":{"8x10":{"x":0.1,"y":0.1,"w":0.8,"h":0.8,"source":"persisted"}},"expression_audit":[],"published":{"version":null,"path":null,"artifact_count":null}},{"stem":"P2","state":"review_required","delivery_id":"fixture-delivery","ingested_at":"2026-08-12T12:00:01Z","review_revision":"p2-r1","previews":{"natural":"previews/P2-natural.jpg"},"preview_hashes":{"natural":"p2-r1"},"stale_previews":[],"adjustments":{},"crops":{"8x10":{"x":0.1,"y":0.1,"w":0.8,"h":0.8,"source":"persisted"}},"expression_audit":[],"published":{"version":null,"path":null,"artifact_count":null}}]}}"#

    private static let adjustedStatusJSON = #"{"ok":true,"result":{"repo":"/fixture","toolchain":{"ok":true,"failures":[]},"lock":{"held":false,"stale":false,"pid":null},"styles":["natural"],"photos":[{"stem":"P1","state":"review_required","delivery_id":"fixture-delivery","ingested_at":"2026-08-12T12:00:00Z","review_revision":"r2","previews":{"natural":"previews/P1-natural.jpg"},"preview_hashes":{"natural":"p1-r2"},"stale_previews":[],"adjustments":{"natural":{"temperature":{"value":5600,"source":"sidecar"},"exposure":{"value":null,"source":"camera"}}},"crops":{"8x10":{"x":0.1,"y":0.1,"w":0.8,"h":0.8,"source":"persisted"}},"expression_audit":[],"published":{"version":null,"path":null,"artifact_count":null}},{"stem":"P2","state":"review_required","delivery_id":"fixture-delivery","ingested_at":"2026-08-12T12:00:01Z","review_revision":"p2-r1","previews":{"natural":"previews/P2-natural.jpg"},"preview_hashes":{"natural":"p2-r1"},"stale_previews":[],"adjustments":{},"crops":{"8x10":{"x":0.1,"y":0.1,"w":0.8,"h":0.8,"source":"persisted"}},"expression_audit":[],"published":{"version":null,"path":null,"artifact_count":null}}]}}"#

    private static let finalStatusJSON = #"{"ok":true,"result":{"repo":"/fixture","toolchain":{"ok":true,"failures":[]},"lock":{"held":false,"stale":false,"pid":null},"styles":["natural"],"photos":[{"stem":"P1","state":"published","delivery_id":"fixture-delivery","ingested_at":"2026-08-12T12:00:00Z","review_revision":"r3","previews":{"natural":"previews/P1-natural.jpg"},"preview_hashes":{"natural":"p1-r2"},"stale_previews":[],"adjustments":{"natural":{"temperature":{"value":5600,"source":"sidecar"},"exposure":{"value":null,"source":"camera"}}},"crops":{"8x10":{"x":0.1,"y":0.1,"w":0.8,"h":0.8,"source":"persisted"}},"expression_audit":["eyes open — all: pass","expressions natural: pass","no blinks in crops: pass"],"published":{"version":"v001","path":"Output/photos/P1","artifact_count":29}},{"stem":"P2","state":"review_required","delivery_id":"fixture-delivery","ingested_at":"2026-08-12T12:00:01Z","review_revision":"p2-r1","previews":{"natural":"previews/P2-natural.jpg"},"preview_hashes":{"natural":"p2-r1"},"stale_previews":[],"adjustments":{},"crops":{"8x10":{"x":0.1,"y":0.1,"w":0.8,"h":0.8,"source":"persisted"}},"expression_audit":[],"published":{"version":null,"path":null,"artifact_count":null}}]}}"#

    private static let adjustJSON = #"{"ok":true,"result":{"stem":"P1","style":"natural","preview":"previews/P1-natural.jpg","temperature":{"value":5600,"source":"sidecar"},"exposure":{"value":null,"source":"camera"},"review_revision_before":"r1","review_revision_after":"r2"}}"#
    private static let previewJSON = #"{"ok":true,"result":{"stem":"P1","style":"natural","preview":"previews/P1-natural.jpg","temperature":{"value":5600,"source":"sidecar"},"exposure":{"value":null,"source":"camera"},"review_revision_before":"r1","review_revision_after":"r2"}}"#
    private static let approveJSON = #"{"ok":true,"result":{"stem":"P1","state":"approved","fingerprint":"fixture-fingerprint"}}"#
    private static let runJSON = #"{"ok":true,"result":{"published":[{"stem":"P1","version":"v001","artifact_count":29}],"advanced":[],"failed":[]}}"#

    func testFullReviewFlowAgainstStubPipeline() async throws {
        let repo = try makeFixtureRepo()
        defer { try? FileManager.default.removeItem(at: repo) }
        let stub = try makeStubPython(at: repo)
        let client = PipelineClient(
            config: PipelineConfig(repo: repo, python: stub),
            executableOverride: stub)
        let model = AppModel(client: client, repo: repo, sliderDebounce: .zero)

        await model.refresh()
        XCTAssertEqual(try XCTUnwrap(model.snapshot).photos.count, 2)

        model.startDraft(stem: "P1")
        model.setSlider(stem: "P1", style: "natural", temperature: 5600,
                        exposure: nil)
        await model.flushPendingAdjustments(stem: "P1")
        let adjustedDraft = try XCTUnwrap(model.drafts["P1"])
        XCTAssertEqual(adjustedDraft.baseRevision, "r2")
        XCTAssertFalse(adjustedDraft.isStale)

        for key in ["eyes_open", "expressions_natural", "no_blinks_in_crops"] {
            model.setDraftCheck(stem: "P1", key: key, isChecked: true)
        }
        XCTAssertTrue(model.canApprove(stem: "P1"))
        await model.approve(stem: "P1")

        let calls = try String(
            contentsOf: repo.appendingPathComponent("stub-calls.log"),
            encoding: .utf8
        ).split(separator: "\n").map(String.init)
        XCTAssertEqual(calls.map { $0.split(separator: " ").first.map(String.init) },
                       ["status", "adjust", "status", "approve", "run", "status"])
        XCTAssertEqual(calls[1],
                       "adjust --stem P1 --style natural --temperature 5600 --json")
        XCTAssertTrue(calls[3].hasPrefix("approve --stem P1 --review-file "))
        XCTAssertTrue(calls[3].hasSuffix(" --json"))
        XCTAssertEqual(calls[4], "run --stem P1 --json")
        XCTAssertEqual(calls[5], "status --json")

        let reviewData = try Data(
            contentsOf: repo.appendingPathComponent("stub-review.json"))
        let review = try XCTUnwrap(
            try JSONSerialization.jsonObject(with: reviewData) as? [String: Any])
        XCTAssertEqual(review["expected_review_revision"] as? String, "r2")
        XCTAssertEqual(review["expression_audit"] as? [String], [
            "eyes open — all: pass",
            "expressions natural: pass",
            "no blinks in crops: pass",
        ])

        XCTAssertEqual(model.snapshot?.photos.first { $0.stem == "P1" }?.state,
                       "published")
        XCTAssertEqual(model.snapshot?.photos.first { $0.stem == "P1" }?
            .published.version, "v001")
    }

    private func makeFixtureRepo() throws -> URL {
        let repo = FileManager.default.temporaryDirectory
            .appendingPathComponent("printworks-smoke-\(UUID().uuidString)",
                                    isDirectory: true)
        for directory in [
            "Input", "Output", "archive", "staging", "run", "recipes",
            "sidecars", "previews", "config/lab-profiles", "config/styles",
            "config/rawtherapee-seed",
        ] {
            try FileManager.default.createDirectory(
                at: repo.appendingPathComponent(directory, isDirectory: true),
                withIntermediateDirectories: true)
        }

        for stem in ["P1", "P2"] {
            try "stem: \(stem)\nstate: review_required\n".write(
                to: repo.appendingPathComponent("recipes/\(stem).yaml"),
                atomically: true, encoding: .utf8)
            try Data([0xff, 0xd8, 0xff, 0xd9]).write(
                to: repo.appendingPathComponent("previews/\(stem)-natural.jpg"))
        }
        return repo
    }

    private func makeStubPython(at repo: URL) throws -> URL {
        let script = repo.appendingPathComponent("stub-python")
        try """
        #!/bin/sh
        set -eu
        printf '%s\\n' "$*" >> "$PWD/stub-calls.log"
        case "$1" in
          status)
            if [ -f "$PWD/run-seen" ]; then
              printf '%s\\n' '\(Self.finalStatusJSON)'
            elif [ -f "$PWD/adjust-seen" ]; then
              printf '%s\\n' '\(Self.adjustedStatusJSON)'
            else
              printf '%s\\n' '\(Self.initialStatusJSON)'
            fi
            ;;
          adjust)
            : > "$PWD/adjust-seen"
            printf '%s\\n' '\(Self.adjustJSON)'
            ;;
          preview)
            printf '%s\\n' '\(Self.previewJSON)'
            ;;
          approve)
            while [ "$#" -gt 0 ]; do
              if [ "$1" = "--review-file" ]; then
                shift
                cp "$1" "$PWD/stub-review.json"
                break
              fi
              shift
            done
            printf '%s\\n' '\(Self.approveJSON)'
            ;;
          run)
            : > "$PWD/run-seen"
            printf '%s\\n' '\(Self.runJSON)'
            ;;
          *)
            echo "unexpected command: $*" >&2
            exit 64
            ;;
        esac
        """.write(to: script, atomically: true, encoding: .utf8)
        try FileManager.default.setAttributes([.posixPermissions: 0o755],
                                              ofItemAtPath: script.path)
        return script
    }
}
