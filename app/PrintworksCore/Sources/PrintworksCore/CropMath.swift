import CoreGraphics
import Foundation

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
}

public enum RepoPaths {
    public static func resolve(_ relative: String, repo: URL) -> URL {
        relative.hasPrefix("/") ? URL(fileURLWithPath: relative)
                                : repo.appendingPathComponent(relative)
    }
}
