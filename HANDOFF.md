# HANDOFF

## Goal
RAWdog Printworks: resumable RAW → print pipeline (Python) plus the macOS SwiftUI
app that drives it. Both plans and the fix round are MERGED. **The repo is now
PUBLIC** and has a README. main = `528b4b5`; branch `johncioni/readme` = PR #7.

## Done (this session)
- **Pre-publication secrets audit — CLEAN.** Scanned the working tree AND all 658
  historical blobs across 259 commits: ~30 provider token patterns (sk-ant, ghp_,
  AKIA, AIza, xox*, PEM keys, JWTs, webhooks) plus generic `password=`/`api_key=`/
  `Authorization:` forms. Zero hits. No `.env`/`.pem`/`.key`/`.netrc` ever
  committed, and **no file was ever added-then-deleted**, so history hides nothing
  the tree doesn't show. Commit emails are all GitHub `noreply`.
- **Repo flipped PRIVATE → PUBLIC**, verified via API. No history rewrite.
- **Secret scanning + push protection ENABLED.** Verify with
  `gh api repos/johncioni/rawdog-printworks --jq '.security_and_analysis'`.
- **README.md written** — front door only; points at the specs rather than
  duplicating them. Every link target and documented CLI subcommand verified.
- **PR #7 opened** (`docs: add README` + a HANDOFF refresh), docs only.
- **GITHUB ACTIONS BILLING IS RESOLVED** — it fixed itself. Standard runners incl.
  `macos-15` are free on public repos, so the flip unblocked it. The `tests` gate
  ran on PR #7 and **passed in 1m11s**, after five straight 4-second billing
  failures on main. No account action needed. Local gate: **296 passed**.

## Ruled out
- **Stripping the QA screenshots.** 26 of 27 PNGs under
  `docs/superpowers/sdd-archive/**/qa/` show a family portrait. Raised before the
  flip; **the user
  confirmed they hold the rights and chose to publish as-is.** Do not "clean this
  up" in a later session — it is a decision, not an oversight.
- **History rewrite as a sanitization route.** GitHub retains `refs/pull/*` for the
  merged PRs; a force-push does not move them, so old blobs stay fetchable by SHA.
  Real removal would mean filter-repo into a *fresh* repo. Only relevant if the
  photo decision is ever reversed.
- **Committing the README straight to main.** Repo convention allows it for docs,
  but a README's rendering *is* the deliverable — the badge, screenshot scale, and
  output-matrix table only show themselves on GitHub. Hence the PR.

## In flight
- **PR #7 is open and awaiting the user's merge** — the only thing outstanding.
  `pytest` check is green; **CodeRabbit review was still in progress** at session
  end. Check both: `gh pr checks 7`.
- No agent terminals, no background jobs, no worktrees. Tree is clean.

## Next
1. `gh pr view 7 --comments` — read CodeRabbit's pass on the README prose, then
   `gh pr merge 7` once the user has read the rendered page.
2. After merge: `git checkout main && git pull && git branch -d johncioni/readme`.
3. **The lab is still unchosen** — verified, not remembered: `config/lab-profiles/`
   holds only `generic-v1.yaml`, so everything published so far used the generic
   profile. Picking a lab means adding a profile YAML per the spec, and it is the
   only open item that changes rendered OUTPUT rather than code quality.
4. New RW2s: drop in `Input/`, `scripts/process.sh ingest`, review in the app.
   Dusk frames need warming sidecars — `sidecars/P1036170_*.pp3` is the template.

## Gates
`.venv/bin/python -m pytest tests/ -q` (296) · `swift test --package-path
app/PrintworksCore` (100) · `zsh scripts/build-app.sh`
