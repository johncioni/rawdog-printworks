# Task 11 re-review — dispatch (final task)

Reviewer: Opus 5 xhigh. Scope: **`de1e774..HEAD`** (`28dd02d` Task 10's fix round,
`b311322` Task 11 steps 1-2, `adae41c` a HANDOFF revert).
Read `task-11-brief.md`, `task-11-dispatch.md`, `task-11-report.md`, and
**`task-11-visual-qa-note.md`** (the controller's Step 3 gate result).

## Controller verification already done

- `swift test --disable-sandbox` → exit 0, **84** tests. `xcodebuild` → exit 0.
  `zsh scripts/build-app.sh` → exit 0, signed arm64 bundle.
- **Smoke-test mutation, mine and independent of the implementer's:** breaking
  the adjust envelope's `review_revision_before` fails it on three assertions,
  including the rebase-vs-stale distinction that is its whole point. (The
  implementer separately recorded its own RED via `executableOverride: nil`.)
- **Visual QA: 11 verified-distinct screenshots in `qa/pass/`**, each saved only
  after a helper confirmed an expected marker was on screen AND the image
  differed from every prior capture.
- **Full loop driven through the UI on the scratch repo**: slider → `adjust`
  (only pipeline-owned files written) → verified→review_required → 4 re-renders →
  audit → Approve enabled → approve+run → **v002 published, 29 artifacts, v001
  pruned** → verified. `git status` after: only `recipes/` and `sidecars/`.

## Your focus

1. **`SmokeTests` quality.** It is the app-side twin of Plan 1's golden fixtures.
   Does it actually pin the wiring, or does it assert things that cannot drift?
   Check the stub's argv dispatch, the review-file assertion (does it verify
   `expected_review_revision` matches, not merely that a file exists), and
   whether a plausible refactor could break the app while leaving it green.
2. **`scripts/build-app.sh`** — `set -euo pipefail` correctness, whether
   `--force --deep --sign -` is right for this app, and whether a failure
   anywhere actually fails the script.
3. **Two QA states I could NOT capture**: the render-progress bar and the
   "rendering preview…" shimmer. Are they reachable in code at all, i.e. is there
   a path where `renderProgress` is populated and rendered? Confirm by reading
   that they are implemented, since I could not observe them.
4. **The Release-vs-Debug input anomaly** (qa note, last section): every
   synthesized click on the Release build returns `window_not_focused` while the
   identical Debug build accepts them; AX reads work for both. Is this an app
   concern (window/scene configuration, activation policy) or purely a macOS
   signing/permission artifact of the ad-hoc-signed bundle? If it is the app's,
   it is a real finding; if not, say so and I will stop worrying about it.
5. Anything Task 10's fix round or Task 11 **broke** in Tasks 1-9.

## Out of scope

The long-deferred pile (m6-m10, i11, N3/N5, n13-n21, kqueue vs in-place edits,
`Output/photos/<stem>/`, the Task 5 refresh gate) — those go to the whole-branch
review, which is the next step after this.

## Output

Write `task-11-rereview.md` **in this ledger directory**. Severity-ordered
findings with file:line and a concrete failure scenario, and a plain statement of
whether Task 11 — and therefore Plan 2's task list — is complete.
