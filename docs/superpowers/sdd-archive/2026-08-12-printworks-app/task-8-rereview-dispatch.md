# Task 8 re-review — dispatch

Reviewer: Opus 5 xhigh. Scope: **`bf4cbd1..e512205`**.
Read `task-8-brief.md` (the spec), `task-8-dispatch.md` (what the implementer was
told, including Task 7's carry-forwards), and `task-8-report.md` (its claims).

## Controller verification already done

- `swift test --disable-sandbox` → exit 0, **66** tests (+2). `xcodebuild` → exit 0.
- **Shared-rebase mutation, re-run by me:** replacing the `rebase(...)` call in
  `rerenderPreview` with a parallel copy that handles only the matching branch
  turns `testRerenderPreviewUsesSharedRebaseForBothPairBranches` RED. The test
  genuinely discriminates the shared path from a copy.
- `rerenderPreview` was NOT re-added — it already existed from Task 5 (`532c311`),
  so the commit adds only the two required tests. I confirmed that provenance.
- **Smoke, partially passed** (`qa/task-8-review-smoke.png`,
  `qa/task-8-stale-chip-bw.png`): double-click opens the review screen; the
  Natural canvas renders the real preview; ⌘1/⌘2/⌘3 switch the style (radio
  values change) and the **canvas actually changes** (mean abs pixel diff 83.7
  between Natural and the Bw placeholder); the "Preview out of date — re-render"
  chip appears for a style with no rendered preview; the sidebar's review level
  shows 42 pt thumbnails with correct Published states.

## THE ONE THING THAT FAILED — please diagnose

**CompareView never opened.** Four attempts, none produced the 4-up grid:

1. `Space` with focus on the sidebar list — nothing.
2. `Space` after clicking the canvas — nothing; focus stayed on `3 list Sidebar`.
3. Click on the "Compare Styles" button by element index — nothing.
4. Click on it by converted window coordinates (769,172 at scale 1.4222) —
   nothing. The tree and screenshot are byte-comparable before and after.

**Why I do not think this is simply "focus was wrong":** ⌘1–⌘4 worked from that
exact same focus state, so synthesized key events do reach the app. And the
button click failing too points at the compare presentation itself rather than at
keyboard routing.

Decide which it is: a real defect in how `CompareView` is presented/toggled, or an
artifact of synthesized events that a human would not hit. If it is real, it is a
Major — `CompareView` is half of Task 8's deliverable and §5's 4-up compare is a
stated done-criterion. Read `CompareView.swift` and the `showingCompare` (or
equivalent) state path in `ReviewView`/`MainWindow` rather than trusting my
attempts; I could not rule out my own tooling.

## Also worth your attention

1. **i4 carry-forward** — the implementer was asked to reuse `PreviewImage` (one
   shared 256 MiB pool) and to report what a canvas-sized entry costs and whether
   one pool is still right. Check it did reuse rather than fork, and judge the
   numbers it gives.
2. **The canvas image path** — content-hash `.id`, `RepoPaths.resolve`, no
   `AsyncImage`, no URL/mtime caching. Task 7 lost a round to exactly this.
3. **Binding constraints**: no pipeline logic in Swift, no repo writes, argv-only,
   views add no model logic. And no path may reach `--force`/`approve` without
   explicit user action — the app points at irreplaceable photo data.
4. Anything Task 8 **broke** in Task 7's now-confirmed behaviour.

## Out of scope

Everything previously deferred (m6-m10, i11, i12, kqueue vs in-place edits,
`Output/photos/<stem>/`, the Task 5 refresh gate). Settings is Task 10; crop
overlay is Task 9.

## Output

Write `task-8-rereview.md`: severity-ordered findings with file:line and a
concrete failure scenario, plus a plain statement of whether Task 8 ships. Lead
with your verdict on the compare failure.
