# HANDOFF

## Goal
RAWdog Printworks: resumable RAW → print pipeline (Python) plus the macOS SwiftUI
app that drives it. Both plans, the fix round, and the README are MERGED. The
repo is **PUBLIC**, CI green on HEAD. main = `374b92d`, local == origin. Nothing
is outstanding — the next session starts new work, not a continuation.

## Done (this session)
- **Pre-publication secrets audit — CLEAN.** Working tree AND all 658 historical
  blobs across 259 commits: ~30 provider patterns plus generic `password=`/
  `api_key=`/`Authorization:`. Zero hits. No `.env`/`.pem`/`.key` ever committed,
  and nothing was ever added-then-deleted, so history hides nothing the tree shows.
- **Repo flipped PRIVATE → PUBLIC**; **secret scanning + push protection ENABLED**.
  Verify: `gh api repos/johncioni/rawdog-printworks --jq '.security_and_analysis'`.
- **README.md written and merged** (PR #7 → `3b95add`) after a CodeRabbit round
  (`be1eef7`). Front door only; points at the specs rather than duplicating them.
- **Actions billing resolved by the flip** — standard runners incl. `macos-15` are
  free on public repos. Five 4s billing failures on main, then green. No account
  action was ever needed.
- **`CLAUDE.md:7` fixed** (`20610cb`): it still said "There is no README".

## Ruled out
- **Stripping the QA screenshots. DO NOT REOPEN THIS.** 26 of 27 PNGs under
  `docs/superpowers/sdd-archive/**/qa/` show a family portrait. The user holds the
  rights, was asked before the flip, and chose to publish as-is. **Already
  re-raised once by a session that skipped this file — read HANDOFF.md before
  auditing anything.** It is a decision, not an oversight.
- **History rewrite as sanitization.** GitHub retains `refs/pull/*` for merged PRs,
  so a force-push leaves old blobs fetchable by SHA; real removal means filter-repo
  into a fresh repo. Only relevant if the photo decision reverses.
- **CodeRabbit MD022 on HANDOFF.md**: contradicts this file's style and the padding
  breaks the 60-line cap. Its `.venv` + MD040 findings on README were real, fixed.
- Older, still standing: `runMutating` cancellable (m12) incl. watchdog→SIGKILL; CR
  Minors/Trivials, m6 coalesce reset, PreviewImageCache cancellation propagation.

## In flight
- **Nothing running.** No agent terminals, no background jobs, no worktrees, no
  open PRs, no extra branches. Tree clean.
- **CI read carefully:** run on `20610cb` shows **cancelled** — that is the
  workflow's own `concurrency: cancel-in-progress` being superseded by `374b92d`,
  NOT a failure. `374b92d` passed. Check: `gh run list --branch main --limit 3`.
- **A second session pushed to main concurrently** this session (`20610cb`,
  `374b92d`). Always `git fetch` and compare before assuming your tree is ahead.

## Next
1. **`CLAUDE.md` is still stale** (flagged, not yet authorised): "Active work" says
   *"Next up is Plan 2"* — it shipped — and "Commands" omits `scripts/build-app.sh`
   and `swift test --package-path app/PrintworksCore`.
2. **The lab is still unchosen** — verified, not remembered: `config/lab-profiles/`
   holds only `generic-v1.yaml`. Picking one means adding a profile YAML per the
   spec; the only open item that changes rendered OUTPUT rather than code quality.
3. New RW2s: drop in `Input/`, `scripts/process.sh ingest`, review in the app.
   Dusk frames need warming sidecars — `sidecars/P1036170_*.pp3` is the template.
4. Tooling limit: synthetic keyboard/mouse events do NOT reach the app, so the crop
   drag and arrow-key nudge rest on unit tests alone.

## Gates
`.venv/bin/python -m pytest tests/ -q` (296) · `swift test --package-path
app/PrintworksCore` (100) · `zsh scripts/build-app.sh`
