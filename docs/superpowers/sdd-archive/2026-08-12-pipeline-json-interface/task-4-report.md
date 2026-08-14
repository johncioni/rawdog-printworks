# Task 4 report — `pipeline/provenance.py`

## What was built

Two new files, additive only; no pre-existing file was modified.

- `/Users/john/photo-edits/.claude/worktrees/json-interface/pipeline/provenance.py` — implemented verbatim from the brief's Step 3 code. Public surface: `gather_material(stem)`, `style_input_hash(stem, style, rec, material=None)`, `content_hash(path)`, `record_preview(rec, stem, style, preview_path, inputs_hash)`, `stale_styles(stem, rec, material=None)`, `review_revision(stem, rec, material=None)`, plus module-private `_canonical_sha` and `_preview_path`.
- `/Users/john/photo-edits/.claude/worktrees/json-interface/tests/test_provenance.py` — the brief's Step 1 test file, verbatim (6 tests).

`pipeline/recipe.py` was **not** touched: the new optional recipe keys (`previews`, and later `app_adjustments`/`delivery_id`) do not enter `recipe.fingerprint`, which reads named keys only.

## TDD sequence followed

1. **Step 1** — wrote `tests/test_provenance.py`.
2. **Step 2** — `pytest tests/test_provenance.py -q` → collection error, `ImportError: cannot import name 'provenance' from 'pipeline'`. Verified failing before implementing.
3. **Step 3** — wrote `pipeline/provenance.py`.
4. **Step 4** — `pytest tests/test_provenance.py -q` → `6 passed in 0.21s`.
5. **Step 5** — full gate `/Users/john/photo-edits/.venv/bin/python -m pytest tests/ -q` → `194 passed in 14.27s`.

## Test evidence

| Run | Command | Result |
|---|---|---|
| Baseline (before any change) | `pytest tests/ -q` | 188 passed |
| Failing check | `pytest tests/test_provenance.py -q` | collection ImportError (expected) |
| New tests | `pytest tests/test_provenance.py -q` | 6 passed |
| Full gate | `pytest tests/ -q` | 194 passed, 0 failed |

188 + 6 = 194: every pre-existing test still passes, unmodified.

Quality gate scope: the repo has no `pyproject.toml`, `setup.cfg`, `.ruff.toml`, `mypy.ini`, or `tox.ini`, and the venv contains no ruff/mypy/flake8/pyright. There is no configured typecheck or lint step, so the pytest run above is the full gate.

Beyond the brief's tests, I ran an out-of-tree verification script (in the session scratchpad, not added to the repo) that builds a temp pipeline root, calls `gather_material`, then replaces `Path.read_bytes`, `Path.read_text`, `Path.open` and `builtins.open` with a function that raises, and calls `stale_styles`, `review_revision`, and `style_input_hash` with `material=`. All three returned normally — empirical confirmation of the zero-additional-reads / single-snapshot rule, including that `recipe.fingerprint` reaches no filesystem when handed pre-read `lock` and `lab` (`toolchain.entries_for` and `labprofile.review_view` are both pure).

## Deviations

1. **Did not run the brief's Step 5 git commands** (`git add` / `git commit`). The team lead's instruction "Do NOT run any git commands" overrides the brief. The two files are written and the full gate passes; the commit is left to the lead.
2. **Baseline test count is 188, not the brief's stated 186.** Tasks 1–3 landed tests after the brief was written. Observation only; no action taken.

No deviations from the brief's code itself — both files are the brief's text verbatim.

## Self-review

Checked against the brief's correctness properties (new files, so review is a read-through rather than a diff):

- **`content_hash` is uncached.** It hashes `path.read_bytes()` on every call with no size/mtime shortcut, and the comment records why. `test_same_size_restored_mtime_swap_is_stale` covers exactly the same-size + restored-mtime swap a cache would miss.
- **Single snapshot.** `gather_material` is the only function that reads the filesystem for style hashes, seed, lock, lab profile, and per-style preview content. `stale_styles` and `review_revision` consume `material["preview_hashes"]` rather than re-hashing previews, so the check-vs-persist window is not reopened. Verified empirically (above), not just by inspection.
- **`record_preview` takes a caller-supplied `inputs_hash`** and never computes one itself, so Task 5 can compute it before the render starts. It mutates `rec` and does not save — saving is the caller's job, as specified.
- **Staleness is a three-way OR**: missing provenance entry, input-hash mismatch, or content-hash mismatch. Each branch has a test (`test_missing_provenance_is_stale`, `test_input_change_is_stale`, `test_swapped_preview_content_is_stale`). Return value is `sorted(...)`.
- **`review_revision` reuses `recipe.fingerprint`'s canonical blob** rather than rebuilding one, so `status` and `approve` cannot drift, and folds in `material["preview_hashes"]`. Prefixed `"sha256:"`.
- **Monkeypatch compatibility preserved**: the module calls `toolchain.entries_for(...)` as a module attribute (not a `from ... import` binding), which is what lets the test fixture's `monkeypatch.setattr(toolchain, "entries_for", ...)` take effect in both `style_input_hash` and `recipe.fingerprint`. Worth keeping in mind before any future import-style cleanup.

Minor notes for downstream tasks (no change made, both are in the brief's verbatim code):

- `material = material or gather_material(stem)` re-gathers if a caller passes a falsy `material` (e.g. `{}`). No caller does, and the guard is the brief's; flagging only so Task 5/6 pass a real snapshot rather than a placeholder.
- `content_hash` catches `FileNotFoundError` only. A preview path that is a directory would raise `IsADirectoryError`; that is not a reachable state for the pipeline's own preview naming.
