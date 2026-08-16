import SwiftUI
import PrintworksCore

struct ErrorBanner: View {
    @Environment(\.openSettings) private var openSettings
    @Bindable var model: AppModel
    let info: PipelineErrorInfo
    @State private var showingDetails = false

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .top, spacing: 10) {
                Image(systemName: "exclamationmark.triangle.fill")
                    .foregroundStyle(Theme.statusReview)

                Text(info.message)
                    .frame(maxWidth: .infinity, alignment: .leading)

                if let action = model.bannerAction {
                    Button(action.title) {
                        perform(action)
                    }
                    .buttonStyle(.borderedProminent)
                    .tint(Theme.accent)
                    .disabled(action == .reReview && model.selectedStem == nil)
                }

                Button("Dismiss", systemImage: "xmark") {
                    model.dismissBanner()
                }
                .labelStyle(.iconOnly)
                .buttonStyle(.plain)
            }

            DisclosureGroup("Show Details", isExpanded: $showingDetails) {
                ScrollView {
                    Text(model.bannerDetails ?? "No additional details.")
                        .font(.caption.monospaced())
                        .textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.top, 6)
                }
                .frame(maxHeight: 140)
            }
            .font(.caption)
        }
        .padding(14)
        .frame(maxWidth: 680)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 10))
        .overlay {
            RoundedRectangle(cornerRadius: 10)
                .stroke(Theme.statusReview.opacity(0.7), lineWidth: 1)
        }
        .shadow(radius: 12, y: 5)
    }

    private func perform(_ action: BannerAction) {
        switch action {
        case .retry:
            Task { await model.retryBannerAction() }
        case .openSettings:
            openSettings()
        case .reReview:
            guard let stem = model.selectedStem else { return }
            model.reReview(stem: stem)
            model.dismissBanner()
        }
    }
}

private extension BannerAction {
    var title: String {
        switch self {
        case .retry: "Retry"
        case .openSettings: "Open Settings"
        case .reReview: "Re-review"
        }
    }
}
