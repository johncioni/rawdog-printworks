# Whole-branch review — dispatch

Reviewer: Opus 5 xhigh. Scope: **`main..HEAD`** on `johncioni/plan2-printworks-app`
— 25 commits, Plan 2 in full. This is the last gate before the merge decision.

Every task already had its own review and, where needed, fix rounds. **Do not
re-review the tasks individually.** Your job is the two things a per-task review
structurally could not do:

1. **Judge the deferred pile as a whole** (below), now that the app exists.
2. **Look across seams** — defects that live between tasks, not inside one.

## Ground truth

- All 11 tasks complete. `swift test` **85 tests** exit 0; `xcodebuild` exit 0;
  `zsh scripts/build-app.sh` exit 0 producing a verified-signed bundle.
- The controller verified every task by exit code plus a mutation per new test,
  and ran a visual QA pass (`task-11-visual-qa-note.md`, 11 verified-distinct
  screenshots) that drove the full loop on a scratch repo: slider → `adjust` →
  verified→review_required → re-renders → audit → Approve → **v002 published,
  29 artifacts, v001 pruned**, with `git status` showing only pipeline-owned
  files touched.
- Task-level reviews live in `task-*-rereview.md`; read them for context rather
  than re-deriving their findings.

## The deferred pile — decide each: fix now, file for later, or drop

Carried deliberately, each with a reason recorded at the time:

**From Task 6** (`task-6-review.md`, `task-6-rereview.md`)
- M1 in-place non-atomic edits are invisible to kqueue (all real pipeline writers
  use temp+`os.replace`; exposure is hand-edits under `config/**`)
- M2 a *re*-publish is caught only incidentally via `rebuild_views()`
- N1 `start()` no-ops while a `stop()` is in flight; a wedged `stop()` makes it
  permanent · N2/N3 `changes` contract documentation · N4 `FakeClient` residual races

**From Task 7** (`task-7-rereview.md`, `…-fix-round-1/2-rereview.md`)
- m6 `firstPendingChangeAt` survives a consumer-less gap → next change emits with
  an already-expired deadline
- m7 the drop target is silent in three no-op cases
- m8 toolbar shows an indeterminate spinner where §5.2 asks for a compact bar
- m9 counts computed by string-comparing a **display label**
- m10 the delivery-filter rule existed in three copies (Task 9 collapsed four →
  one; confirm nothing regressed)
- i5 the M1 fix promoted m6 from near-unreachable to routinely reachable
- i11 sidebar renders warm brown, not §5.1's black primary

**From Task 8** (`task-8-rereview.md`) — N3 compare cells are portrait so
landscape previews use ~45% of them (I confirmed this visually); N5 Escape does
not close compare

**From Task 9** (`task-9-rereview.md`) — n13 the 8×10-only hit region is a ~5%
sliver with real geometry; n14/n15/n16 (check whether Task 10 closed them)

**From Task 10** (`task-10-rereview.md`) — n18 `pendingInputFiles` matches fewer
spellings than the pipeline; n19 Settings' Cancel does not revert; n20 Save is not
gated on an idle model; n21 notifications have no body and `lastIngestFailures`
renders nowhere

**From Task 11** (`task-11-rereview.md`) — I1 the ingest→run chain narrowing is a
deliberate behaviour change (confirm it is the one we want)

**Standing decision — do not reopen:** m12. `runMutating` is intentionally
uncancellable; the user decided this explicitly rather than accept SIGTERMing
RawTherapee mid-write into `staging/`. It is documented in code and pinned by a
test. If you think it is wrong, say so once, briefly, and move on.

## Cross-seam questions only this review can answer

1. **Does the app honour the pipeline's state machine everywhere?** Approval
   fingerprints, backward transitions, `expected_review_revision`, and the
   `current` symlink/version pruning. One wrong assumption in a view could
   publish or approve something the user did not visually approve — the single
   worst outcome for this app.
2. **`--force` reachability, whole-branch.** Task 7 found "Retry" escalating to a
   whole-repo `run --force`. Sweep every path again now that Tasks 8-11 added
   controls: can any UI affordance reach `--force`, `approve`, or a destructive
   command without explicit user intent?
3. **Contract drift.** `Contract.swift` decodes Plan 1's golden fixtures
   (`tests/fixtures/json_contract/`), which are binding. Confirm nothing across
   25 commits altered decoding semantics. Task 9 added a computed
   `cropRetryToken`; verify it is genuinely additive.
4. **Consistency across the four views** built by different rounds — status
   mapping, error surfacing, image loading (all should route through
   `PreviewImage`), and accessibility labelling.
5. **Anything that only appears at branch scale**: duplicated logic, dead code,
   abandoned seams, `#if DEBUG` surface that should not ship.

## Explicitly out of scope

Plan 1 / the python pipeline (merged and separately reviewed) and the
`HANDOFF.md` churn on this branch (an artifact of Codex's stop hook; the
authoritative checkpoint lives on `main`).

## Output

Write `whole-branch-review.md` **in this ledger directory**: severity-ordered
findings with file:line and a concrete failure scenario; an explicit
fix-now / file / drop verdict for **each** deferred item above; and a plain
statement of whether this branch should merge to `main` as-is.

The user will decide the merge; give them what they need to decide it.
