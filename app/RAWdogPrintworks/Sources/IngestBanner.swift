import PrintworksCore
import SwiftUI

struct IngestBanner: View {
    @Bindable var model: AppModel

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: "tray.and.arrow.down.fill")
                .foregroundStyle(Theme.accent)
            Text(message)
                .frame(maxWidth: .infinity, alignment: .leading)
            Button("Ingest now") {
                Task { await model.ingestPending() }
            }
            .buttonStyle(.borderedProminent)
            .tint(Theme.accent)
            .disabled(model.busyExternally || model.activeCommand != nil)
        }
        .padding(14)
        .frame(maxWidth: 680)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 10))
        .overlay {
            RoundedRectangle(cornerRadius: 10)
                .stroke(Theme.accent.opacity(0.7), lineWidth: 1)
        }
        .shadow(radius: 12, y: 5)
    }

    private var message: String {
        let count = model.pendingInputFiles.count
        return "\(count) new RAW \(count == 1 ? "file" : "files") — Ingest now?"
    }
}
