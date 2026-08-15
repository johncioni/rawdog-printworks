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

    func evict(contentHash: String) {
        let keys = images.keys.filter { $0.contentHash == contentHash }
        for key in keys {
            if let evicted = images.removeValue(forKey: key) {
                totalCost -= evicted.cost
            }
        }
        recency.removeAll { $0.contentHash == contentHash }
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
            let raw = Int(ceil(maxPointSize * displayScale))
            let maxPixelSize = (raw + 255) / 256 * 256
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
    }
}
