import SwiftUI
import PrintworksCore

struct ReviewScreen: View {
    @Bindable var model: AppModel
    @State private var showingCompare = false
    @State private var showingCrops = false
    @State private var cropResult: CropsResult?
    @State private var previewImageSize: CGSize?

    var body: some View {
        HStack(spacing: 0) {
            ZStack {
                Theme.canvas
                if showingCompare {
                    CompareView(model: model) {
                        showingCompare = false
                    }
                } else if let photo = selectedPhoto {
                    reviewCanvas(photo)
                } else {
                    ContentUnavailableView(
                        "Select a photo to review.",
                        systemImage: "photo"
                    )
                }
            }
            .overlay { keyboardShortcuts }

            Rectangle()
                .fill(Theme.hairline)
                .frame(width: 1)

            inspectorColumn
        }
        .background(Theme.canvas)
        .task(id: cropLoadKey) {
            guard showingCrops, let photo = selectedPhoto else {
                cropResult = nil
                return
            }
            cropResult = nil
            let result = await model.crops(stem: photo.stem)
            guard model.selectedStem == photo.stem,
                  model.photo(photo.stem)?.reviewRevision == photo.reviewRevision
            else { return }
            cropResult = result
        }
        .onChange(of: selectedPreviewIdentity) { _, _ in
            previewImageSize = nil
        }
    }

    private func reviewCanvas(_ photo: PhotoStatus) -> some View {
        let photoStyle = model.selectedStyle
        let previewPath = photo.previews[photoStyle] ?? nil
        let previewHash = photo.previewHashes[photoStyle] ?? nil
        return ZStack {
            ZStack {
                PreviewImage(
                    path: previewPath,
                    contentHash: previewHash,
                    repo: model.repo,
                    contentMode: .fit,
                    onImageSize: { size in
                        guard model.selectedStem == photo.stem,
                              model.selectedStyle == photoStyle,
                              (model.photo(photo.stem)?
                                .previewHashes[photoStyle] ?? nil) == previewHash
                        else { return }
                        previewImageSize = size
                    }
                )
                .id(previewHash)

                if showingCrops, !cropWindows.isEmpty,
                   let previewImageSize {
                    CropOverlayView(
                        windows: cropWindows,
                        imageSize: previewImageSize,
                        onNudge: { cropName, window in
                            model.setCropNudge(
                                stem: photo.stem,
                                cropName: cropName,
                                window: window)
                        }
                    )
                }
            }
            .padding(20)

            if photo.stalePreviews.contains(model.selectedStyle) {
                stalePreviewChip(photo)
                    .frame(maxWidth: .infinity, maxHeight: .infinity,
                           alignment: .topLeading)
                    .padding(20)
            }

            if let command = model.activeCommand,
               ["preview", "adjust"].contains(command),
               model.activeStem == photo.stem {
                RenderingPreviewOverlay()
            }

            if showingCrops, let basisLabel {
                Text(basisLabel)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.white)
                    .padding(.horizontal, 10)
                    .padding(.vertical, 7)
                    .background(Theme.panel,
                                in: RoundedRectangle(cornerRadius: 8))
                    .overlay {
                        RoundedRectangle(cornerRadius: 8)
                            .stroke(Theme.hairline, lineWidth: 1)
                    }
                    .frame(maxWidth: .infinity, maxHeight: .infinity,
                           alignment: .bottomLeading)
                    .padding(20)
                    .accessibilityLabel("Crop basis: \(basisLabel)")
            }
        }
    }

    private func stalePreviewChip(_ photo: PhotoStatus) -> some View {
        Button {
            Task {
                await model.rerenderPreview(
                    stem: photo.stem, style: model.selectedStyle)
            }
        } label: {
            Label("Preview out of date — re-render",
                  systemImage: "arrow.clockwise")
                .font(.caption.weight(.semibold))
                .foregroundStyle(.white)
                .padding(.horizontal, 10)
                .padding(.vertical, 7)
                .background(Theme.panel,
                            in: RoundedRectangle(cornerRadius: 8))
                .overlay {
                    RoundedRectangle(cornerRadius: 8)
                        .stroke(Theme.hairline, lineWidth: 1)
                }
        }
        .buttonStyle(.plain)
        .accessibilityLabel("Preview out of date — re-render")
        .disabled(model.busyExternally || model.activeCommand != nil)
    }

    private var inspectorColumn: some View {
        VStack(spacing: 0) {
            Button {
                showingCompare.toggle()
            } label: {
                Label(showingCompare ? "Close Compare" : "Compare Styles",
                      systemImage: showingCompare
                        ? "rectangle" : "square.grid.2x2")
                    .frame(maxWidth: .infinity)
            }
            .keyboardShortcut(.space, modifiers: [])
            .accessibilityLabel(showingCompare
                                ? "Close Compare" : "Compare Styles")
            .padding(18)

            Divider()

            InspectorView(model: model)
        }
        .frame(width: 260)
        .frame(maxHeight: .infinity, alignment: .top)
        .background(Theme.panel)
    }

    private var keyboardShortcuts: some View {
        ZStack {
            ForEach(Array(styles.prefix(4).enumerated()), id: \.offset) {
                index, style in
                Button("Select \(style)") {
                    model.selectedStyle = style
                }
                .keyboardShortcut(
                    KeyEquivalent(Character(String(index + 1))),
                    modifiers: .command
                )
            }

            Button("Previous Photo") { moveSelection(by: -1) }
                .keyboardShortcut(.leftArrow, modifiers: [])
                .disabled(adjacentStem(offset: -1) == nil)

            Button("Next Photo") { moveSelection(by: 1) }
                .keyboardShortcut(.rightArrow, modifiers: [])
                .disabled(adjacentStem(offset: 1) == nil)

            Button("Toggle Crop Overlay") { showingCrops.toggle() }
                .keyboardShortcut("c", modifiers: [])

            if showingCompare {
                Button("Close Compare") { showingCompare = false }
                    .keyboardShortcut(.escape, modifiers: [])
            }
        }
        .frame(width: 0, height: 0)
        .opacity(0)
        .accessibilityHidden(true)
    }

    private var selectedPhoto: PhotoStatus? {
        guard let stem = model.selectedStem else { return nil }
        return model.photo(stem)
    }

    private var styles: [String] {
        let reported = model.snapshot?.styles ?? []
        return reported.isEmpty
            ? ["natural", "filmic", "bw", "vibrant"] : reported
    }

    private var reviewPhotos: [PhotoStatus] {
        guard let selectedPhoto else { return [] }
        return model.photos(inDeliveryOf: selectedPhoto.deliveryId)
    }

    private var cropWindows: [String: CropWindow] {
        guard let photo = selectedPhoto else { return [:] }
        var windows = cropResult?.stem == photo.stem
            ? cropResult?.windows ?? [:] : photo.crops
        if let nudges = model.drafts[photo.stem]?.cropNudges {
            windows.merge(nudges) { _, nudge in nudge }
        }
        return windows
    }

    private var basisLabel: String? {
        guard cropResult?.stem == selectedPhoto?.stem else { return nil }
        switch cropResult?.basis {
        case "center": return "centered fallback"
        case "detector_error": return "detection failed — centered"
        case nil, "faces", "persisted": return nil
        case let basis?: return basis.replacingOccurrences(of: "_", with: " ")
        }
    }

    private var cropLoadKey: String {
        guard let photo = selectedPhoto else { return "none|\(showingCrops)" }
        return "\(photo.stem)|\(photo.reviewRevision)|\(showingCrops)"
    }

    private var selectedPreviewIdentity: String? {
        guard let photo = selectedPhoto else { return nil }
        let hash = photo.previewHashes[model.selectedStyle] ?? nil
        return "\(photo.stem)|\(model.selectedStyle)|\(hash ?? "missing")"
    }

    private func adjacentStem(offset: Int) -> String? {
        guard let stem = model.selectedStem,
              let index = reviewPhotos.firstIndex(where: { $0.stem == stem })
        else { return nil }
        let nextIndex = index + offset
        guard reviewPhotos.indices.contains(nextIndex) else { return nil }
        return reviewPhotos[nextIndex].stem
    }

    private func moveSelection(by offset: Int) {
        guard let stem = adjacentStem(offset: offset) else { return }
        model.selectedStem = stem
    }
}

private struct RenderingPreviewOverlay: View {
    var body: some View {
        TimelineView(.animation(minimumInterval: 1.0 / 30.0)) { context in
            GeometryReader { geometry in
                let duration = 1.4
                let elapsed = context.date.timeIntervalSinceReferenceDate
                    .truncatingRemainder(dividingBy: duration)
                let phase = elapsed / duration
                let bandWidth = max(geometry.size.width * 0.32, 120)

                ZStack {
                    Color.black.opacity(0.34)

                    LinearGradient(
                        colors: [.clear, .white.opacity(0.16), .clear],
                        startPoint: .leading,
                        endPoint: .trailing
                    )
                    .frame(width: bandWidth)
                    .offset(x: -bandWidth
                            + phase * (geometry.size.width + 2 * bandWidth))

                    Label("Rendering preview…", systemImage: "sparkles")
                        .font(.callout.weight(.semibold))
                        .foregroundStyle(.white)
                        .padding(.horizontal, 14)
                        .padding(.vertical, 9)
                        .background(Theme.panel,
                                    in: RoundedRectangle(cornerRadius: 8))
                }
            }
        }
        .allowsHitTesting(false)
        .accessibilityLabel("Rendering preview")
    }
}
