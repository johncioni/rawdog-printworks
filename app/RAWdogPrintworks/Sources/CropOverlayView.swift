import SwiftUI
import PrintworksCore

struct CropOverlayView: View {
    let windows: [String: CropWindow]
    let imageSize: CGSize
    let onNudge: (String, CropWindow) -> Void

    var body: some View {
        GeometryReader { geometry in
            let imageRect = CropMath.aspectFitRect(
                image: imageSize, container: geometry.size)

            ZStack {
                ForEach(["8x10", "5x7"], id: \.self) { cropName in
                    if let window = windows[cropName] {
                        CropWindowOutline(
                            cropName: cropName,
                            window: window,
                            imageRect: imageRect,
                            onNudge: onNudge
                        )
                    }
                }
            }
        }
        .allowsHitTesting(true)
    }
}

private struct CropWindowOutline: View {
    let cropName: String
    let window: CropWindow
    let imageRect: CGRect
    let onNudge: (String, CropWindow) -> Void

    @State private var translation: CGSize = .zero

    var body: some View {
        let drawnWindow = translatedWindow
        Rectangle()
            .stroke(Theme.accent, style: strokeStyle)
            .frame(width: window.w * imageRect.width,
                   height: window.h * imageRect.height)
            .contentShape(Rectangle())
            .position(
                x: imageRect.minX
                    + (drawnWindow.x + drawnWindow.w / 2) * imageRect.width,
                y: imageRect.minY
                    + (drawnWindow.y + drawnWindow.h / 2) * imageRect.height
            )
            .gesture(
                DragGesture()
                    .onChanged { translation = $0.translation }
                    .onEnded { value in
                        guard imageRect.width > 0, imageRect.height > 0 else {
                            translation = .zero
                            return
                        }
                        let nudged = CropMath.nudged(
                            window,
                            dx: value.translation.width / imageRect.width,
                            dy: value.translation.height / imageRect.height
                        )
                        translation = .zero
                        onNudge(cropName, nudged)
                    }
            )
            .accessibilityLabel("\(displayName) crop window")
            .accessibilityHint("Drag to reposition the crop")
    }

    private var translatedWindow: CropWindow {
        guard imageRect.width > 0, imageRect.height > 0 else { return window }
        return CropMath.nudged(
            window,
            dx: translation.width / imageRect.width,
            dy: translation.height / imageRect.height
        )
    }

    private var strokeStyle: StrokeStyle {
        cropName == "5x7"
            ? StrokeStyle(lineWidth: 2, dash: [8, 6])
            : StrokeStyle(lineWidth: 2)
    }

    private var displayName: String {
        cropName == "8x10" ? "8 by 10" : "5 by 7"
    }
}
