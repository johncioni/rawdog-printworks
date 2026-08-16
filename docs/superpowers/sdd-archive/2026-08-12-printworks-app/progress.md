# SDD ledger — plan: docs/superpowers/plans/2026-08-12-printworks-app.md

Worktree: /Users/john/orca/workspaces/rawdog-printworks/plan2-printworks-app
Branch: johncioni/plan2-printworks-app (from origin/main @ 60facc9)
Spec: docs/superpowers/specs/2026-08-12-macos-app-design.md (binding authority)

Global Constraints (from plan §Global Constraints, binding on every task):
macOS 15 min; SwiftUI; no third-party UI dependencies (XcodeGen is a build-time
tool); no pipeline logic in Swift; no repo writes from Swift — the only
Swift-written file is the temp review-file, created OUTSIDE the repo; subprocess
env exactly: cwd=repo, python by absolute path from Settings,
PATH=/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin, argv only, never a shell.

## Pre-task: RAW-10 (not a plan task)

Ruling: RAW-10 runs before Task 1, extending the existing run_partial_failure
scenario rather than adding a new one — the goal is that Plan 2's decoder sees
failed[].code varying, and the canonical partial-failure fixture is where a
decoder author looks. Cost if wrong: a larger regenerated fixture diff.

## Pre-flight conflict scan

Cross-task rows (pairs sharing a file or interface):

| Producer → Consumer | Shared surface | Finding |
|---|---|---|
| T1 → T2 | Contract.swift, ContractTests.swift | T1 creates placeholder + `Contract.version == 1` test; T2 "replaces placeholder". Clean, but T2 must not delete the version test. Carried into T2 dispatch. |
| T1 → T7, T10 | PrintworksApp.swift | T1 creates; T7 wires AppModel/watcher, T10 adds Settings scene. Sequential, no overlap in concern. Clean. |
| T1 → T11 | RAWdogPrintworks.xcodeproj (XcodeGen) | T11's build script consumes T1's project generation. Clean. |
| T2 → T3, T4, T5 | Contract models | All consume; none redefine. Clean. |
| T5 → T7, T9, T10 | AppModel.swift | T7 modifies "only if a computed helper is missing — no behavior changes"; T9 and T10 add behavior "test-first". Clean, but T7's no-behavior-change limit must be enforced at review. Carried into T7 dispatch. |
| T7 → T8 | MainWindow.swift | T8 replaces T7's `ReviewScreen` stub — T7 must actually leave a stub by that name. Carried into T7 dispatch. |
| T8 → T9 | ReviewView.swift | T9 adds overlay + inspector column. Clean. |
| T4, T3 → T11 | Debouncer/flushPendingAdjustments, PipelineClient | Smoke test drives the real objects. Clean. |
| T6 → T7 | RepoWatcher | Wired into PrintworksApp by T7. Clean. |
| T11 → tests/conftest.py | Python test suite | READ ONLY — T11 mirrors the dir list to build a temp fixture repo. No Python write. Clean (verified: "dirs from `tests/conftest.py` list"). |

Per-task self-consistency rows: T1 (5 steps / 5 test mentions), T2 (5/5),
T3 (5/4), T4 (3/5), T5 (4/4), T6 (3/3), T11 (4/3) — each task's Create/Modify
list matches the files its own steps and interfaces name. T7 (4 steps / 1),
T8 (4/1), T9 (5/0), T10 (4/0) are the SwiftUI view tasks: they name no unit
tests of their own by design, because the plan's stated gate for view work is
`xcodebuild build` plus the visual-QA screenshots in T11, with logic changes
pushed down into AppModel "test-first". Consistent with the plan, not a defect.

FINDING (ruled): the plan uses two path conventions with no stated rule —
T1-T3 write `app/PrintworksCore/Sources/...` in full, while T4, T5, T6, T7, T9,
T10 write bare `Sources/PrintworksCore/...`. An implementer given only its brief
would plausibly create `Sources/PrintworksCore/CropMath.swift` at the REPO ROOT,
outside the package, breaking the build.
Ruling: bare `Sources/…` and `Tests/…` paths are relative to
`app/PrintworksCore/`; app-target files live under `app/RAWdogPrintworks/Sources/`.
Carried verbatim into every dispatch from T4 onward. Cost if wrong: files land
in the wrong directory and the package fails to build — caught by the task's own
`swift test`, so recoverable, but it would burn a fix round per task.

## Task log

RAW-10: complete (commits 60facc9..a3e8363, review clean — spec ✅, quality
approved, no findings; reviewer independently re-ran the gate and confirmed the
fixtures regenerate byte-identically, so they are generated not hand-edited).

Task 1: implemented (commit 0bff85d, 10 files / +436). BASE was a3e8363.
Implementer DONE: swift test 1/1, xcodebuild BUILD SUCCEEDED, Python suite
unchanged at 295 pass / 1 skip, worktree clean. xcodegen 2.46.0 installed via
brew (authorized; any other machine or CI building this needs the same step —
carry into Task 11, which owns the release build script).
Task 1: complete (commits a3e8363..0bff85d, review clean — spec ✅, quality
approved, no Critical/Important findings). Reviewer independently re-ran
`swift test`, `xcodebuild build` AND `clean build`, and confirmed .gitignore
actually suppresses every build byproduct in practice.
- Committed project.pbxproj is NOT a deviation: mandated in three places
  (brief Step 5, spec §9 line 235 "Xcode project (committed)", plan line 39).
  Task 11's release script re-runs `xcodegen generate` first, so the release
  path never trusts the checked-in copy; the committed one serves spec §9's
  "open in Xcode, ⌘R" dev workflow. `app/**/xcuserdata/` correctly excludes the
  user-specific noise while leaving the shared pbxproj tracked.
- CARRY INTO LATER TASKS: any task that edits `project.yml` must regenerate and
  commit the `.xcodeproj` in the SAME commit, or the two drift.
- The xcodebuild `warning:` is benign (App Intents metadata processor reporting
  nothing to extract; Xcode 15+ inserts that phase into every app target).
- CARRY INTO TASK 11: the brief's build command passes no `-destination`, so
  xcodebuild emits "Using the first of multiple matching destinations" on this
  machine. Harmless now; the release script should pin a destination.

Task 2: complete (commits 0bff85d..3378ea9, review clean — spec ✅, quality
approved, 1 deferred minor). swift test 10/10, xcodebuild BUILD SUCCEEDED,
Python gate unchanged 295/1. Reviewer independently re-ran the suite and
confirmed the closed-enum guard is enforced at COMPILE time (an enum-typed
`.code` would not type-unify with the String literals the tests compare
against), which is stronger than the runtime guarantee I asked for.

Task 2: minor (deferred): optional fields are not drift-tested. A rename on an
optional key (CropsResult.basis, CropWindow.source, ToolchainIssue.problem,
PhotoStatus.published, deliveryId/ingestedAt) decodes to nil rather than
throwing, and the brief's mandated Step 1 tests assert decode-success only, not
field values. Required fields ARE structurally protected (keyNotFound throws).
Partly a fixture-coverage gap: toolchain.failures is [] and published is null in
every current fixture, so some optionals have no real data to test against.
Out of scope for Task 2 (frozen fixtures + mandated test body). POINT THE FINAL
WHOLE-BRANCH REVIEW AT THIS to triage before merge.

Ruling (Task 2, plan-internal conflict): Task 2's Interfaces block names a test
helper `repoFixturesURL()`, but its own Step 1 verbatim code inlines that path
logic in a private `fixture(_:)` method instead. The implementer followed the
literal Step 1 code. RATIFIED — Step 1 is the code that actually runs and is
self-consistent; adding an unused free function to satisfy an Interfaces line
would be dead code. Verified myself that `repoFixturesURL` appears ONLY in the
plan's own Task 2 section and Task 2's brief/report — no later task consumes
it. Cost if wrong: a 3-line extraction, trivially recoverable.

Ruling (Task 2, typing): `code` fields stay plain `String` (per the brief's
literal typing) rather than a Swift enum. This is what makes all ten contract
codes AND an unrecognised future code decode without a closed-enum trap — the
whole reason RAW-10 ran first. A closed enum here would be a latent crash.

Task 3: implemented (commit 243f154). BASE 3378ea9. swift test 17/17 (run 3x
for flake-checking), xcodebuild BUILD SUCCEEDED, Python gate 295/1, clean.

Ruling (Task 3, plan defect in a test oracle): the brief's verbatim
`testEnvironmentAndCwdPinned` assertion cannot pass on macOS. I verified this
myself rather than accepting the implementer's account: `URL.resolvingSymlinks
InPath()` leaves `/var` as `/var` (NSTemporaryDirectory stays /var/folders/…),
while the stub script's cwd resolves through realpath to /private/var/folders/…
— so neither branch of the brief's disjunction can ever match on this host.
RATIFIED the implementer's fix: canonicalize BOTH sides via realpath(3) in the
test oracle only; `PipelineClient.swift` stays verbatim to the brief. Because
both sides are canonicalized, a genuine cwd bug still fails the test. Cost if
wrong: a too-permissive oracle could mask a cwd regression — mitigated by the
reviewer being asked to check exactly that.

Task 3 review: spec ✅ but 1 CRITICAL + 1 IMPORTANT → fix loop entered.
CRITICAL: `readabilityHandler` can be invoked concurrently by two GCD threads
for the same pipe. `handle.availableData` is read OUTSIDE the lock and appended
INSIDE it, so append order follows lock-acquisition order, not read order —
chunks splice out of order, the spliced JSON fails to parse, and `try?` drops
the event silently. Reviewer measured 112-263 of 400 progress events delivered,
reproduced under TSan AND in plain release builds, via its own stress harness.
IMPORTANT: the brief's prose specifies a direct `LineCollector` chunk test
("ab", "c\nde", "f\n") that was never written; all 7 delivered tests use single
atomic `echo` writes under PIPE_BUF, which is why the race went undetected.

Ruling (Task 3, finding vs plan text): the CRITICAL defect is present VERBATIM
in the brief's own mandated Step 3 code — the implementer did not introduce it.
FIXING ANYWAY. The spec is the binding authority and it requires progress
events to reach the UI live during multi-minute renders; silent event loss
violates that, and the plan's code is only the plan's argument for how to meet
it. Deviating from mandated code here is correct. Cost if wrong: a small
divergence between plan text and implementation, which the plan's own later
tasks never read. Not fixing would push silent data loss into every progress
bar built on this actor in Tasks 7-11.

Task 3: fix round 1/5 (2 addressed pending re-review, 0 open; commits
243f154..e47ad9c). The implementer TESTED the suggested mechanism rather than
assuming it: wrapping the handler in `DispatchQueue.sync` reduced but did not
eliminate the race (1-2 failures per 8 suite runs, clustered near process
exit). It then removed `FileHandle.readabilityHandler` entirely for a dedicated
blocking-read loop per pipe (`drain`), making concurrent access structurally
impossible rather than synchronised-around. 20/20 tests; 20 full-suite + 40
stress-only + 20 shutdown-sensitive runs, zero failures; clean TSan; xcodebuild
OK. `LineCollector.finish(_ handle:)` → `flushRemainder()` (internal only, no
downstream consumer). Disclosed concern under re-review: `drain` blocks one GCD
global-queue worker per pipe for the subprocess lifetime.

Task 3: complete (commits 3378ea9..e47ad9c, 1 fix round, re-review clean —
both findings ADDRESSED, no new breakage). The re-reviewer did not take the fix
on trust: it rebuilt the PRE-FIX code from git in a scratch dir and reproduced
the bug (4/150 exit-boundary failures, 731/800 events on a burst), then ran the
same harness against the fixed code for 0/150 across ~280 stress iterations,
plus 20 full-suite runs, 40 burst runs, 4 TSan runs, and a 20-concurrent-client
test. It also confirmed the new burst test genuinely discriminates by running
it against pre-fix source. Subprocess constraints re-verified intact after the
rewrite (cwd, absolute python, exact PATH, argv-only, ContractDecoder.make()
reused, exit code never consulted).

Task 3: minor (deferred): `drain` blocks one GCD `.utility` worker thread per
pipe for each subprocess's lifetime, so each live subprocess ties up two OS
threads. Not a deadlock — every drain unblocks when its subprocess exits — but
unbounded under load, and `run()` (unlike `runMutating`) caps nothing. Fine for
the app's actual shape (one PipelineClient per repo). RELEVANT TO TASK 5 AND
TASK 11: if either lets clients or concurrent `run()` calls proliferate, bound
it with a semaphore or a limited-concurrency executor. POINT THE FINAL
WHOLE-BRANCH REVIEW AT THIS.

Task 4: implemented (commit 3dc7904). BASE e47ad9c. 25/25 tests across 20
invocations (suite x6, DebouncerTests x10 sequential + x4 concurrent),
xcodebuild OK, Python 295/1, clean. Reviewer dispatched.

Ruling (Task 4, toolchain adaptations): the brief's verbatim code did not
compile on Swift 6.2.4 / Xcode 26.3 — `import CoreGraphics` was needed for
CGRect's labeled init, and raw `NSLock.lock()/unlock()` is unavailable in async
contexts so `fire()` uses `NSLock.withLock {}`. RATIFIED pending the reviewer
confirming both are genuine toolchain constraints and behaviour-preserving.
These are adaptations to make mandated code build, not design changes; no
public signature moved. Cost if wrong: a hidden behavioural change inside a
lock — which is why the reviewer is asked to verify the claims, not accept them.

Task 4: complete (commits e47ad9c..3dc7904, review clean — spec ✅, quality
approved, 1 deferred minor). Reviewer worked the crop math by hand for BOTH
orientations (incl. a portrait case the tests omit), cross-checked the clamping
against pipeline/geometry.py's `subject_crop_norm` (same idiom — Swift mirrors
the pipeline rather than redefining validity), reproduced BOTH compile errors
by reverting the fixes (genuine toolchain constraints, confirmed), and
mutation-tested the debouncer three ways (fires-every / never-fires /
fires-first) — all caught, so the wall-clock test is not vacuous. It also noted
SPM's incremental build cache can produce a false pass and wiped `.build`
between mutations. Contract.swift's +8 lines were explicitly directed by the
brief (public memberwise init for CropWindow); RepoPathsTests' placement
mirrors the brief's own merged source file.

Task 4: minor (deferred): `aspectFitRect` tests exercise only a landscape 4:3
source across two container shapes; no portrait-source case is in the suite.
Implementation is orientation-agnostic and was verified correct by hand, so
this is a coverage gap, not a defect.

Task 4: minor (deferred): `testOnlyLastScheduledActionRuns` is wall-clock
dependent (50ms debounce / 150ms wait), kept verbatim from the brief rather
than changing Debouncer's public API to inject a clock. Stress-run 19x with a
~100ms margin. Blast radius is local only — Swift tests do not run in CI, only
the Python suite does. IF SWIFT TESTS EVER JOIN CI, this is the flake
candidate; revisit then.

Task 5: implemented (commit 532c311, +1255). BASE 3dc7904. 40/40 tests run 4x,
xcodebuild OK, Python 295/1, clean. Status DONE_WITH_CONCERNS.

Ruling (Task 5 vs Task 6 boundary): the implementer built TASK 6's briefed
refresh gate (one `status` in flight + one trailing) inside Task 5 and flagged
it rather than hiding it. RATIFIED, it stays. Task 5's own action cycle is the
second independent `refresh()` caller, so the fan-out exists the moment this
lands, and WITHOUT the gate the brief's own
`testDebouncersAreKeyedPerStemAndStyle` has a real data race — two overlapping
`applyAdjust` calls hit `FakeClient.statusQueue.removeFirst()` from different
threads. Shipping a known race to preserve a task boundary would be exactly the
mistake Task 3 cost us a fix round for. CARRY INTO TASK 6: the gate already
exists (~6 lines at the top of `refresh()`); Task 6 must not duplicate it, and
its reviewer must confirm the existing gate satisfies Task 6's spec.

Task 5 answered the carried Task 3 concern: the design does NOT fan out per
photo or per keystroke — grid/sidebar read `snapshot` and load JPGs off disk
with zero subprocesses, sliders coalesce through the per-(stem,style) debouncer
into a queued mutation, and each action issues at most one sequential `status`
plus an optional `crops`. The only genuine edge was concurrent `refresh()`
callers, which the gate closes. Unbounded-`run()` concern is therefore CLOSED
for the app's own paths; the raw `PipelineClient.run()` cap remains unbounded
for any future caller.

CARRY INTO TASK 7: `RunResult.failed` is not stored on the model, so spec §7's
per-card "render failed" badge needs one more field. Task 7's brief does not
mention it — its dispatch must, or the badge silently cannot be built.

Task 5: minor (deferred): `INGEST_NOTICE` is a synthetic code — skips and
conflicts are not failures, but the brief routes them through the
`PipelineErrorInfo`-typed banner. Cosmetic typing smell, per brief.
Task 5: minor (deferred): `approve(stem:)` writes all three audit strings as
": pass" unconditionally (per brief); correct only because `canApprove` gates
it. Fragile if `canApprove` is ever relaxed.

Task 5 review: SPEC ❌ + 1 Critical + 5 Important + 4 Minor → fix loop.
Reviewer probed rather than inferred; all findings reproduced.

SAFETY VERDICT FIRST (the one that matters): every failure is fail-CLOSED. The
reviewer probed specifically for whether the deferral can swallow a genuine
external edit and it cannot — `reconcileDrafts` only ever SETS isStale, the
terminal refresh always reconciles, and the pipeline's own
expected_review_revision → STALE_REVIEW is an independent backstop. THE APP
CANNOT APPROVE PIXELS THE USER NEVER LOOKED AT.

C1 (Critical) `flushPendingAdjustments` does not flush. AppModel.swift:340-356
iterates `pendingAdjustments`, but `firePendingAdjust` CLEARS the entry before
issuing the command — so once the debounce timer fired, flush finds nothing and
returns while the adjust is still in flight. Real path: drag slider → 2s
debounce fires → click Approve inside the command window → approve serializes
`expected_review_revision` from the PRE-adjust draft. Either order is wrong
(STALE_REVIEW + re-check everything, or approve succeeds and the adjust then
demotes the just-published photo). Fix: track the in-flight task per key (or
clear the entry only after the adjust completes) and await it.
A2/I1 (Important) §6.1 deferral leaks: `reconcileDrafts` tests
activeCommand/activeStem at RECONCILE time, not CAPTURE time, so a refresh
whose status was taken during the command but lands after `endCommand` falsely
stales the draft — and nothing can un-stale it. Deterministic 5/5. Becomes an
everyday event the moment Task 6's watcher + 5s poll land. Fix: stamp the
snapshot with the commandGeneration/activeStem in force when `status` was
DISPATCHED.
FLAKY SUITE: `swift test` fails ~14% (5 in 35 runs), always
testDebouncersAreKeyedPerStemAndStyle, a consequence of C1. The implementer's
"4 runs green" was simply not enough runs — treat <20 runs as no evidence for
this package.
I2 every timer-driven adjust runs inside an ALREADY-CANCELLED Task —
Debouncer.fire() cancels pendingTask while executing inside it (probe:
Task.isCancelled true, sleep(200ms) returns in 0.3ms). Harmless only because
PipelineClient's I/O is cancellation-insensitive. ROOT CAUSE IS TASK 4's
Debouncer; Task 4's 2 tests cannot see it. Landmine for any future timeout.
I3 retry banner button is dead on two paths (surface() sets bannerAction=.retry
with lastFailedAction nil) — Task 7 would wire a dead button.
I4 overlapping actions clobber activeCommand/activeStem → busy pill lies,
canApprove goes false, and the §6.1 deferral is disabled for the other stem.
I5 `RunResult.failed`, `RunResult.advanced` and `IngestResult.failed` are ALL
dropped (applyRunResult:578-581 keeps only `published`). Spec §7 needs the
per-card badge from result.failed. Cheapest to fix here while applyRunResult is
the single write site.
M1 endCommand's refresh can be absorbed by the gate (affects Task 11's
post-await assertions). M2 progressKeys/commandGeneration are single-valued
across concurrent commands. M3 busyExternally sticks on if refresh fails.
M4 the brief's FakeClient has an unsynchronized mutateLog — the gate closes
only the statusQueue half, so "structurally impossible" was overbroad.

Reviewer also caught that ONE of the implementer's own added tests does not
discriminate: testReconcileIsDeferredWhileTheStemsOwnCommandRuns sets the flags
by hand and refreshes synchronously, proving only that the `continue` exists —
it never exercises a refresh that STARTS during a command and LANDS after,
which is the only shape the bug takes. It stays green while the case fails.

Refresh gate verdict: correct and race-free as written, and it is spec §7
behaviour verbatim (watcher-storm rule), not merely borrowed Task 6 scope — so
the earlier ruling to keep it in Task 5 stands.

CODEX DISPATCH LESSON (cost one wasted 6-minute run, task-msskqmga-fv1ss0):
Codex's writable root is the CWD OF THE PROCESS THAT LAUNCHES IT, and
`codex-companion.mjs task` has no --cwd flag. Dispatching through the
`codex:codex-rescue` subagent inherits the controller session's cwd (the main
checkout at ~/Projects/rawdog-printworks), so every edit to the Orca worktree
at ~/orca/workspaces/... was rejected: "patch rejected: writing outside of the
project". Codex read the spec and had correctly isolated the F2 RED case before
it hit the wall — the work was fine, the mount was not.
CORRECT INVOCATION (matches Plan 1's ledger: "cwd = worktree"): call the
companion directly from the worktree —
  cd <worktree> && node <plugin>/scripts/codex-companion.mjs task \
    --background --write --fresh --model gpt-5.6-sol --effort xhigh "<prompt>"
Relaunched as task-mssl68qs-lmks2k. Also note `task --help` is NOT a help flag —
it is taken as a prompt and starts a real (read-only) Codex thread; use the
bare `codex-companion.mjs` with no args for usage.

Task 5: fix round 1/5 COMMITTED as 7e19bee (Codex gpt-5.6-sol xhigh implemented
F1-F6; controller staged and committed because .git is read-only in its
sandbox). Scoped re-review dispatched on review-532c311..7e19bee.diff.
CONTROLLER VERIFICATION (I ran these myself, not Codex): xcodebuild BUILD
SUCCEEDED with an explicit -destination; `swift test` 15 consecutive runs,
15/15 green at 45 tests (was ~14% flaky, 5 failures in 35 runs, before the fix);
pytest 295 passed / 1 skipped; only the 4 intended Swift files changed, no
Python and no fixture drift.
NOTE: Codex's own xcodebuild attempt failed (exit 74) inside its sandbox even
with CFFIXED_USER_HOME set — a sandbox limitation, NOT a code failure. The
controller must run xcodebuild verification for Codex-implemented tasks.
The Codex job was still running at 15m42s when I committed; its work was
complete on disk and independently verified, so I did not wait for its report.

Codex job task-mssl68qs-lmks2k COMPLETED at 20m21s: "Implemented all six
findings with regression coverage." Its own reported evidence:
- F1 identity-stamped in-flight adjust tasks; flush awaits all styles.
- F2 status snapshots capture command generation/stem AT DISPATCH TIME.
- F3 timer fire clears its task without self-cancelling; generation guards the
  replacement.
- F4 retry button suppressed when no retry closure exists; both paths tested.
- F5 run advanced/failures and ingest file failures retained.
- F6 rewritten race test FAILED PRE-FIX AND PASSES POST-FIX (the red/green
  proof I required), keyed test covers 3 pairs.
- swift test 25/25 runs, 45 tests each; pytest 295 passed / 1 skipped.
This corroborates my own independent verification (15/15 runs, xcodebuild
SUCCEEDED, pytest 295/1) recorded above.

CODEX BOUNDARY VIOLATION (caught and reverted): Codex also rewrote the
WORKTREE's HANDOFF.md, replacing the project checkpoint with a Task-5-scoped
summary (24 insertions / 47 deletions). That file is the branch's copy of the
project checkpoint and would have carried a task scratchpad into the merge. I
reverted it and captured the evidence here instead. LESSON FOR FUTURE CODEX
DISPATCHES: explicitly forbid touching HANDOFF.md — it reads HANDOFF.md for
context (it said so in the blocked run) and evidently treats it as its own
checkpoint to update.

Task 5: COMPLETE (commits 3dc7904..7e19bee, 1 fix round, re-review clean —
all six findings ADDRESSED, no new Critical/Important breakage, verdict
"ship it"). The re-reviewer verified by REVERTING individual fixes in scratch
copies rather than reasoning: reverting only the flushPendingAdjustments body
reproduced the exact pre-adjust-revision bug 5/5 AND reproduced the historical
flake, independently confirming F1 was the flake's root cause; reverting only
the F2 change made the rewritten deferral test fail 5/5 deterministically;
restoring the single `pendingTask?.cancel()` line failed the new F3 test 3/3.
F1 is closed BY CONSTRUCTION, not by narrowing: the removeValue and the
inFlightAdjustments assignment sit in one synchronous @MainActor block with no
suspension point, so flush can never observe the entry in neither map.
Safety property re-verified and IMPROVED: reconcileDrafts still only ever SETS
isStale, the capture-time deferral cannot swallow an external edit (both rebase
gates live outside the deferral window), and F1 changed approve's failure mode
from "silently serializes the pre-adjust revision" to "rebase or mark stale and
let the pipeline reject" — both fail-closed, the new one strictly better.
Suite: reviewer's 15/15 on top of my 15/15, 45 tests.

CARRY INTO TASK 6 — IMPORTANT, and Task 6 is what makes it bite:
The MIRROR of F2 is still open. A status dispatched while IDLE that lands after
an adjust rebased the draft reconciles a pre-command snapshot and falsely marks
the draft PERMANENTLY stale (reconcile never clears isStale). The re-reviewer
probed it: it fails on the fixed code AND on the F2-reverted code, so it is
pre-existing, not introduced by the fix round — which is why it was logged
rather than looped. It becomes an everyday occurrence the moment Task 6 adds
the 5-second poll, exactly as the spec argued for F2 itself.
Fix is one line, and the field already exists: the fix diff added
`SnapshotCapture.commandGeneration` and never uses it beyond a nil-check —
also skip reconcile when `capture.commandGeneration != commandGeneration`
(i.e. a command began or ended between dispatch and landing). DO THIS AS PART
OF TASK 6, before the poll lands.

Task 5: minor (deferred): applyRunResult/applyIngestResult early-return on a
nil result, so a hard failure leaves the previous run's failures visible (same
pre-existing pattern as lastPublished). flushPendingAdjustments snapshots its
key set once, so a slider moved DURING the flush is not covered (inherent to
any flush design). testDebouncersAreKeyedPerStemAndStyle compares a Set so it
would not catch a duplicate adjust — exactly-once still holds by lock/
generation reasoning, but no test asserts it.

F2-MIRROR: FIXED (commit 3212f6c, controller-implemented, TDD). The carried gap
above is closed before Task 6's poll lands, as directed.
- Test first: `testReconcileIsSkippedWhenACommandRanBetweenDispatchAndLanding`
  is the deliberate mirror of `testReconcileIsDeferredWhileTheStemsOwnCommandRuns`
  — same fixture, same gates, the ONLY difference being that the watcher refresh
  is dispatched while IDLE and the adjust begins after it. Watched it fail first
  (XCTAssertFalse on isStale, AppModelTests.swift:539).
- Fix: `SnapshotCapture.commandGeneration` is now always stamped (was nil when
  idle, which is why the mirror case had no guard at all); `activeStem` alone
  now carries "a command was running at dispatch". `reconcileDrafts` early-returns
  when the generation moved between dispatch and landing.
- The naive form of this fix does NOT work: with `commandGeneration` left as
  `Int?`, `capture.commandGeneration != commandGeneration` is nil != Int, i.e.
  ALWAYS true when captured while idle, which disables reconciliation entirely
  for the common case. The field had to become non-optional first.
- Discrimination proof, not assertion: removing ONLY the guard line in a scratch
  copy fails the new test 5/5, and it is the only test in the package that fails
  — so the guard is load-bearing and nothing else depended on the old shape.
- Gates: swift test 20/20 consecutive green at 46 tests; xcodebuild BUILD
  SUCCEEDED (-destination pinned); pytest 295 passed / 1 skipped; only the two
  intended Swift files touched.
- Fail-closed re-verified: reconcile still only ever SETS isStale; this only
  suppresses a verdict from a snapshot already known to be out of date, and the
  gate's trailing refresh (plus the pipeline's expected_review_revision →
  STALE_REVIEW backstop) still judges the draft against current disk truth.
- Shared-fixture rename in the same commit: `DeferredReconcileClient`'s
  `capturedDuringCommand:` → `heldStatus:`, because the label is now wrong for
  half its call sites (mine holds a status captured BEFORE the command).

Task 6: DISPATCHED to Codex gpt-5.6-sol xhigh as task-mssrwrc5-9wl7s9 (cd $WT
first, per the ledger's dispatch lesson). The dispatch carries five rulings the
brief does not: the bare-`Sources/` path convention; "the refresh gate already
exists in AppModel — verify it, do not rebuild it, do not add a second gate
test"; a hard file-scope limit that explicitly forbids touching HANDOFF.md
(it overwrote it last time); no git and no xcodebuild in its sandbox; and the
20-run anti-flake gate (watcher tests are the most timing-sensitive in the
package). It also mandates tests the brief omits for `startPolling`/
`stopPolling`, the missing-directory rule, and fd closure on `stop()`.

Task 6: implemented (commit b3fcf2a, +399 across exactly 2 files). BASE 3212f6c.
Codex job task-mssrwrc5-9wl7s9 finished in ~22 minutes, verdict DONE; the
controller committed for it (.git read-only in its sandbox).
CONTROLLER-RUN GATES (mine, not the implementer's): swift test 20/20
consecutive green at 50 tests (46 + 4 new); xcodebuild BUILD SUCCEEDED with a
pinned -destination; pytest 295 passed / 1 skipped; `git status` confirmed only
RepoWatcher.swift + RepoWatcherTests.swift were added.
Implementer's own evidence, corroborating: RED captured before implementation
("cannot find 'RepoWatcher' in scope" x4), 20/20 full-suite and 20/20
RepoWatcherTests-only runs, pytest 295/1.
Disclosed toolchain adaptation (3rd task in a row to hit one): the brief's
verbatim `withTimeout` helper does not compile under Swift 6.2.4 strict
concurrency — "capture of 'iterator' with non-Sendable type
AsyncStream<Void>.Iterator in a '@Sendable' closure" and "mutation of captured
var 'iterator' in concurrently-executing code". Iterator locals became
`nonisolated(unsafe) var`; no public signature moved. Pointed the reviewer at
whether that opt-out is actually safe when `withTimeout` cancels a child
suspended inside `iterator.next()`.
Beyond the brief, it added tests for polling start/stop, the missing-directory
retry, and fd closure at the OS boundary (`fcntl(F_GETFD)` → EBADF), all of
which the brief omitted — those were required by the dispatch, not volunteered.
It also confirmed the existing Task 5 refresh gate satisfies the brief and left
it untouched, as directed.

CODEX BOUNDARY VIOLATION, ROOT CAUSE NOW KNOWN (2nd occurrence): it rewrote
HANDOFF.md again despite an explicit, prominent prohibition in the dispatch —
and this time it said why: "Refreshed this checkpoint for the mandatory stop
hook; the report discloses it." The user's global Stop hook fires inside
Codex's session too and instructs it to refresh HANDOFF.md before finishing,
and it (correctly, per that hook's own wording) obeyed the hook over my
instruction. So the prohibition CANNOT win — it is not a discipline problem.
It rewrote from the WORKTREE's stale branch-point copy, so the result was a
task summary grafted onto pre-Plan-2 content (PR #3/#4, main = 0e3749b).
Reverted; the two intended files were untouched by it.
FOR EVERY FUTURE CODEX DISPATCH: expect HANDOFF.md to come back modified, and
either (a) revert it as a routine post-step, or (b) give the hook something
legitimate to satisfy — tell Codex to treat task-N-report.md as its checkpoint
and to restore HANDOFF.md from git before finishing. Do not spend another
dispatch's prompt budget on a prohibition that the hook outranks.

NOTE (spec vs plan wording, not a defect): spec §6 item 5 says "FSEvents"; the
plan/brief mandate kqueue `DispatchSource` per directory, which is why the brief
enumerates every review-input directory (kqueue is non-recursive). kqueue
satisfies the observable requirement; implementing FSEvents instead would be a
design change, so the brief governs. Flagging for the final whole-branch review.

Task 6 review: SPEC ❌ + 1 CRITICAL + 5 IMPORTANT + 6 minor → fix loop entered.
Full text: .superpowers/sdd/2026-08-12-printworks-app/task-6-review.md. The
reviewer built harnesses and mutants for everything; it also reported what it
probed and found FINE, which is as useful as the findings.

C1 (Critical) `changes` is SINGLE-SHOT. It is one `AsyncStream` built in `init`,
and `AsyncStream.Iterator.next()` finishes the whole stream when its consumer
task is cancelled — not just that read. So the first cancelled consumer kills
the watcher for the object's lifetime. Compounding: `stop()` never finishes the
continuation (only `deinit` does), so a `for await` loop CANNOT be ended by
stopping the watcher — cancellation is the only exit, and cancellation is what
destroys it. Spec §6 item 5 makes this stream the app's ONLY refresh path ("No
refresh button exists"), so the failure mode is the entire UI silently freezing
with no error and no recovery short of relaunch. Proven with three probes, incl.
the exact `.task {}` shape Task 7 would use: consumerA=1, consumerB=0. The
kqueue side genuinely restarts across stop()/start() — only the stream cannot.
I1 coalescing, the headline behaviour, is NOT TESTED: a watcher yielding per raw
event (no coalescing at all) passes the shipped suite 4/4. Confirms the
controller's suspicion; origin is the brief's mandated test (misleading comment,
`XCTAssertNotNil` where it means "exactly one").
I2 six of the eleven watched directories can be DELETED from the list with the
suite green — including `Input/` (spec §6's own worked example), `run/` (what
clears the busy pill) and bare `config/` (toolchain.lock). All 11 verified to
work at runtime; this is purely a test gap.
I3 `stop()` deadlocks if reached on the watcher's own queue, and `deinit` is
that path (the queue transiently upgrades the weak self). Proven to hang with an
injected `queue.async { stop() }` (exit 3) but NOT reachable organically in 4500
randomised release-during-storm iterations. Fix because it is 3 lines
(setSpecific/getSpecific), not because it was measured in the wild.
I4 the 500ms coalesce is a pure trailing debounce with NO MAX-WAIT: 29 writes
over 6s at 200ms gaps produced 0 emissions during the activity. Since the busy
pill needs a refresh to set `busyExternally`, and that is what starts the 5s
fallback poll, steady CLI activity yields no pill and no fallback. Origin: the
brief's mandated Step 3.
I5 THE SUITE IS FLAKY AT HEAD AND MY 20/20 WAS LUCK, NOT PROOF: 48 green / 2 red
over 50 runs, always `testDebouncersAreKeyedPerStemAndStyle`. TSan finds exactly
ONE race in the whole suite and it is the test fixture — `FakeClient.mutateLog`
is a bare array appended from a `nonisolated` async func. This is the ledger's
own deferred Task 5 "M4", NOT Task 6 (same fixture at 3212f6c, and
`--filter AppModelTests` is 30/30 at both revisions). So Task 5's fix round cut
the flake from ~14% to ~4% by closing F1; M4 is the remaining half. Fixing it
now because it poisons every gate from here on.
LESSON ON GATE ORACLES: the reviewer recorded a false 20/20 by grepping
"Executed N tests, with 0 failures", which matches a PER-SUITE line rather than
the run. Use the process exit code. (My own runs used a whole-output grep for
the 50-test bundle line, which does discriminate — a failing run prints "with 1
failure" — so my 20/20 was a sound oracle over a genuinely lucky sample, not a
false green. Re-measuring at 30 runs with an exit-code oracle to pin the rate.)
FLAKE RATE, RESOLVED (controller re-measurement): 30/30 green with an EXIT-CODE
oracle, i.e. 50 consecutive green on my side vs the reviewer's 48/50. Not a
contradiction and NOT grounds to dismiss I5 — TSan's single reported race is
objective evidence independent of sampling, and the reviewer was running
mutants, sanitizers and xcodebuild CONCURRENTLY when it hit its 2 reds. The
failure is LOAD-DEPENDENT. Practical consequence for every future gate in this
package: a green suite on an idle machine is weak evidence; run the suite under
load, or use TSan, when the question is "is there a race".
Minors: the missing-directory test doesn't test its name (a start-once-only
mutant survives); the mandated test leaks its temp repo; `start()` racing
`stop()` off-MainActor can leave live fds (poll path is generation-guarded,
plain `start()` is not); the vanished-directory discard is untested.

Task 6: fix round 1/5 DISPATCHED to Codex as task-mssxil2l-p8mc9m, covering
F1=C1, F2=I1, F3=I2, F4=I3, F5=I4, F6=I5 (the FakeClient fixture race — the only
edit permitted outside the two Task 6 files), F7=the four cheap minors. The
dispatch requires red-then-green per finding PLUS a mutation check that each new
test dies when its behaviour is re-broken — because I1 and I2 exist precisely
because tests were written that could not fail. It also tells Codex the flake is
load-dependent so it does not "disprove" F6 on an idle machine, and mandates an
exit-code oracle over the grep that produced the reviewer's false 20/20.
Two findings are explicitly ruled OUT of the round as deliberate deferrals
(in-place-edit invisibility, unwatched `Output/photos/<stem>/`).
DEFERRED, deliberately: in-place non-atomic edits are invisible to kqueue (all
real pipeline writers use temp+os.replace; exposure is hand-edits under
`config/**` — this is the measured content of the FSEvents-vs-kqueue note
above), and `Output/photos/<stem>/` is unwatched so a RE-publish emits only
incidentally via `rebuild_views()` touching the watched `Output/`. POINT THE
FINAL WHOLE-BRANCH REVIEW AT BOTH.
Reviewer-verified FINE (do not re-litigate): the stopPolling race is not real
(mean 5µs against a 37ms budget, 0/80 violations under load ~280, and the
assertion is not vacuous — an injected 60ms stall breaks it 10/10); fd recycling
cannot make the EBADF assertion lie (0 spurious in 400 reps incl. fd churn, and
it dies if close/cancel/wait is removed); `nonisolated(unsafe)` is safe as used
and the toolchain claim is true (reverting all 8 reproduces both cited errors);
no organically reachable deadlock, and `stop()` blocks its caller 0.48ms worst
case during a 4000-file storm; all 11 directories work; `@unchecked Sendable` is
honest; scope holds; the refresh gate was verified, not rebuilt, and is spec §7
verbatim. It re-ran xcodebuild (SUCCEEDED) and pytest (295/1) itself.

UNBLOCKS TASKS 7-10 (controller experiment, verified before use): the view
tasks' only gate is `xcodebuild build`, which Codex cannot run (sandbox, exit
74) — so as briefed, the implementer of every remaining task would be writing
SwiftUI it cannot compile even once. It CAN type-check the app-target sources
against the built core module, no xcodebuild involved:

  cd $WT && swift build --package-path app/PrintworksCore   # produce the module
  swiftc -typecheck -sdk "$(xcrun --show-sdk-path --sdk macosx)" \
    -target arm64-apple-macosx15.0 -swift-version 6 \
    -I app/PrintworksCore/.build/arm64-apple-macosx/debug/Modules \
    app/RAWdogPrintworks/Sources/*.swift

Clean on the current tree; the flags mirror project.yml (SWIFT_VERSION 6.0,
deploymentTarget macOS 15.0), and it is NOT vacuous — appending a deliberate
`model.nonexistentProperty` to a scratch copy reproduced "error: cannot find
'model' in scope", so it discriminates. Put this in every Tasks 7-10 dispatch.
LIMITS, state them in the dispatch so nobody mistakes it for the real gate: it
type-checks only — no linking, no Info.plist/resource processing, no
`@main`/App lifecycle validation, no SwiftUI runtime behaviour. The controller
still runs the real `xcodebuild` gate, and Task 7's Step 3 manual smoke +
Task 11's visual QA remain the actual done-criteria for view work.

NOTE (brief thinness — affects dispatch composition, not a plan defect):
all 11 briefs are generated. Tasks 8/9/10 are 23/25/24 lines and Task 7 is 58,
versus 131-352 for Tasks 1-6. The view tasks are deliberately terse because the
plan pushes their behaviour into the spec and their gate is `xcodebuild build`
plus Task 11's visual QA, not unit tests. Consequence: their dispatches must
carry more controller-supplied context than Tasks 1-6 did — a pointer to the
spec sections describing the UI (docs/superpowers/specs/2026-08-12-macos-app-
design.md §5-§8), the AppModel surface Task 5 actually produced, and the exact
view files Task 7 left behind. Pointers to files/sections, never pasted text.
