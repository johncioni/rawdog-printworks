import SwiftUI
import PrintworksCore

private struct PreviewRequest: Hashable {
    let contentHash: String
    let url: URL
    let maxPixelSize: Int
}

/// Shared hash-keyed preview loader for grid cards, sidebar thumbnails, and
/// the review canvas. ImageIO work runs in detached utility tasks; the actor
/// coordinates only cache state, so unrelated decodes can overlap.
struct PreviewImage: View {
    let path: String?
    let contentHash: String?
    let repo: URL
    let contentMode: ContentMode
    let onImageSize: (@MainActor (CGSize) -> Void)?

    @Environment(\.displayScale) private var displayScale
    @State private var preview: DownsampledPreview?
    @State private var loadedHash: String?

    init(path: String?, contentHash: String?, repo: URL,
         contentMode: ContentMode = .fill,
         onImageSize: (@MainActor (CGSize) -> Void)? = nil) {
        self.path = path
        self.contentHash = contentHash
        self.repo = repo
        self.contentMode = contentMode
        self.onImageSize = onImageSize
    }

    var body: some View {
        GeometryReader { geometry in
            let maxPointSize = max(geometry.size.width, geometry.size.height)
            let raw = Int(ceil(maxPointSize * displayScale))
            let maxPixelSize = (raw + 255) / 256 * 256
            content(
                request: request(maxPixelSize: maxPixelSize),
                showCaption: min(geometry.size.width, geometry.size.height) >= 100
            )
        }
    }

    @ViewBuilder
    private func content(request: PreviewRequest?, showCaption: Bool) -> some View {
        Group {
            if let preview {
                Image(decorative: preview.image, scale: displayScale)
                    .resizable()
                    .aspectRatio(contentMode: contentMode)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .clipped()
            } else {
                ZStack {
                    Theme.canvas
                    VStack(spacing: 6) {
                        Image(systemName: path == nil
                              ? "photo.badge.plus"
                              : "exclamationmark.triangle")
                            .font(.largeTitle)
                        if showCaption {
                            Text(path == nil
                                 ? "Not rendered" : "Preview unavailable")
                                .font(.caption)
                        }
                    }
                    .foregroundStyle(.secondary)
                }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .task(id: request) { await load(request) }
    }

    private func request(maxPixelSize: Int) -> PreviewRequest? {
        guard maxPixelSize > 0,
              let path,
              let contentHash,
              !contentHash.isEmpty else { return nil }
        return PreviewRequest(
            contentHash: contentHash,
            url: RepoPaths.resolve(path, repo: repo),
            maxPixelSize: maxPixelSize
        )
    }

    @MainActor
    private func load(_ request: PreviewRequest?) async {
        let nextHash = request?.contentHash
        if loadedHash != nextHash {
            loadedHash = nextHash
            preview = nil
        }
        guard let request else { return }

        let loaded = await PreviewImageCache.shared.image(
            contentHash: request.contentHash,
            url: request.url,
            maxPixelSize: request.maxPixelSize
        )
        guard !Task.isCancelled,
              loadedHash == request.contentHash else { return }
        preview = loaded
        if let loaded {
            onImageSize?(CGSize(width: CGFloat(loaded.image.width),
                                height: CGFloat(loaded.image.height)))
        }
    }
}
