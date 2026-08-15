### Task 7: Shell UI — MainWindow, Sidebar, Grid, drop target

**Files:**
- Create: `app/RAWdogPrintworks/Sources/MainWindow.swift`, `SidebarView.swift`, `GridView.swift`, `ErrorBanner.swift`
- Modify: `PrintworksApp.swift` (wire AppModel/watcher/settings), `Sources/PrintworksCore/AppModel.swift` (only if a computed helper is missing — no behavior changes)

**Interfaces:**
- Consumes: `AppModel` (Task 5), `RepoWatcher` (Task 6), `Theme` (Task 1).
- Produces: `MainWindow(model:)` — `NavigationSplitView`; sidebar lists deliveries (Browse) or the open delivery's photos (Review level) with 42 pt thumbnails + state dots; detail pane switches `GridView` ↔ `ReviewView` (Task 8 stub: `Text` placeholder until Task 8 replaces it); toolbar (delivery name, needs-review count, compact `ProgressView` when `renderProgress` non-empty, Reprocess menu → `model.reprocess(stem:)`/`reprocessAll()` which issue `run --stem S --force --json`/`run --force --json`; Grid/Review toggle); `.dropDestination(for: URL.self)` on the whole window → `model.ingest(paths:)`; empty state "Drop RAW files to start a delivery."; persistent busy pill (`Capsule` with "Pipeline busy (CLI)") when `model.busyExternally`; `ErrorBanner(model:)` overlay rendering `model.banner` with message + Show Details disclosure + per-code action button (Retry/Open Settings/Re-review per spec §7).

Key view code (complete files in the implementing commit; structure fixed here):

```swift
// MainWindow.swift (skeleton — fill bodies, keep names)
struct MainWindow: View {
    @Bindable var model: AppModel
    @State private var showingReview = false

    var body: some View {
        NavigationSplitView {
            SidebarView(model: model, showingReview: $showingReview)
                .background(.ultraThinMaterial)
        } detail: {
            ZStack(alignment: .top) {
                if model.selectedStem != nil && showingReview {
                    ReviewScreen(model: model)          // Task 8 replaces stub
                } else {
                    GridView(model: model, openReview: { stem in
                        model.selectedStem = stem; showingReview = true
                    })
                }
                if let banner = model.banner { ErrorBanner(model: model, info: banner) }
            }
            .background(Theme.windowBase)
        }
        .preferredColorScheme(.dark)
        .dropDestination(for: URL.self) { urls, _ in
            Task { await model.ingest(paths: urls.map(\.path)) }
            return true
        }
    }
}
```

Status-dot mapping (single helper used by sidebar + grid badges): `verified`→`Theme.statusPublished`/"Published", `preview_ready`/`review_required`→`Theme.statusReview`/"Needs review", `approved`/`rendered`→accent/"Rendering", else `Theme.statusIngested`/"Ingested". Grid cards: `LazyVGrid(columns: [GridItem(.adaptive(minimum: 260))])`; every image load resolves the contract's repo-relative path via `RepoPaths.resolve(path, repo: model.repo)` then `NSImage(contentsOf:)`, inside an `.id(photo.previewHashes["natural"] ?? "")`-keyed view (content-hash cache key — never URL/mtime caching); badge top-left, `ProgressView(value:)` overlay when `model.renderProgress[stem]` present, `.onTapGesture(count: 2)` → openReview. Sidebar delivery rows drive `model.selectedDeliveryId`; the toolbar Reprocess menu calls `model.reprocess(stem:)`/`reprocessAll()` (both exist from Task 5 — views add no model logic).

- [ ] **Step 1: Implement the four files** per the skeleton (no unit tests — logic already covered in core; the gate is the build).
- [ ] **Step 2: Build** — `xcodegen generate` (if project.yml changed) + `xcodebuild … build` → BUILD SUCCEEDED. Also `swift test --package-path app/PrintworksCore` still green.
- [ ] **Step 3: Manual smoke** — `open` the built app against the real repo (Settings default `~/Projects/rawdog-printworks`): grid shows P1036163/P1036170 as Published, sidebar shows "Earlier" group (legacy recipes have no delivery_id). Screenshot for the Task 11 QA set.
- [ ] **Step 4: Commit**

```bash
git add app/
git commit -m "feat(app): main window shell — sidebar, grid, drop target, busy pill, error banner"
```

---

