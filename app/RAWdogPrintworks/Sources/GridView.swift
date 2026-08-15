import AppKit
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
                preview(photo)
                    .id(photo.previewHashes["natural"] ?? "")

                Label(appearance.label, systemImage: "circle.fill")
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(appearance.color)
                    .padding(.horizontal, 9)
                    .padding(.vertical, 6)
                    .background(.ultraThinMaterial,
                                in: RoundedRectangle(cornerRadius: 8))
                    .padding(10)

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

    @ViewBuilder
    private func preview(_ photo: PhotoStatus) -> some View {
        if let path = photo.previews["natural"] ?? nil,
           let image = NSImage(contentsOf: RepoPaths.resolve(path, repo: model.repo)) {
            Image(nsImage: image)
                .resizable()
                .scaledToFill()
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .clipped()
        } else {
            ZStack {
                Theme.canvas
                Image(systemName: "photo")
                    .font(.largeTitle)
                    .foregroundStyle(.secondary)
            }
        }
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
