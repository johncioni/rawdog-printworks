import Foundation
import SwiftUI
import PrintworksCore

struct InspectorView: View {
    @Bindable var model: AppModel

    @State private var cropResult: CropsResult?
    @State private var warmth = 5500.0
    @State private var exposure = 0.0
    @State private var warmthWasTouched = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 18) {
                header
                stylePicker
                adjustSection
                Divider()
                cropsSection
                Divider()
                auditSection
                if draft?.isStale == true {
                    staleDraftBanner
                }
                approveButton
            }
            .padding(18)
        }
        .frame(width: 260)
        .frame(maxHeight: .infinity, alignment: .top)
        .background(Theme.panel)
        .task(id: selectionKey) {
            guard let stem, let photo else {
                cropResult = nil
                return
            }
            if model.drafts[stem] == nil {
                model.startDraft(stem: stem)
            }
            configureControls(from: photo)
            cropResult = nil
            let result = await model.crops(stem: stem)
            guard model.selectedStem == stem,
                  model.photo(stem)?.reviewRevision == photo.reviewRevision
            else { return }
            cropResult = result
        }
    }

    private var header: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(stem ?? "Review")
                .font(.title3.weight(.semibold))
                .lineLimit(1)
            Text("Preview style")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
    }

    private var stylePicker: some View {
        Picker("Style", selection: $model.selectedStyle) {
            ForEach(styles, id: \.self) { style in
                Text(style.capitalized).tag(style)
            }
        }
        .pickerStyle(.segmented)
        .labelsHidden()
        .accessibilityLabel("Preview style")
    }

    private var adjustSection: some View {
        VStack(alignment: .leading, spacing: 10) {
            sectionTitle("Adjust")

            HStack {
                Text("Warmth")
                Spacer()
                Text(warmthDisplay)
                    .foregroundStyle(.secondary)
                    .monospacedDigit()
            }
            .font(.caption)
            Slider(value: warmthBinding, in: 3000...9000, step: 50)
                .tint(Theme.accent)
                .accessibilityLabel("Warmth")
                .accessibilityValue(warmthDisplay)
                .disabled(stem == nil || controlsDisabled)

            HStack {
                Text("Exposure")
                Spacer()
                Text(String(format: "%+.2f EV", exposure))
                    .foregroundStyle(.secondary)
                    .monospacedDigit()
            }
            .font(.caption)
            Slider(value: exposureBinding, in: -1...1, step: 0.05)
                .tint(Theme.accent)
                .accessibilityLabel("Exposure")
                .accessibilityValue(String(format: "%+.2f EV", exposure))
                .disabled(stem == nil || controlsDisabled)

            Button("Reset") {
                guard let stem else { return }
                Task {
                    await model.resetAdjust(
                        stem: stem, style: model.selectedStyle)
                    if let current = model.photo(stem) {
                        configureControls(from: current)
                    }
                }
            }
            .accessibilityLabel("Reset adjustments")
            .disabled(stem == nil || controlsDisabled)
        }
    }

    private var cropsSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            sectionTitle("Crops")
            ForEach(["8x10", "5x7"], id: \.self) { cropName in
                HStack(spacing: 6) {
                    Text(cropName == "8x10" ? "8 × 10" : "5 × 7")
                    Spacer()
                    Text(cropStatus(cropName))
                        .foregroundStyle(.secondary)
                    if draft?.cropNudges[cropName] != nil {
                        Text("nudged")
                            .font(.caption2.weight(.semibold))
                            .foregroundStyle(Theme.accent)
                    }
                }
                .font(.caption)
            }
        }
    }

    private var auditSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            sectionTitle("Expression audit")
            auditToggle("Eyes open", key: "eyes_open")
            auditToggle("Expressions natural", key: "expressions_natural")
            auditToggle("No blinks in crops", key: "no_blinks_in_crops")
            TextField("Note", text: noteBinding)
                .textFieldStyle(.roundedBorder)
                .accessibilityLabel("Expression audit note")
        }
    }

    private var staleDraftBanner: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label("This photo changed on disk — re-check before approving",
                  systemImage: "exclamationmark.triangle.fill")
                .font(.caption)
                .foregroundStyle(Theme.statusReview)
            Button("Re-review") {
                guard let stem else { return }
                model.reReview(stem: stem)
            }
            .accessibilityLabel("Re-review photo")
        }
        .padding(10)
        .background(Theme.windowBase,
                    in: RoundedRectangle(cornerRadius: 8))
    }

    private var approveButton: some View {
        Button("Approve") {
            guard let stem else { return }
            Task { await model.approve(stem: stem) }
        }
        .buttonStyle(.borderedProminent)
        .tint(Theme.accent)
        .frame(maxWidth: .infinity)
        .accessibilityLabel("Approve photo")
        .disabled(stem.map { !model.canApprove(stem: $0) } ?? true)
    }

    private func auditToggle(_ title: String, key: String) -> some View {
        Toggle(title, isOn: Binding(
            get: { draft?.checks[key] ?? false },
            set: { isChecked in
                guard let stem else { return }
                model.setDraftCheck(stem: stem, key: key,
                                    isChecked: isChecked)
            }
        ))
        .toggleStyle(.checkbox)
        .accessibilityLabel(title)
    }

    private var warmthBinding: Binding<Double> {
        Binding(
            get: { warmth },
            set: { value in
                warmth = value
                warmthWasTouched = true
                guard let stem else { return }
                model.setSlider(stem: stem, style: model.selectedStyle,
                                temperature: value, exposure: nil)
            }
        )
    }

    private var exposureBinding: Binding<Double> {
        Binding(
            get: { exposure },
            set: { value in
                exposure = value
                guard let stem else { return }
                model.setSlider(stem: stem, style: model.selectedStyle,
                                temperature: nil, exposure: value)
            }
        )
    }

    private var noteBinding: Binding<String> {
        Binding(
            get: { draft?.note ?? "" },
            set: { note in
                guard let stem else { return }
                model.setDraftNote(stem: stem, note: note)
            }
        )
    }

    private var stem: String? { model.selectedStem }

    private var photo: PhotoStatus? {
        guard let stem else { return nil }
        return model.photo(stem)
    }

    private var draft: ReviewDraft? {
        guard let stem else { return nil }
        return model.drafts[stem]
    }

    private var styles: [String] {
        let reported = model.snapshot?.styles ?? []
        return reported.isEmpty
            ? ["natural", "filmic", "bw", "vibrant"] : reported
    }

    private var selectedAdjustments: StyleAdjustments? {
        photo?.adjustments[model.selectedStyle]
    }

    private var warmthDisplay: String {
        if selectedAdjustments?.temperature.source == "camera",
           !warmthWasTouched {
            return "As shot"
        }
        return "\(Int(warmth.rounded())) K"
    }

    private var controlsDisabled: Bool {
        model.busyExternally || model.activeCommand != nil
    }

    private var selectionKey: String {
        guard let photo else { return "none|\(model.selectedStyle)" }
        return "\(photo.stem)|\(model.selectedStyle)|\(photo.reviewRevision)"
    }

    private func configureControls(from photo: PhotoStatus) {
        let controls = photo.adjustments[model.selectedStyle]
        warmth = controls?.temperature.value ?? 5500
        exposure = controls?.exposure.value ?? 0
        warmthWasTouched = false
    }

    private func cropStatus(_ cropName: String) -> String {
        if let source = draft?.cropNudges[cropName]?.source {
            return source
        }
        if draft?.cropNudges[cropName] != nil { return "draft" }
        if let source = cropResult?.windows[cropName]?.source {
            return source
        }
        if cropResult?.windows[cropName] != nil { return "available" }
        return "unavailable"
    }

    private func sectionTitle(_ title: String) -> some View {
        Text(title.uppercased())
            .font(.caption.weight(.semibold))
            .foregroundStyle(.secondary)
    }
}
