import AppKit
import SwiftUI
import PrintworksCore

struct MainWindow: View {
    @Bindable var model: AppModel
    @State private var showingReview = false
    @State private var showingReprocessAllConfirmation = false

    var body: some View {
        NavigationSplitView {
            SidebarView(model: model, showingReview: $showingReview)
                .background(.ultraThinMaterial)
        } detail: {
            ZStack(alignment: .top) {
                if model.selectedStem != nil && showingReview {
                    ReviewScreen(model: model)
                } else {
                    GridView(model: model, openReview: { stem in
                        model.selectedStem = stem
                        showingReview = true
                    })
                }

                VStack(spacing: 12) {
                    if let banner = model.banner {
                        ErrorBanner(model: model, info: banner)
                    }
                    if !model.pendingInputFiles.isEmpty {
                        IngestBanner(model: model)
                    }
                }
                .padding()
            }
            .background(Theme.windowBase)
            .overlay(alignment: .bottom) {
                if let status = model.longRunningCommand {
                    longRunningPanel(status)
                } else if model.busyExternally {
                    Label("Pipeline busy (CLI)", systemImage: "lock.fill")
                        .font(.callout.weight(.medium))
                        .padding(.horizontal, 14)
                        .padding(.vertical, 7)
                        .background(.regularMaterial, in: Capsule())
                        .overlay {
                            Capsule().stroke(Theme.hairline, lineWidth: 1)
                        }
                        .padding(.bottom, 16)
                }
            }
        }
        .preferredColorScheme(.dark)
        .toolbar { toolbarContent }
        .confirmationDialog(
            model.reprocessAllConfirmation.title,
            isPresented: $showingReprocessAllConfirmation,
            titleVisibility: .visible
        ) {
            Button("Reprocess All Photos", role: .destructive) {
                Task { await model.reprocessAll() }
            }
            Button("Cancel", role: .cancel) {}
                .keyboardShortcut(.defaultAction)
        } message: {
            Text(model.reprocessAllConfirmation.message)
        }
        .dropDestination(for: URL.self) { urls, _ in
            model.ingestDropped(paths: urls.map(\.path))
        }
    }

    private func longRunningPanel(
        _ status: LongRunningCommandStatus
    ) -> some View {
        VStack(alignment: .leading, spacing: 7) {
            Label(status.message, systemImage: "clock.badge.exclamationmark")
                .font(.callout.weight(.semibold))
            Text("The app is still waiting and will not stop the pipeline. "
                 + "If you judge it stuck, inspect or end the process in Activity Monitor.")
                .font(.caption)
                .foregroundStyle(.secondary)
            Button("Reveal Run Folder in Finder") {
                NSWorkspace.shared.activateFileViewerSelecting([status.revealURL])
            }
            .controlSize(.small)
        }
        .padding(12)
        .frame(maxWidth: 520, alignment: .leading)
        .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 10))
        .overlay {
            RoundedRectangle(cornerRadius: 10)
                .stroke(Theme.hairline, lineWidth: 1)
        }
        .padding(.bottom, 16)
    }

    @ToolbarContentBuilder
    private var toolbarContent: some ToolbarContent {
        ToolbarItem(placement: .principal) {
            HStack(spacing: 10) {
                Text(deliveryTitle)
                    .font(.headline)
                    .lineLimit(1)
                Text("\(needsReviewCount) needs review")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }

        ToolbarItem(placement: .status) {
            if !model.renderProgress.isEmpty {
                ProgressView()
                    .controlSize(.small)
                    .help("Rendering photos")
            }
        }

        ToolbarItemGroup(placement: .primaryAction) {
            Menu {
                Button("This Photo") {
                    guard let stem = model.selectedStem else { return }
                    Task { await model.reprocess(stem: stem) }
                }
                .disabled(model.selectedStem == nil)

                Button("All Photos") {
                    showingReprocessAllConfirmation = true
                }
            } label: {
                Label("Reprocess", systemImage: "arrow.clockwise")
            }
            .disabled(model.busyExternally || model.activeCommand != nil)

            Picker("View", selection: $showingReview) {
                Label("Grid", systemImage: "square.grid.2x2")
                    .tag(false)
                Label("Review", systemImage: "photo")
                    .tag(true)
            }
            .pickerStyle(.segmented)
            .labelsHidden()
            .frame(width: 130)
            .disabled(model.selectedStem == nil)
        }
    }

    private var toolbarPhotos: [PhotoStatus] {
        let photos = model.snapshot?.photos ?? []
        if showingReview,
           let stem = model.selectedStem,
           let photo = model.photo(stem) {
            return model.photos(inDeliveryOf: photo.deliveryId)
        }
        guard let selectedDeliveryID = model.selectedDeliveryId else {
            return photos
        }
        return model.photos(inDeliveryOf: selectedDeliveryID)
    }

    private var deliveryTitle: String {
        if showingReview,
           let stem = model.selectedStem,
           let photo = model.photo(stem) {
            return photo.deliveryId ?? "Earlier"
        }
        guard let selectedDeliveryID = model.selectedDeliveryId else {
            return "All Deliveries"
        }
        return selectedDeliveryID ?? "Earlier"
    }

    private var needsReviewCount: Int {
        PhotoStateAppearance.needsReviewCount(
            states: toolbarPhotos.map(\.state))
    }
}
