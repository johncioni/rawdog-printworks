import CoreGraphics
import Foundation

public enum CropNudgeDirection: Sendable {
    case up
    case down
    case left
    case right
}

public enum CropMath {
    public static func nudged(_ window: CropWindow, dx: Double, dy: Double)
    -> CropWindow {
        CropWindow(x: min(max(window.x + dx, 0), 1 - window.w),
                   y: min(max(window.y + dy, 0), 1 - window.h),
                   w: window.w, h: window.h, source: window.source)
    }

    public static func aspectFitRect(image: CGSize, container: CGSize) -> CGRect {
        let scale = min(container.width / image.width,
                        container.height / image.height)
        let size = CGSize(width: image.width * scale, height: image.height * scale)
        return CGRect(x: (container.width - size.width) / 2,
                      y: (container.height - size.height) / 2,
                      width: size.width, height: size.height)
    }

    public static func nudged(
        _ window: CropWindow, translation: CGSize, imageSize: CGSize
    ) -> CropWindow {
        guard imageSize.width > 0, imageSize.height > 0 else { return window }
        return nudged(
            window,
            dx: translation.width / imageSize.width,
            dy: translation.height / imageSize.height)
    }

    public static func nudged(
        _ window: CropWindow, direction: CropNudgeDirection,
        imageSize: CGSize, step: CGFloat = 1
    ) -> CropWindow {
        let translation = switch direction {
        case .up: CGSize(width: 0, height: -step)
        case .down: CGSize(width: 0, height: step)
        case .left: CGSize(width: -step, height: 0)
        case .right: CGSize(width: step, height: 0)
        }
        return nudged(window, translation: translation, imageSize: imageSize)
    }

    /// Returns the crop whose visible outline is nearest the pointer. Filled
    /// interiors are deliberately excluded so an overlapping crop cannot
    /// steal a drag from the outline the user aimed at.
    public static func cropTarget(
        at point: CGPoint, windows: [String: CropWindow], imageRect: CGRect,
        hitTolerance: CGFloat = 10
    ) -> String? {
        guard imageRect.width > 0, imageRect.height > 0,
              hitTolerance >= 0 else { return nil }
        var candidates: [(name: String, distance: CGFloat)] = []
        for name in windows.keys.sorted() {
            guard let window = windows[name] else { continue }
            let rect = CGRect(
                x: imageRect.minX + window.x * imageRect.width,
                y: imageRect.minY + window.y * imageRect.height,
                width: window.w * imageRect.width,
                height: window.h * imageRect.height)
            let distance = distanceToOutline(point, rect: rect)
            if distance <= hitTolerance {
                candidates.append((name, distance))
            }
        }
        return candidates.min {
            if $0.distance == $1.distance { return $0.name < $1.name }
            return $0.distance < $1.distance
        }?.name
    }

    private static func distanceToOutline(_ point: CGPoint, rect: CGRect)
    -> CGFloat {
        if rect.contains(point) {
            return min(
                point.x - rect.minX, rect.maxX - point.x,
                point.y - rect.minY, rect.maxY - point.y)
        }
        let nearestX = min(max(point.x, rect.minX), rect.maxX)
        let nearestY = min(max(point.y, rect.minY), rect.maxY)
        return hypot(point.x - nearestX, point.y - nearestY)
    }
}

public enum RepoPaths {
    public static func resolve(_ relative: String, repo: URL) -> URL {
        relative.hasPrefix("/") ? URL(fileURLWithPath: relative)
                                : repo.appendingPathComponent(relative)
    }
}
