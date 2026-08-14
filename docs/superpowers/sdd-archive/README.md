# SDD execution archives

Ledgers, task briefs and task reports from subagent-driven plan executions,
copied out of the gitignored `.superpowers/sdd/` working directories so the
record survives the worktree that produced it.

These are the *curated* record — what each task was asked to do, what the
implementer reported, and the controller's rulings — not raw session
transcripts. Read them when you need to know **why** something was built the
way it was, in cases where the commit messages and the plan's own
"Review-round decisions" section aren't specific enough.

## `2026-08-12-pipeline-json-interface/`

Plan 1, the pipeline's `--json` interface. 13 tasks, executed 2026-08-12/13 on
branch `worktree-json-interface`, merged as PR #3 (merge commit `356115c`,
16 task commits preserved). Contains `progress.md` (the ledger, including every
ruling) plus a brief and report per task.

Worth knowing from it: implementers were Codex Sol 5.6 at xhigh via
codex-companion (`--fresh` per task, controller commits because Codex's sandbox
mounts `.git` read-only), reviewers were Claude subagents, and Task 1 initially
BLOCKED because the Codex sandbox rejected all writes — the fallback rule after
two such failures is recorded in the ledger's first lines.

The corresponding raw session transcript (~38 MB) is **not** archived here. It
lives at `~/.claude/projects/-Users-john-photo-edits--claude-worktrees-json-interface/`
— note the stale path, a leftover of the repo move (see
`docs/repo-move-orphans.md`). It holds the full turn-by-turn history including
every subagent dispatch, but almost everything durable in it is already either
in this archive, in the plan document, or in git history.
