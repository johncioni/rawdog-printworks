import SwiftUI
import PrintworksCore

struct CropOverlayView: View {
    let windows: [String: CropWindow]
    let imageSize: CGSize
    let onNudge: (String, CropWindow) -> Void

    @State private var selectedCropName = "8x10"
    @State private var drag: CropDrag?
    @FocusState private var isFocused: Bool

    var body: some View {
        GeometryReader { geometry in
            let imageRect = CropMath.aspectFitRect(
                image: imageSize, container: geometry.size)

            ZStack {
                ForEach(["8x10", "5x7"], id: \.self) { cropName in
                    if let window = displayedWindow(
                        cropName: cropName, imageRect: imageRect
                    ) {
                        CropWindowOutline(
                            cropName: cropName,
                            window: window,
                            imageRect: imageRect,
                            isSelected: cropName == selectedCropName
                        )
                    }
                }
            }
            .contentShape(Rectangle())
            .gesture(dragGesture(imageRect: imageRect))
            .focusable()
            .focused($isFocused)
            .onMoveCommand { direction in
                keyboardNudge(direction, imageRect: imageRect)
            }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel("\(displayName(selectedCropName)) crop window")
            .accessibilityHint(
                "Drag the crop outline or use arrow keys to reposition it")
        }
    }

    private func dragGesture(imageRect: CGRect) -> some Gesture {
        DragGesture(minimumDistance: 0)
            .onChanged { value in
                if drag == nil {
                    guard let cropName = CropMath.cropTarget(
                        at: value.startLocation, windows: windows,
                        imageRect: imageRect),
                          let window = windows[cropName]
                    else { return }
                    selectedCropName = cropName
                    isFocused = true
                    drag = CropDrag(
                        cropName: cropName, window: window,
                        translation: value.translation)
                } else {
                    drag?.translation = value.translation
                }
            }
            .onEnded { value in
                guard let drag else { return }
                let nudged = CropMath.nudged(
                    drag.window, translation: value.translation,
                    imageSize: imageRect.size)
                self.drag = nil
                onNudge(drag.cropName, nudged)
            }
    }

    private func displayedWindow(
        cropName: String, imageRect: CGRect
    ) -> CropWindow? {
        guard let window = windows[cropName] else { return nil }
        guard let drag, drag.cropName == cropName else { return window }
        return CropMath.nudged(
            drag.window, translation: drag.translation,
            imageSize: imageRect.size)
    }

    private func keyboardNudge(
        _ direction: MoveCommandDirection, imageRect: CGRect
    ) {
        let cropName = windows[selectedCropName] != nil
            ? selectedCropName : windows.keys.sorted().first
        guard let cropName, let window = windows[cropName],
              let direction = cropNudgeDirection(direction)
        else { return }
        selectedCropName = cropName
        onNudge(
            cropName,
            CropMath.nudged(
                window, direction: direction, imageSize: imageRect.size))
    }

    private func cropNudgeDirection(
        _ direction: MoveCommandDirection
    ) -> CropNudgeDirection? {
        switch direction {
        case .up: .up
        case .down: .down
        case .left: .left
        case .right: .right
        @unknown default: nil
        }
    }

    private func displayName(_ cropName: String) -> String {
        cropName == "8x10" ? "8 by 10" : "5 by 7"
    }
}

private struct CropDrag {
    let cropName: String
    let window: CropWindow
    var translation: CGSize
}

private struct CropWindowOutline: View {
    let cropName: String
    let window: CropWindow
    let imageRect: CGRect
    let isSelected: Bool

    var body: some View {
        Rectangle()
            .stroke(Theme.accent, style: strokeStyle)
            .frame(width: window.w * imageRect.width,
                   height: window.h * imageRect.height)
            .position(
                x: imageRect.minX
                    + (window.x + window.w / 2) * imageRect.width,
                y: imageRect.minY
                    + (window.y + window.h / 2) * imageRect.height
            )
            .allowsHitTesting(false)
    }

    private var strokeStyle: StrokeStyle {
        cropName == "5x7"
            ? StrokeStyle(lineWidth: isSelected ? 3 : 2, dash: [8, 6])
            : StrokeStyle(lineWidth: isSelected ? 3 : 2)
    }
}
