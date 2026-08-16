import CoreGraphics
import Foundation
import ImageIO

public struct DownsampledPreview: @unchecked Sendable {
    public let image: CGImage

    init(image: CGImage) {
        self.image = image
    }
}

public actor PreviewImageCache {
    public static let shared = PreviewImageCache()

    private static let countLimit = 40
    private static let totalCostLimit = 256 * 1024 * 1024

    private struct Key: Hashable, Sendable {
        let contentHash: String
        let maxPixelSize: Int
    }

    private struct Entry {
        let preview: DownsampledPreview
        let cost: Int
    }

    typealias Decoder = @Sendable (URL, Int) -> DownsampledPreview?

    private var images: [Key: Entry] = [:]
    private var recency: [Key] = []
    private var totalCost = 0
    private var inFlight: [Key: Task<DownsampledPreview?, Never>] = [:]
    private let decoder: Decoder

    public init() {
        self.decoder = Self.decode
    }

    /// Test seam for deterministically controlling decode duration.
    init(decoder: @escaping Decoder) {
        self.decoder = decoder
    }

    public func image(
        contentHash: String,
        url: URL,
        maxPixelSize: Int
    ) async -> DownsampledPreview? {
        guard !Task.isCancelled else { return nil }
        let key = Key(contentHash: contentHash,
                      maxPixelSize: maxPixelSize)
        if let entry = images[key] {
            touch(key)
            return entry.preview
        }

        let task: Task<DownsampledPreview?, Never>
        if let existing = inFlight[key] {
            task = existing
        } else {
            let decoder = decoder
            task = Task.detached(priority: .utility) {
                decoder(url, maxPixelSize)
            }
            inFlight[key] = task
        }

        let decoded = await task.value
        inFlight.removeValue(forKey: key)
        guard !Task.isCancelled, let decoded else { return nil }

        // Another waiter for the same key may have populated the cache while
        // this actor was suspended. Preserve one coherent entry and recency.
        if let entry = images[key] {
            touch(key)
            return entry.preview
        }
        insert(decoded, for: key)
        return decoded
    }

    private func touch(_ key: Key) {
        recency.removeAll { $0 == key }
        recency.append(key)
    }

    private func insert(_ preview: DownsampledPreview, for key: Key) {
        let cost = preview.image.bytesPerRow * preview.image.height
        guard cost <= Self.totalCostLimit else { return }
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
    }

    private nonisolated static func decode(
        url: URL, maxPixelSize: Int
    ) -> DownsampledPreview? {
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
        return DownsampledPreview(image: image)
    }
}
