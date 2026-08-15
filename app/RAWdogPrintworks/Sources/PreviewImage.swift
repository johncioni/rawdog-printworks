import ImageIO
import SwiftUI
import PrintworksCore

private struct DownsampledPreview: @unchecked Sendable {
    let image: CGImage
}

private actor PreviewImageCache {
    static let shared = PreviewImageCache()
    private static let countLimit = 40
    private static let totalCostLimit = 256 * 1024 * 1024

    private struct Key: Hashable {
        let contentHash: String
        let maxPixelSize: Int
    }

    private struct Entry {
        let preview: DownsampledPreview
        let cost: Int
    }

    private var images: [Key: Entry] = [:]
    private var recency: [Key] = []
    private var totalCost = 0

    func image(
        contentHash: String,
        url: URL,
        maxPixelSize: Int
    ) -> DownsampledPreview? {
        guard !Task.isCancelled else { return nil }
        let key = Key(contentHash: contentHash,
                      maxPixelSize: maxPixelSize)
        if let entry = images[key] {
            recency.removeAll { $0 == key }
            recency.append(key)
            return entry.preview
        }

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
        let cost = image.bytesPerRow * image.height
        guard cost <= Self.totalCostLimit else { return preview }
        while images.count >= Self.countLimit
                || totalCost > Self.totalCostLimit - cost {
            guard let oldest = recency.first else { break }
            recency.removeFirst()
            if let evicted = images.removeValue(forKey: oldest) {
                totalCost -= evicted.cost
            }
        }
        images[key] = Entry(preview: preview, cost: cost)
        recency.append(key)
        totalCost += cost
        return preview
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
