import SwiftUI
import PrintworksCore

struct PhotoStateAppearance {
    let color: Color
    let label: String

    init(state: String) {
        switch state {
        case "verified":
            color = Theme.statusPublished
            label = "Published"
        case "preview_ready", "review_required":
            color = Theme.statusReview
            label = "Needs review"
        case "approved", "rendered":
            color = Theme.accent
            label = "Rendering"
        default:
            color = Theme.statusIngested
            label = "Ingested"
        }
    }
}

struct GridView: View {
    @Bindable var model: AppModel
    let openReview: (String) -> Void

    private let columns = [GridItem(.adaptive(minimum: 260), spacing: 16)]

    var body: some View {
        if visiblePhotos.isEmpty {
            ContentUnavailableView(
                "Drop RAW files to start a delivery.",
                systemImage: "photo.badge.plus"
            )
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else {
            ScrollView {
                LazyVGrid(columns: columns, spacing: 16) {
                    ForEach(visiblePhotos, id: \.stem) { photo in
                        photoCard(photo)
                            .onTapGesture(count: 2) {
                                openReview(photo.stem)
                            }
                    }
                }
                .padding(20)
            }
        }
    }

    private func photoCard(_ photo: PhotoStatus) -> some View {
        let appearance = PhotoStateAppearance(state: photo.state)
        return VStack(alignment: .leading, spacing: 10) {
            ZStack(alignment: .topLeading) {
                PreviewImage(
                    path: photo.previews["natural"] ?? nil,
                    contentHash: photo.previewHashes["natural"] ?? nil,
                    repo: model.repo
                )

                Label(appearance.label, systemImage: "circle.fill")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(appearance.color)
                    .padding(.horizontal, 9)
                    .padding(.vertical, 6)
                    .background(Theme.panel.opacity(0.85),
                                in: RoundedRectangle(cornerRadius: 8))
                    .padding(10)

                if model.lastFailures[photo.stem] != nil {
                    HStack(spacing: 8) {
                        Label("Render failed",
                              systemImage: "exclamationmark.triangle.fill")
                        Button("Retry") {
                            Task { await model.retryRender(stem: photo.stem) }
                        }
                        .buttonStyle(.borderless)
                        .disabled(model.busyExternally
                                  || model.activeCommand != nil)
                    }
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.white)
                    .padding(.horizontal, 9)
                    .padding(.vertical, 6)
                    .background(Color.red,
                                in: RoundedRectangle(cornerRadius: 8))
                    .frame(maxWidth: .infinity, maxHeight: .infinity,
                           alignment: .topTrailing)
                    .padding(10)
                }

                if let progress = model.renderProgress[photo.stem] {
                    VStack {
                        Spacer()
                        ProgressView(value: progressFraction(progress))
                            .tint(Theme.accent)
                            .padding(12)
                            .background(.ultraThinMaterial)
                    }
                }
            }
            .frame(height: 190)
            .clipShape(RoundedRectangle(cornerRadius: 10))

            Text(photo.stem)
                .font(.headline)
                .lineLimit(1)
        }
        .padding(10)
        .background(Theme.panel, in: RoundedRectangle(cornerRadius: 10))
        .overlay {
            RoundedRectangle(cornerRadius: 10)
                .stroke(Theme.hairline, lineWidth: 1)
        }
        .contentShape(RoundedRectangle(cornerRadius: 10))
    }

    private var visiblePhotos: [PhotoStatus] {
        let photos = model.snapshot?.photos ?? []
        guard let selectedDeliveryID = model.selectedDeliveryId else {
            return photos
        }
        return photos.filter { $0.deliveryId == selectedDeliveryID }
    }

    private func progressFraction(_ event: ProgressEvent) -> Double {
        guard let index = event.index, let total = event.total, total > 0 else {
            return 0
        }
        return min(max(Double(index) / Double(total), 0), 1)
    }
}
