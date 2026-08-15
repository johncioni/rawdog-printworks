import SwiftUI
import PrintworksCore

struct SidebarView: View {
    @Bindable var model: AppModel
    @Binding var showingReview: Bool

    var body: some View {
        List {
            if showingReview, model.selectedStem != nil {
                reviewSidebar
            } else {
                browseSidebar
            }
        }
        .listStyle(.sidebar)
        .navigationSplitViewColumnWidth(min: 210, ideal: 250, max: 320)
    }

    @ViewBuilder
    private var browseSidebar: some View {
        Section("Deliveries") {
            Button {
                model.selectedDeliveryId = nil
            } label: {
                deliveryRow(
                    title: "All Deliveries",
                    photos: model.snapshot?.photos ?? [],
                    selected: model.selectedDeliveryId == nil
                )
            }
            .buttonStyle(.plain)

            let deliveries = model.deliveries()
            ForEach(deliveries.indices, id: \.self) { index in
                let delivery = deliveries[index]
                Button {
                    model.selectedDeliveryId = .some(delivery.id)
                } label: {
                    deliveryRow(
                        title: delivery.id ?? "Earlier",
                        photos: delivery.photos,
                        selected: isSelected(delivery.id)
                    )
                }
                .buttonStyle(.plain)
            }
        }

        Section("Pipeline") {
            pipelineRow(
                title: model.snapshot?.toolchain.ok == true
                    ? "Toolchain OK" : "Toolchain unavailable",
                systemImage: model.snapshot?.toolchain.ok == true
                    ? "checkmark.circle.fill" : "exclamationmark.triangle.fill",
                color: model.snapshot?.toolchain.ok == true
                    ? Theme.statusPublished : Theme.statusReview
            )
            pipelineRow(
                title: pipelineActivityTitle,
                systemImage: model.busyExternally ? "lock.fill" : "circle.fill",
                color: model.busyExternally ? Theme.statusReview
                    : Theme.statusIngested
            )
        }
    }

    @ViewBuilder
    private var reviewSidebar: some View {
        Section {
            Button {
                showingReview = false
            } label: {
                Label("Deliveries", systemImage: "chevron.left")
            }
            .buttonStyle(.plain)
        }

        Section("Photos") {
            ForEach(reviewPhotos, id: \.stem) { photo in
                Button {
                    model.selectedStem = photo.stem
                } label: {
                    photoRow(photo)
                }
                .buttonStyle(.plain)
            }
        }
    }

    private func deliveryRow(
        title: String,
        photos: [PhotoStatus],
        selected: Bool
    ) -> some View {
        HStack(spacing: 10) {
            Image(systemName: "shippingbox")
                .foregroundStyle(selected ? Theme.accent : .secondary)
                .frame(width: 16)

            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .lineLimit(1)
                Text("\(photos.count) photos · \(reviewCount(in: photos)) review")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }
            Spacer(minLength: 0)
        }
        .contentShape(Rectangle())
        .padding(.vertical, 3)
    }

    private func photoRow(_ photo: PhotoStatus) -> some View {
        let appearance = PhotoStateAppearance(state: photo.state)
        return HStack(spacing: 10) {
            PreviewImage(
                path: photo.previews["natural"] ?? nil,
                contentHash: photo.previewHashes["natural"] ?? nil,
                repo: model.repo
            )
            .frame(width: 42, height: 42)
            .clipShape(RoundedRectangle(cornerRadius: 6))

            VStack(alignment: .leading, spacing: 3) {
                Text(photo.stem)
                    .lineLimit(1)
                HStack(spacing: 5) {
                    Circle()
                        .fill(appearance.color)
                        .frame(width: 7, height: 7)
                    Text(appearance.label)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }
            Spacer(minLength: 0)
        }
        .contentShape(Rectangle())
        .padding(.vertical, 2)
    }

    private func pipelineRow(
        title: String,
        systemImage: String,
        color: Color
    ) -> some View {
        Label {
            Text(title)
                .font(.caption)
                .foregroundStyle(.secondary)
        } icon: {
            Image(systemName: systemImage)
                .foregroundStyle(color)
        }
    }

    private var reviewPhotos: [PhotoStatus] {
        guard let stem = model.selectedStem,
              let selectedPhoto = model.photo(stem) else { return [] }
        return (model.snapshot?.photos ?? []).filter {
            $0.deliveryId == selectedPhoto.deliveryId
        }
    }

    private var pipelineActivityTitle: String {
        if model.busyExternally { return "Busy in CLI" }
        if let command = model.activeCommand { return "Running \(command)" }
        return "Idle"
    }

    private func isSelected(_ deliveryID: String?) -> Bool {
        guard let selectedDeliveryID = model.selectedDeliveryId else {
            return false
        }
        return selectedDeliveryID == deliveryID
    }

    private func reviewCount(in photos: [PhotoStatus]) -> Int {
        photos.count {
            PhotoStateAppearance(state: $0.state).label == "Needs review"
        }
    }
}
