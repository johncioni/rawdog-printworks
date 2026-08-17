# HANDOFF

## Goal
RAWdog Printworks: resumable RAW → print pipeline (Python) plus the macOS SwiftUI
app that drives it. Both plans, the fix round and the README are MERGED; repo is
**PUBLIC**, CI green, tree clean, local == origin. No code work outstanding — the
open items are photo decisions and one doc fix, both under Next.

## Done
- **`P1036094` ingested and previewed** — it had sat in `Input/` referenced
  nowhere in the repo. Now archived w/ SHA-256, recipe written, 4 previews,
  state `preview_ready`. **Awaiting visual review + approve; nothing published.**
  A 3rd frame from the same shoot: 12 subjects, flat overcast midday (163 =
  golden hour / lifeguard stand, 170 = dusk / shoreline). Ingest warned
  `missing or empty LensModel` — harmless, but expect it again on this frame.
- **`CLAUDE.md` fully refreshed** (`20610cb`, `f5391e8`, `a55e75d`). Four stale
  claims: "there is no README"; a Commands block listing only the Python gate;
  "Active work" still saying *"next up is Plan 2"*; and "22 files, 3 styles" —
  real sets are **29 artifacts / 4 styles**. Counts re-run live, not remembered:
  **pytest 296** (old "295" predated a skip becoming a pass), **swift test 100**.
- Recorded in Commands, re-proposed and dismissed twice now: `-disable-sandbox` /
  `OTHER_SWIFT_FLAGS='$(inherited) -disable-sandbox'` is the **agent-seatbelt
  workaround, not a build requirement**. Do not bake it in.
- Earlier: **secrets audit CLEAN** (tree + 658 historical blobs, zero hits); repo
  flipped **PUBLIC** w/ scanning + push protection, which fixed Actions billing;
  **README.md merged** (PR #7 → `3b95add`).

## Ruled out
- **Stripping the QA screenshots. DO NOT REOPEN THIS.** 26 of 27 PNGs under
  `docs/superpowers/sdd-archive/**/qa/` show a family portrait. The user holds
  the rights, was asked before the flip, and chose to publish as-is. **Already
  re-raised once by a session that skipped this file — read HANDOFF.md before
  auditing anything.** It is a decision, not an oversight.
- **History rewrite as sanitization.** GitHub retains `refs/pull/*` for merged
  PRs, so a force-push leaves old blobs fetchable by SHA; real removal means
  filter-repo into a fresh repo. Only relevant if the photo decision reverses.
- **CodeRabbit MD022 on HANDOFF.md**: contradicts this file's style; the padding
  breaks the 60-line cap. Still standing: `runMutating` cancellable (m12) incl.
  watchdog→SIGKILL; CR Minors/Trivials, m6 reset, PreviewImageCache cancellation.

## In flight
- **Nothing running** — no agent terminals, background jobs, worktrees, open PRs
  or extra branches. Another session has pushed to main concurrently during this
  work, so `git fetch` and compare before assuming your tree is ahead.
- **Reading CI:** *cancelled* on an older SHA is `concurrency: cancel-in-progress`
  being superseded, NOT a failure. `gh run list --branch main --limit 3`.

## Next
1. **Review P1036094 in the app, then approve or reject.** Once approved,
   `scripts/process.sh run --stem P1036094` renders and publishes it.
2. **`README.md` has the same stale count — UNFIXED, user not yet asked.** L7 and
   the L59-66 matrix say 22 files / 3 styles; worse, L67 claims `vibrant` "ships
   for preview and comparison" when published sets contain `_vibrant.tif/.jpg/
   _5x7/_8x10` — it IS delivered. Public front door. The **spec is FINE**: its
   rev-8 note (L183) declares every "22"/"3 styles" in it reads 29/4.
3. **The lab is still unchosen** — `config/lab-profiles/` has only
   `generic-v1.yaml`. A real profile changes `[review]` fields (`ppi`,
   `color_space`, `safe_edge_percent`), breaking the approval fingerprint and
   sending verified photos BACKWARD to `review_required`. Do it deliberately.
4. Tooling limit: synthetic keyboard/mouse events do NOT reach the app, so the
   crop drag and arrow-key nudge rest on unit tests alone.
5. Gates: `.venv/bin/python -m pytest tests/ -q` (296) · `swift test
   --package-path app/PrintworksCore` (100) · `zsh scripts/build-app.sh`
