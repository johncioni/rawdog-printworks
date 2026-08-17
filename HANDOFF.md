# HANDOFF

## Goal
RAWdog Printworks: resumable RAW → print pipeline (Python) plus the macOS
SwiftUI app driving it. Both plans, the fix round and the README are MERGED;
repo **PUBLIC**, CI green, tree clean. Open items all listed under Next.

## Done
- **Lab-profile selection: spec written + reviewed** — `d2754b7`, `8a51de6`,
  `docs/superpowers/specs/2026-08-17-lab-profile-selection-design.md`. Read it
  rather than this summary. Review checked claims against code, not prose: it
  opened §10 (blocking) and folded in 3 amendments (dry-run must flag crops
  that fail `validate_crop` at the new PPI; memo invalidation; a broken pointer
  must not disable the tools that repair it).
- **Step 0 landed** (`5679791`): driver.py and provenance.py each hardcoded
  `"generic-v1"`, feeding the approval fingerprint and the artifact dep hashes
  respectively — divergence would approve against one lab and invalidate
  against another, silently. **297 pytest / 100 swift; both photos still
  `verified`, so no fingerprint moved.**
- **`P1036094` ingested + previewed** — it had sat in `Input/` referenced
  nowhere in the repo. Archived, recipe + 4 sidecars committed, state
  `preview_ready`. **Nothing published; awaiting your review.**
- **`CLAUDE.md` refreshed** (`20610cb`, `f5391e8`, `a55e75d`): claimed no README,
  listed only the Python gate, said *"next up is Plan 2"*, and said "22 files /
  3 styles" when real sets are **29 artifacts / 4 styles**.
- Dismissed twice, now in Commands: `-disable-sandbox` is the agent-seatbelt
  workaround, **not a build requirement**. Do not bake it into build-app.sh.

## Ruled out
- **Stripping the QA screenshots. DO NOT REOPEN THIS.** 26 of 27 PNGs under
  `docs/superpowers/sdd-archive/**/qa/` show a family portrait; the user holds
  the rights, was asked before the flip, chose to publish. **Re-raised once by a
  session that skipped this file.** A decision, not an oversight.
- **History rewrite as sanitization.** GitHub keeps `refs/pull/*`; force-pushing
  still leaves old blobs fetchable by SHA. Only if that decision reverses.
- Spec **§11** out-of-scope: per-delivery/per-photo labs, in-app profile edit.
  Standing: m12 cancellable + watchdog→SIGKILL; CR Minors, m6, cache cancel.

## In flight
- **Nothing running** — no agent terminals, jobs, worktrees, PRs or branches.
- **Reading CI:** *cancelled* on an older SHA is `cancel-in-progress` being
  superseded, NOT a failure — check `gh run list --branch main --limit 3`.
  Another session has pushed to main concurrently; `git fetch` before assuming.

## Next
1. **Lab selection BLOCKED on §10: published-version retention.** Publish keeps
   ONE version and `recover()` re-reaps, so switching labs destroys the record
   of what you sent the previous lab — unfixable by hand. Spec lists 3 options
   + a recommendation (b). On answer → **`writing-plans`, NOT implementation.**
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
