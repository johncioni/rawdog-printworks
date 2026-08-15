import ImageIO
import SwiftUI
import PrintworksCore

private struct DownsampledPreview: @unchecked Sendable {
    let image: CGImage
}

private actor PreviewImageCache {
    static let shared = PreviewImageCache()

    private struct Key: Hashable {
        let contentHash: String
        let maxPixelSize: Int
    }

    private var images: [Key: DownsampledPreview] = [:]

    func image(
        contentHash: String,
        url: URL,
        maxPixelSize: Int
    ) -> DownsampledPreview? {
        guard !Task.isCancelled else { return nil }
        let key = Key(contentHash: contentHash,
                      maxPixelSize: maxPixelSize)
        if let image = images[key] { return image }

        let sourceOptions = [kCGImageSourceShouldCache: false] as CFDictionary
        guard let source = CGImageSourceCreateWithURL(url as CFURL,
                                                       sourceOptions) else {
            return nil
        }
        let thumbnailOptions = [
            kCGImageSourceCreateThumbnailFromImageAlways: true,
            kCGImageSourceCreateThumbnailWithTransform: true,
            kCGImageSourceShouldCacheImmediately: true,
            kCGImageSourceThumbnailMaxPixelSize: maxPixelSize,
        ] as CFDictionary
        guard let image = CGImageSourceCreateThumbnailAtIndex(
            source, 0, thumbnailOptions
        ) else { return nil }

        let preview = DownsampledPreview(image: image)
        images[key] = preview
        return preview
    }

    func evict(contentHash: String) {
        images = images.filter { $0.key.contentHash != contentHash }
    }
}

private struct PreviewRequest: Hashable {
    let contentHash: String
    let url: URL
    let maxPixelSize: Int
}

/// Shared hash-keyed preview loader for grid cards, sidebar thumbnails, and
/// the review canvas. ImageIO work runs on the cache actor, never MainActor.
struct PreviewImage: View {
    let path: String?
    let contentHash: String?
    let repo: URL

    @Environment(\.displayScale) private var displayScale
    @State private var preview: DownsampledPreview?
    @State private var loadedHash: String?

    var body: some View {
        GeometryReader { geometry in
            let maxPointSize = max(geometry.size.width, geometry.size.height)
            let maxPixelSize = Int(ceil(maxPointSize * displayScale))
            content(request: request(maxPixelSize: maxPixelSize))
        }
    }

    @ViewBuilder
    private func content(request: PreviewRequest?) -> some View {
        Group {
            if let preview {
                Image(decorative: preview.image, scale: displayScale)
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
            if let loadedHash {
                await PreviewImageCache.shared.evict(contentHash: loadedHash)
            }
            loadedHash = nextHash
        }
        preview = nil
        guard let request else { return }

        let loaded = await PreviewImageCache.shared.image(
            contentHash: request.contentHash,
            url: request.url,
            maxPixelSize: request.maxPixelSize
        )
        guard !Task.isCancelled,
              loadedHash == request.contentHash else { return }
        preview = loaded
    }
}
