# HANDOFF

## Goal
RAWdog Printworks: resumable RAW → print pipeline (Python) plus the macOS
SwiftUI app driving it. Both plans, the fix round and the README are MERGED;
repo **PUBLIC**, CI green, tree clean. Open items are all listed under Next.

## Done
- **`P1036094` ingested and previewed** — it had sat in `Input/` referenced
  nowhere in the repo. Archived w/ SHA-256, recipe + 4 sidecars committed, 4
  previews, state `preview_ready`. **Nothing published; awaiting your review.**
  A 3rd setup from that shoot: 12 subjects, flat overcast midday (163 = golden
  hour / lifeguard stand, 170 = dusk / shore). Ingest warns `missing or empty
  LensModel` on this frame — harmless.
- **`CLAUDE.md` fully refreshed** (`20610cb`, `f5391e8`, `a55e75d`). Four stale
  claims: "there is no README"; a Commands block listing only the Python gate;
  "Active work" still saying *"next up is Plan 2"*; and "22 files, 3 styles" —
  real sets are **29 artifacts / 4 styles**. Counts re-run live, not recalled:
  **pytest 296** (old "295" predated a skip becoming a pass), **swift 100**.
- Re-proposed and dismissed twice, so it is now written into Commands:
  `-disable-sandbox` / `OTHER_SWIFT_FLAGS='$(inherited) -disable-sandbox'` is
  the **agent-seatbelt workaround, not a build requirement**. Do not bake in.
- Earlier: **secrets audit CLEAN** (tree + 658 blobs); repo flipped **PUBLIC**
  w/ scanning + push protection; **README.md merged** (PR #7 → `3b95add`).

## Ruled out
- **Stripping the QA screenshots. DO NOT REOPEN THIS.** 26 of 27 PNGs under
  `docs/superpowers/sdd-archive/**/qa/` show a family portrait; the user holds
  the rights, was asked before the flip, and chose to publish. **Already
  re-raised once by a session that skipped this file.** A decision, not an error.
- **History rewrite as sanitization.** GitHub keeps `refs/pull/*`, so a
  force-push leaves old blobs fetchable by SHA. Only if that decision reverses.
- **CodeRabbit MD022 here**: contradicts this file's style; padding breaks the
  line cap. Standing: `runMutating` cancellable (m12) incl. watchdog→SIGKILL;
  CR Minors/Trivials, m6 reset, PreviewImageCache cancellation.

## In flight
- **Nothing running** — no agent terminals, jobs, worktrees, PRs or branches.
  Another session has pushed to main concurrently, so `git fetch` and compare
  before assuming your tree is ahead.
- **Reading CI:** *cancelled* on an older SHA is `cancel-in-progress` being
  superseded, NOT a failure. `gh run list --branch main --limit 3`.

## Next
1. **Review P1036094 in the app, then approve or reject.** Once approved,
   `scripts/process.sh run --stem P1036094` renders and publishes it.
2. **`README.md` carries the same stale count — UNFIXED, user not yet asked.**
   L7 + the L59-66 matrix say 22 files / 3 styles; worse, L67 says `vibrant`
   "ships for preview and comparison" when published sets contain
   `_vibrant.tif/.jpg/_5x7/_8x10` — it IS delivered. Public front door. The
   **spec is FINE**: its rev-8 note (L183) says every "22"/"3 styles" reads 29/4.
3. **Lab still unchosen** — `config/lab-profiles/` has only `generic-v1.yaml`.
   A real profile changes `[review]` fields (`ppi`, `color_space`,
   `safe_edge_percent`), breaking approval fingerprints and sending verified
   photos BACKWARD to `review_required`.
4. Synthetic key/mouse events do NOT reach the app — the crop drag and
   arrow-key nudge rest on unit tests alone.
5. Gates: `pytest tests/ -q` (296) · `swift test --package-path
   app/PrintworksCore` (100) · `zsh scripts/build-app.sh`
