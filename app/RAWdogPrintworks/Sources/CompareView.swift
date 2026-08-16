import SwiftUI
import PrintworksCore

struct CompareView: View {
    @Bindable var model: AppModel
    let onSelect: () -> Void

    var body: some View {
        Grid(horizontalSpacing: 12, verticalSpacing: 12) {
            GridRow {
                panel(at: 0)
                panel(at: 1)
            }
            GridRow {
                panel(at: 2)
                panel(at: 3)
            }
        }
        .padding(20)
        .background(Theme.canvas)
    }

    @ViewBuilder
    private func panel(at index: Int) -> some View {
        if styles.indices.contains(index) {
            let style = styles[index]
            let previewPath = photo?.previews[style] ?? nil
            let previewHash = photo?.previewHashes[style] ?? nil
            Button {
                model.selectedStyle = style
                onSelect()
            } label: {
                ZStack(alignment: .topLeading) {
                    PreviewImage(
                        path: previewPath,
                        contentHash: previewHash,
                        repo: model.repo,
                        contentMode: .fit
                    )
                    .id(previewHash)

                    Text(style.capitalized)
                        .font(.caption.weight(.semibold))
                        .foregroundStyle(.white)
                        .padding(.horizontal, 9)
                        .padding(.vertical, 6)
                        .background(Theme.panel,
                                    in: RoundedRectangle(cornerRadius: 8))
                        .padding(10)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(Theme.canvas)
                .clipShape(RoundedRectangle(cornerRadius: 10))
                .overlay {
                    RoundedRectangle(cornerRadius: 10)
                        .stroke(model.selectedStyle == style
                                ? Theme.accent : Theme.hairline,
                                lineWidth: model.selectedStyle == style ? 2 : 1)
                }
                .contentShape(RoundedRectangle(cornerRadius: 10))
            }
            .buttonStyle(.plain)
            .accessibilityLabel(style.capitalized)
        } else {
            Theme.canvas
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        }
    }

    private var photo: PhotoStatus? {
        guard let stem = model.selectedStem else { return nil }
        return model.photo(stem)
    }

    private var styles: [String] {
        let reported = model.snapshot?.styles ?? []
        let available = reported.isEmpty
            ? ["natural", "filmic", "bw", "vibrant"] : reported
        return Array(available.prefix(4))
    }
}
