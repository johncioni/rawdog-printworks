# HANDOFF

## Goal
RAWdog Printworks: resumable RAW → print pipeline (Python) plus the macOS SwiftUI
app that drives it. Both plans, the fix round, and the README are MERGED. The
repo is **PUBLIC**, CI green. main = `f5391e8`, local == origin, tree clean.
Nothing is outstanding — the next session starts new work, not a continuation.

## Done (this session)
- **`CLAUDE.md` fully refreshed** (`20610cb`, `f5391e8`). It had three stale
  claims: "there is no README"; a Commands block listing only the Python gate;
  and an "Active work" section still saying *"next up is Plan 2"*. All fixed.
  Gates re-run live to get real numbers, not remembered ones: **pytest 296**
  (the old "295 tests" predated a skip becoming a pass), **swift test 100**.
- Recorded in Commands, because it has been re-proposed twice and dismissed
  twice: `-disable-sandbox` / `OTHER_SWIFT_FLAGS='$(inherited) -disable-sandbox'`
  is the **agent-seatbelt workaround, not a build requirement**. The Release
  gate passes without it. Do not bake it into `scripts/build-app.sh`.

## Earlier, still load-bearing
- **Pre-publication secrets audit — CLEAN.** Tree AND all 658 historical blobs
  across 259 commits; ~30 provider patterns plus generic `password=`/`api_key=`/
  `Authorization:`. Zero hits. Nothing was ever added-then-deleted.
- **Repo is PUBLIC; secret scanning + push protection ENABLED.** Verify:
  `gh api repos/johncioni/rawdog-printworks --jq '.security_and_analysis'`.
- **Actions billing resolved by the public flip** — standard runners incl.
  `macos-15` are free on public repos. No account action was ever needed.
- **README.md merged** (PR #7 → `3b95add`). Front door only; points at specs.

## Ruled out
- **Stripping the QA screenshots. DO NOT REOPEN THIS.** 26 of 27 PNGs under
  `docs/superpowers/sdd-archive/**/qa/` show a family portrait. The user holds
  the rights, was asked before the flip, and chose to publish as-is. **Already
  re-raised once by a session that skipped this file — read HANDOFF.md before
  auditing anything.** It is a decision, not an oversight.
- **History rewrite as sanitization.** GitHub retains `refs/pull/*` for merged
  PRs, so a force-push leaves old blobs fetchable by SHA; real removal means
  filter-repo into a fresh repo. Only relevant if the photo decision reverses.
- **CodeRabbit MD022 on HANDOFF.md**: contradicts this file's style and the
  padding breaks the 60-line cap. Its `.venv` + MD040 README findings were real.
- Older, still standing: `runMutating` cancellable (m12) incl. watchdog→SIGKILL;
  CR Minors/Trivials, m6 coalesce reset, PreviewImageCache cancellation.

## In flight
- **Nothing running.** No agent terminals, no background jobs, no worktrees, no
  open PRs, no extra branches.
- **A second session has pushed to main concurrently** during this work. Always
  `git fetch` and compare before assuming your tree is ahead.
- **Reading CI:** a run marked *cancelled* on an older SHA is the workflow's own
  `concurrency: cancel-in-progress` being superseded, NOT a failure. Check the
  newest: `gh run list --branch main --limit 3`.

## Next
1. **The lab is still unchosen** — verified, not remembered: `config/lab-profiles/`
   holds only `generic-v1.yaml`. Picking one means adding a profile YAML per the
   spec; the only open item that changes rendered OUTPUT rather than code quality.
2. New RW2s: drop in `Input/`, `scripts/process.sh ingest`, review in the app.
   Dusk frames need warming sidecars — `sidecars/P1036170_*.pp3` is the template.
3. Tooling limit: synthetic keyboard/mouse events do NOT reach the app, so the
   crop drag and arrow-key nudge rest on unit tests alone.

## Gates
`.venv/bin/python -m pytest tests/ -q` (296) · `swift test --package-path
app/PrintworksCore` (100) · `zsh scripts/build-app.sh`
