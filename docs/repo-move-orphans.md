# Orphans from the `~/photo-edits` → `~/Projects/rawdog-printworks` move

Audit run 2026-08-14. Tool state is keyed by **absolute repo path**, so moving a
checkout silently strands anything registered under the old one. Nothing errors —
the new path just starts empty — which is why these are worth listing.

## Fixed

| What | Where | Action taken |
|---|---|---|
| Project memories (4) | `~/.claude/projects/-Users-john-photo-edits/memory/` | Copied to the new project's memory dir; `MEMORY.md` index rebuilt. Originals left in place. This one had teeth: `model-usage-preferences` was among them, so five Plan 2 tasks ran Claude implementers when the standing directive was Codex. |
| Codex project trust | `~/.codex/config.toml` | Only `/Users/john/photo-edits` was `trust_level = "trusted"`. Added entries for `/Users/john/Projects/rawdog-printworks` and the Plan 2 Orca worktree. Backup at `config.toml.bak-premove-fix`. Without this the Codex switch would have hit trust prompts. |
| git worktree pointers | `.git/worktrees/json-interface/gitdir` and the worktree's `.git` file | Both rewritten to the new path (done earlier in the move). `git worktree repair` was a no-op because the worktree is locked. |
| `config/toolchain.lock` | repo | `python` path updated (informational entry — not part of the approval fingerprint, so approvals stood). |
| Docs | Plan 2 + macOS app spec | App-default repo paths updated. |

## Left alone deliberately

| What | Where | Why |
|---|---|---|
| Stale Codex project entry | `~/.codex/config.toml` → `[projects."/Users/john/photo-edits"]` | Harmless; removing it is cosmetic. Delete if you want the file tidy. |
| Stale Claude project entry | `~/.claude.json` → `projects["/Users/john/photo-edits"]` | Holds only telemetry and an `activeWorktreeSession` pointing at dead paths. The new path is registered separately and in use. |
| Old project dirs | `~/.claude/projects/-Users-john-photo-edits/` and `…--claude-worktrees-json-interface/` | The second still holds the **session transcript of the Plan 1 SDD run** (`6fa5d6a6-…jsonl`). That is the only record of how Plan 1 was executed apart from the worktree's ledger — do not delete without deciding you don't want it. |
| Codex plugin job state (100 jobs) | `~/.claude/plugins/data/codex-openai-codex/state/photo-edits-34ba0c1c4806c924/` | Historical job records keyed to the old path. New work creates a new keyed dir. |
| claude-hud caches, `~/.claude/history.jsonl` | various | Caches and shell history; regenerate or are append-only history. |

## Checked and clean

Shell rc files, `~/.zprofile`, launchd agents in `~/Library/LaunchAgents`,
Orca's registered repos and worktrees (all point at the new path), and
`~/.gemini/settings.json` — none reference the old path.

## Next time a repo moves

1. `ls ~/.claude/projects/` for the old sanitized path (`-Users-john-<old-path>`) and migrate its `memory/` dir first — that is the loss you won't notice.
2. `grep -n "<old-path>" ~/.codex/config.toml` and re-add `trust_level` for the new path.
3. `git worktree list` — if any worktree still shows the old path, rewrite both `.git/worktrees/<name>/gitdir` and the worktree's own `.git` file (`repair` won't touch a locked worktree).
4. Grep the repo itself, including gitignored state: `config/toolchain.lock`, provenance JSON, and any doc that hardcodes a path.
