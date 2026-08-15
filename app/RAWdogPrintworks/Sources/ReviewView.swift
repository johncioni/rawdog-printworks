import SwiftUI
import PrintworksCore

struct ReviewScreen: View {
    @Bindable var model: AppModel
    @State private var showingCompare = false

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

            inspector
        }
        .background(Theme.canvas)
    }

    private func reviewCanvas(_ photo: PhotoStatus) -> some View {
        let previewPath = photo.previews[model.selectedStyle] ?? nil
        let previewHash = photo.previewHashes[model.selectedStyle] ?? nil
        return ZStack {
            PreviewImage(
                path: previewPath,
                contentHash: previewHash,
                repo: model.repo,
                contentMode: .fit
            )
            .id(previewHash)
            .padding(20)

            if photo.stalePreviews.contains(model.selectedStyle) {
                stalePreviewChip(photo)
                    .frame(maxWidth: .infinity, maxHeight: .infinity,
                           alignment: .topLeading)
                    .padding(20)
            }

            if model.activeCommand == "preview",
               model.activeStem == photo.stem {
                RenderingPreviewOverlay()
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
        .disabled(model.busyExternally || model.activeCommand != nil)
    }

    private var inspector: some View {
        VStack(alignment: .leading, spacing: 18) {
            VStack(alignment: .leading, spacing: 4) {
                Text(model.selectedStem ?? "Review")
                    .font(.title3.weight(.semibold))
                    .lineLimit(1)
                Text("Preview style")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Picker("Style", selection: $model.selectedStyle) {
                ForEach(styles, id: \.self) { style in
                    Text(style.capitalized).tag(style)
                }
            }
            .pickerStyle(.segmented)
            .labelsHidden()

            Button {
                showingCompare.toggle()
            } label: {
                Label(showingCompare ? "Close Compare" : "Compare Styles",
                      systemImage: showingCompare
                        ? "rectangle" : "square.grid.2x2")
                    .frame(maxWidth: .infinity)
            }
            .keyboardShortcut(.space, modifiers: [])

            Divider()

            VStack(alignment: .leading, spacing: 6) {
                Text("⌘1–⌘4  Switch style")
                Text("Space  Compare")
                Text("← / →  Previous / next photo")
            }
            .font(.caption)
            .foregroundStyle(.secondary)

            Spacer()
        }
        .padding(18)
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
        return (model.snapshot?.photos ?? []).filter {
            $0.deliveryId == selectedPhoto.deliveryId
        }
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
