### Task 8: ReviewView + CompareView

**Files:**
- Create: `app/RAWdogPrintworks/Sources/ReviewView.swift`, `CompareView.swift`
- Modify: `MainWindow.swift` (replace the `ReviewScreen` stub)

**Interfaces:**
- Consumes: `AppModel.selectedStem/selectedStyle`, `PhotoStatus.previews/previewHashes/stalePreviews`.
- Produces: `ReviewScreen(model:)` — large canvas on `Theme.canvas` showing the selected style's preview (`NSImage(contentsOfFile:)`, `.id(previewHash)` so a content-hash change forces reload; never `AsyncImage`/URL cache); segmented style control bound to `model.selectedStyle`; keyboard: `⌘1`–`⌘4` (`.keyboardShortcut("1", modifiers: .command)` on hidden buttons) switch style, `space` toggles `CompareView`, `c` toggles the crop overlay (Task 9), `←`/`→` move `model.selectedStem` through the open delivery; per-style "preview out of date — re-render" chip when the style ∈ `stalePreviews` → `model.rerenderPreview(stem:style:)` (`preview --stem S --style Y --json` via `mutate`); "rendering preview…" shimmer overlay while that command is `activeCommand`.
- `CompareView(model:)` — 2×2 grid of the four styles' previews with labels; click a panel → sets `selectedStyle`, dismisses compare.

- [ ] **Step 1: Implement** both views; add `rerenderPreview` to `AppModel` **with unit tests first** in `AppModelTests`: (a) asserts args `["preview", "--stem", "P1", "--style", "filmic", "--json"]` and a refresh after; (b) asserts the result's `reviewRevisionBefore/After` pair flows through the SAME shared `rebase(stem:before:after:)` path as `applyAdjust` — a matching pair rebases the draft, a non-matching one marks it stale. Canvas image loading resolves via `RepoPaths.resolve` + content-hash `.id` keying, as in Task 7.
- [ ] **Step 2: Gate** — `swift test --package-path app/PrintworksCore` PASS + `xcodebuild … build` SUCCEEDED.
- [ ] **Step 3: Manual smoke + screenshot** — review P1036163: style switching updates the canvas; space shows 4-up compare.
- [ ] **Step 4: Commit**

```bash
git add app/
git commit -m "feat(app): review screen — canvas, style switching, compare mode, stale-preview chip"
```

---

