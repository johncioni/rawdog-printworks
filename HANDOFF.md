# HANDOFF

## Goal
RAWdog Printworks: resumable RAW → print pipeline (Python) plus the macOS SwiftUI
app that drives it. Both plans, the fix round, and the README are MERGED. The
repo is **PUBLIC**, CI is green. main = `20610cb`. Nothing is outstanding — the
next session starts new work, not a continuation.

## Done (this session)
- **PR #7 (`docs: add README`) merged** as `3b95add`, after a CodeRabbit round
  (`be1eef7`). CI on main **passed in 1m27s**.
- **Fixed `CLAUDE.md:7`** (`20610cb`): it still said "There is no README". Now
  points at `README.md` for orientation while keeping the design spec canonical
  for behaviour, and names the app spec alongside it. Both paths verified.

## Carried forward (earlier sessions, still true)
- Pre-publication **secrets audit CLEAN** across the working tree and all 658
  historical blobs; secret scanning + push protection ENABLED. Verify:
  `gh api repos/johncioni/rawdog-printworks --jq '.security_and_analysis'`.
- **Actions billing resolved by the public flip** — standard runners incl.
  `macos-15` are free on public repos. No account action was ever needed.
- Plan 2 + the 4-batch fix round shipped; visual QA passed (F1 confirmed live on
  a published photo). Archives under `docs/superpowers/sdd-archive/`.

## Ruled out
- **Stripping the QA screenshots. DO NOT REOPEN THIS.** 26 of 27 PNGs under
  `docs/superpowers/sdd-archive/**/qa/` show a family portrait. The user holds
  the rights, was asked before the flip, and chose to publish as-is. **This was
  already re-raised once by a session that skipped reading this file — read
  HANDOFF.md before auditing anything.** It is a decision, not an oversight.
- **History rewrite as sanitization.** GitHub retains `refs/pull/*` for merged
  PRs, so a force-push leaves old blobs fetchable by SHA; real removal means
  filter-repo into a fresh repo. Only relevant if the photo decision reverses.
- Making `runMutating` cancellable (m12), incl. CodeRabbit's watchdog→SIGKILL.
- CR Minors/Trivials, m6 coalesce reset, PreviewImageCache cancellation
  propagation — deliberately filed, listed in the archived fix-round README.

## In flight
- **Nothing running.** No agent terminals, no background jobs, no worktrees, no
  open PRs, no extra branches. Tree clean.

## Next
1. Nothing is required.
2. **`CLAUDE.md` is still stale in two places** (flagged to the user, not yet
   authorised): the "Active work" section says *"Next up is Plan 2"* — it
   shipped — and "Commands" covers only the pipeline, omitting
   `zsh scripts/build-app.sh` and `swift test --package-path app/PrintworksCore`.
3. **The lab is still unchosen** — verified, not remembered: `config/lab-profiles/`
   holds only `generic-v1.yaml`, so everything published so far used the generic
   profile. Picking one means adding a profile YAML per the spec; it is the only
   open item that changes rendered OUTPUT rather than code quality.
4. New RW2s: drop in `Input/`, `scripts/process.sh ingest`, review in the app.
   Dusk frames need warming sidecars — `sidecars/P1036170_*.pp3` is the template.
5. Known tooling limit: synthetic keyboard/mouse events do NOT reach the app, so
   the crop drag and arrow-key nudge rest on unit tests alone. To see a
   keyboard-gated view, temporarily default it on, rebuild, then revert.

## Gates
`.venv/bin/python -m pytest tests/ -q` (296) · `swift test --package-path
app/PrintworksCore` (100) · `zsh scripts/build-app.sh`
