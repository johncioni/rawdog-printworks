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

## `2026-08-12-printworks-app/`

Plan 2, the macOS SwiftUI app. 11 tasks, on branch
`johncioni/plan2-printworks-app`. **Archived mid-plan (through Task 6) and
therefore stale from Task 7 onward — refresh it on completion.**

Worth knowing from it:

- `task-6-review.md` → `task-6-fix-round-1.md` → `task-6-rereview.md` is the
  most complete decision trail in either plan. The re-review re-derived its
  own 20-mutant matrix rather than inheriting the fix report's evidence, and
  it **corrected the controller**: "late, never lost" was upheld and reproduced
  at load ~300, but the stated bound (`maxCoalesceWait` 2s) was wrong — that
  bounds the scheduled deadline, not delivery. Commit `c4a10d1`'s message still
  carries the bad phrasing; this archive is where the correction lives.
- `task-6-fix-round-1.md` is a **controller reconstruction**, not an
  implementer's report — the Codex job died on a stream disconnect after its
  gate passed but before it reported. Claims are tagged `[claimed]` vs
  `[verified]`; treat `[claimed]` as unconfirmed.
- Carried into Task 7 rather than a fix round 2: P1 (the coalesce *window* is
  unpinned — `coalesce-10x` survives) and minors M1-M4.

The 8 `review-*.diff` files in the source directory are **not** archived: every
endpoint is a commit on the branch, so each is regenerable with `git diff A..B`.
