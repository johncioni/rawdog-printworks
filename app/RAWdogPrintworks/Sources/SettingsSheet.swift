import PrintworksCore
import SwiftUI

struct SettingsSheet: View {
    let onSave: (String, String) -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var repoPath: String
    @State private var pythonPath: String
    @State private var validation: Validation = .checking
    @State private var validatedCandidate: Candidate?

    init(
        initialRepoPath: String, initialPythonPath: String,
        onSave: @escaping (String, String) -> Void
    ) {
        self.onSave = onSave
        _repoPath = State(initialValue: initialRepoPath)
        _pythonPath = State(initialValue: initialPythonPath)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            Text("Pipeline Settings")
                .font(.title2.weight(.semibold))

            Grid(alignment: .leading, horizontalSpacing: 12, verticalSpacing: 14) {
                GridRow {
                    Text("Repository")
                    TextField("~/Projects/rawdog-printworks", text: $repoPath)
                        .textFieldStyle(.roundedBorder)
                }
                GridRow {
                    Text("Python")
                    TextField("<repo>/.venv/bin/python", text: $pythonPath)
                        .textFieldStyle(.roundedBorder)
                }
            }

            validationView

            HStack {
                Spacer()
                Button("Cancel") { dismiss() }
                    .keyboardShortcut(.cancelAction)
                Button("Save") {
                    onSave(repoPath, pythonPath)
                    dismiss()
                }
                .keyboardShortcut(.defaultAction)
                .disabled(validatedCandidate != candidate)
            }
        }
        .padding(22)
        .frame(width: 560)
        .task(id: candidate) {
            await validate(candidate)
        }
    }

    @ViewBuilder
    private var validationView: some View {
        switch validation {
        case .checking:
            Label("Checking pipeline…", systemImage: "clock")
                .foregroundStyle(.secondary)
        case .valid:
            Label("Pipeline status is valid.", systemImage: "checkmark.circle.fill")
                .foregroundStyle(.green)
        case .invalid(let message):
            Label(message, systemImage: "exclamationmark.triangle.fill")
                .foregroundStyle(Theme.statusReview)
                .textSelection(.enabled)
        case .transientError(let message):
            VStack(alignment: .leading, spacing: 4) {
                Label("Status is temporarily unavailable.",
                      systemImage: "exclamationmark.arrow.trianglehead.2.clockwise.rotate.90")
                    .foregroundStyle(Theme.statusReview)
                Text(message)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .textSelection(.enabled)
                Text("You can still save these paths and retry status from the app.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
    }

    @MainActor
    private func validate(_ candidate: Candidate) async {
        validation = .checking
        validatedCandidate = nil
        do {
            try await Task.sleep(for: .milliseconds(600))
        } catch {
            return
        }
        guard !Task.isCancelled else { return }

        // URL(fileURLWithPath:) does not expand ~. Expand both candidates
        // before either is used to configure the throwaway validation client.
        let repo = URL(
            fileURLWithPath: NSString(
                string: candidate.repoPath).expandingTildeInPath,
            isDirectory: true)
        let python = URL(
            fileURLWithPath: NSString(
                string: candidate.pythonPath).expandingTildeInPath)
        let client = PipelineClient(config: PipelineConfig(
            repo: repo, python: python))
        let result = await client.status()
        guard !Task.isCancelled, self.candidate == candidate else { return }

        switch SettingsStatusValidation.classify(result) {
        case .valid:
            validatedCandidate = candidate
            validation = .valid
        case .invalid(let message):
            validatedCandidate = nil
            validation = .invalid(message)
        case .transientError(let message):
            validatedCandidate = candidate
            validation = .transientError(message)
        }
    }

    private var candidate: Candidate {
        Candidate(repoPath: repoPath, pythonPath: pythonPath)
    }
}

private struct Candidate: Hashable {
    let repoPath: String
    let pythonPath: String
}

private enum Validation: Equatable {
    case checking
    case valid
    case invalid(String)
    case transientError(String)
}
