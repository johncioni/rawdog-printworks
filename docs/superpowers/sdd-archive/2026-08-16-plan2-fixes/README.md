# Plan 2 fix round — scope contract

Branch `johncioni/plan2-fixes`, based on `3919b99` (the PR #5 merge). Plan 2 is
**already merged**; this round is the agreed follow-up.

## Sources (both in-repo, read them — do not re-derive)

- `docs/superpowers/sdd-archive/2026-08-12-printworks-app/whole-branch-review.md`
  — the whole-branch review. Findings F1–F11, and a verdict on every deferred item.
- `docs/superpowers/sdd-archive/2026-08-12-printworks-app/coderabbit-reconciliation.md`
  — how CodeRabbit's 32 findings map onto that review, plus what was dismissed.

## The user chose this scope. It is a contract, not a starting point.

**IN:** the review's F1–F6, CodeRabbit's Majors, and the weak-test cluster
(including its Minors, because a test that cannot fail is the defect).

**OUT — do not fix, even when you are editing the same file:**

- CR Minors not in the weak-test cluster: `GridView.swift:73-93` (failure code
  for the badge), `SidebarView.swift:35-47` (stable row identity),
  `ReviewView.swift:189-198` (bare shortcuts), `InspectorView.swift:50-56`
  (cached `nil` crops), `InspectorView.swift:75-77` (style-name helper),
  `RepoWatcher.swift:330-349` (coalesce reset — this is m6, deliberately filed).
- All 6 CR Trivials (named bindings, `lock.withLock`, `XCTUnwrap`, mark
  `private`, extract shared ingest, poll instead of sleep).
- `scripts/build-app.sh:5-7` — **dismissed as a false positive.**
  `OTHER_SWIFT_FLAGS='$(inherited) -disable-sandbox'` is the *Codex seatbelt
  workaround*, not a production build requirement. Do not add it to the shipping
  Release build.

Fix-by-adjacency is the main risk here. If you believe an out-of-scope item is
actually load-bearing for an in-scope one, say so in your report and leave it.

## Standing decisions — do not reopen

**m12: `runMutating` is intentionally uncancellable.** The user decided this
rather than accept SIGTERMing RawTherapee mid-write into `staging/`. Batch 3
contains an item adjacent to it with a specific, deliberately different remedy —
follow that spec literally.

## Batches

1. `batch-1-brief.md` — gating and safety (F1 F2 F3 F4 F5 F6)
2. `batch-2-brief.md` — tests that cannot fail
3. `batch-3-brief.md` — concurrency, correctness, performance

One batch at a time. The controller verifies and commits each batch before the
next is dispatched; your sandbox mounts `.git` read-only, so **do not commit**.
