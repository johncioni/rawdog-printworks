# HANDOFF

## Goal
RAWdog Printworks: resumable RAW → print pipeline (Python) plus the macOS
SwiftUI app driving it. Both plans, the fix round and the README are MERGED;
repo **PUBLIC**, CI green, tree clean. Open items all listed under Next.

## Done
- **Lab-profile selection: spec written, awaiting your review** — `d2754b7`,
  `docs/superpowers/specs/2026-08-17-lab-profile-selection-design.md`. Read it
  rather than this summary; every decision and its reason is in there.
- **Step 0 landed** (`5679791`): driver.py and provenance.py each hardcoded
  `"generic-v1"`, feeding the approval fingerprint and the artifact dep hashes
  respectively — divergence would approve against one lab and invalidate
  against another, silently. **297 pytest / 100 swift; both photos still
  `verified`, so no fingerprint moved.**
- **`P1036094` ingested + previewed** — it had sat in `Input/` referenced
  nowhere in the repo. Archived w/ SHA-256, recipe + 4 sidecars committed,
  state `preview_ready`. **Nothing published; awaiting your review.** 3rd setup
  from that shoot: 12 subjects, flat overcast midday. Ingest warns `missing or
  empty LensModel` on it — harmless.
- **`CLAUDE.md` refreshed** (`20610cb`, `f5391e8`, `a55e75d`): it claimed no
  README, listed only the Python gate, said *"next up is Plan 2"*, and said
  "22 files / 3 styles" when real sets are **29 artifacts / 4 styles**.
- Dismissed twice, now written into Commands: `-disable-sandbox` is the
  **agent-seatbelt workaround, not a build requirement**. Do not bake it in.

## Ruled out
- **Stripping the QA screenshots. DO NOT REOPEN THIS.** 26 of 27 PNGs under
  `docs/superpowers/sdd-archive/**/qa/` show a family portrait; the user holds
  the rights, was asked before the flip, and chose to publish. **Already
  re-raised once by a session that skipped this file.** A decision, not an error.
- **History rewrite as sanitization.** GitHub keeps `refs/pull/*`; a force-push
  still leaves old blobs fetchable by SHA. Only if that decision reverses.
- **Per-delivery / per-photo lab selection**, and app-side profile editing —
  see the spec's §10. Standing: `runMutating` cancellable (m12) incl.
  watchdog→SIGKILL; CR Minors/Trivials, m6 reset, cache cancellation.

## In flight
- **Nothing running** — no agent terminals, jobs, worktrees, PRs or branches.
- **Reading CI:** *cancelled* on an older SHA is `cancel-in-progress` being
  superseded, NOT a failure — check `gh run list --branch main --limit 3`.
  Another session has pushed to main concurrently; `git fetch` before assuming.

## Next
1. **Lab selection: user is reviewing the spec.** On approval the next step is
   the **`writing-plans` skill — NOT implementation**; do not code from the spec
   directly. Research each profile from that lab's own published guide; ship
   none whose 9 lab-determined fields aren't all sourced.
2. **Review P1036094 in the app, then approve or reject.** Once approved,
   `scripts/process.sh run --stem P1036094` renders and publishes it.
3. **`README.md` has a stale count — UNFIXED, user not yet asked.** L7 + the
   L59-66 matrix say 22 files / 3 styles; L67 calls `vibrant` preview-only when
   published sets contain `_vibrant.tif/.jpg/_5x7/_8x10`. Public front door.
   The **spec is FINE**: its rev-8 note (L183) says every "22" reads 29/4.
4. Synthetic key/mouse events do NOT reach the app — crop drag and arrow-key
   nudge rest on unit tests alone.
5. Gates: `pytest tests/ -q` (297) · `swift test --package-path
   app/PrintworksCore` (100) · `zsh scripts/build-app.sh`
