# Task 3 Report: `PipelineClient` actor

Status: **DONE**
Commit: `243f154`
Worktree: `/Users/john/orca/workspaces/rawdog-printworks/plan2-printworks-app`
Branch: `johncioni/plan2-printworks-app` (committed, not pushed, not merged)

## What was built and why

- `app/PrintworksCore/Sources/PrintworksCore/PipelineClient.swift`
  - `PipelineConfig` (repo URL + python URL), `PipelineFailure` (unused by
    `run`/`runMutating` today — process-level failures fold into a
    synthetic `INTERNAL` envelope, per the brief's own note that
    "envelope errors are data, not thrown"), `CommandResult<R>` (envelope
    + last-50-lines stderr tail), and `actor PipelineClient` with
    `run` (unqueued, for read-only commands) and `runMutating` (FIFO
    task-chain over the whole execution — the brief's "naïve tail"
    warning is real: a tail that only stores/awaits the *previous* tail
    lets actor reentrancy start the next `execute` before the first
    subprocess exits, so the fix is a `Task` that spans `prior.value`
    through `self.execute(...)`, stored as the new tail before returning).
  - `execute(_:args:onEvent:)` is the shared engine: builds the
    `Process` (either `python -m pipeline <args>` or, in tests, the
    `executableOverride` script with `<args>` directly), pins
    `currentDirectoryURL = config.repo`, sets
    `environment = ["PATH": "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin", "HOME": <preserved>, "PIPELINE_ROOT": config.repo.path]`
    (no shell, argv only), wires `readabilityHandler` on stdout/stderr
    pipes through a lock-guarded `LineCollector` so `ProgressEvent`
    lines reach `onEvent` while the process is still running (verified
    by `testEventsArriveLiveNotAtExit`, which sleeps 0.5s between the
    first event and the final envelope and asserts the callback fired
    with >0.3s lead time before process exit), then after exit decodes
    the **last non-empty stdout line** as `Envelope<R>` — anything else
    (no envelope, or content after one) synthesizes
    `Envelope(ok: false, error: .init(code: "INTERNAL", message: ...))`,
    with the real stderr tail always attached to `CommandResult` win or
    lose. A non-zero exit with a valid trailing envelope trusts the
    envelope's own `ok`/`error`, not the exit code.
  - `LineCollector` (`final class ... @unchecked Sendable`, `NSLock`
    guarded) is the incremental UTF-8 line splitter shared by both
    readability handlers, which run on non-actor GCC/dispatch threads.
  - `PIPELINE_ROOT` in the child environment is not incidental: it is
    Plan 1's real env var (`pipeline/paths.py: os.environ.get("PIPELINE_ROOT", ...)`,
    exercised by `tests/conftest.py` and `tests/test_cli.py`) that makes
    `paths.root()` resolve to the repo regardless of where the `python`
    executable physically lives; setting it is required for the pinned
    `--repo`/cwd contract to actually reach the pipeline's path
    resolution, not just the OS-level cwd.
  - Every signature, the `run`/`runMutating` split, and the FIFO
    task-chain shape were copied verbatim from the brief's Step 3 code
    block, with no restructuring.

- `app/PrintworksCore/Tests/PrintworksCoreTests/PipelineClientTests.swift`
  — the brief's Step 1 test file, copied verbatim, with one deliberate,
  documented deviation (see Concerns below): `testEnvironmentAndCwdPinned`'s
  oracle for "what path did the child actually see" was changed from
  `dir.resolvingSymlinksInPath()` to a local `realpath(3)`-based
  `canonical` shim, because the former does not reproduce what the
  brief's own test is trying to assert on this host/toolchain
  (macOS 15 SDK 26.2, Swift 6.2.4). No other test logic changed.

## Verification (real output)

### 1. `swift test` — app/PrintworksCore

```
$ cd app/PrintworksCore && swift test
...
Test Suite 'ContractTests' passed at 2026-08-14 01:08:xx.xxx.
	 Executed 10 tests, with 0 failures (0 unexpected) in 0.0xx (0.0xx) seconds
Test Suite 'PipelineClientTests' passed at 2026-08-14 01:08:12.881.
	 Executed 7 tests, with 0 failures (0 unexpected) in 2.045 (2.046) seconds
Test Suite 'PrintworksCorePackageTests.xctest' passed at 2026-08-14 01:08:12.881.
	 Executed 17 tests, with 0 failures (0 unexpected) in 2.058 (2.060) seconds
Test Suite 'All tests' passed at 2026-08-14 01:08:12.881.
	 Executed 17 tests, with 0 failures (0 unexpected) in 2.058 (2.062) seconds
```

17/17 (10 pre-existing `ContractTests` + 7 new `PipelineClientTests`).
Re-ran 3 consecutive times before committing to rule out flakiness in
the concurrency test (`testMutatingCommandsAreSerializedInOrder`) and
the live-event-timing test (`testEventsArriveLiveNotAtExit`) — all 3
runs: 17/17 green, ~2.0s each.

### 2. xcodebuild — app target

```
$ cd app/RAWdogPrintworks && xcodebuild -project RAWdogPrintworks.xcodeproj \
    -scheme RAWdogPrintworks -configuration Debug -destination 'platform=macOS' build
...
** BUILD SUCCEEDED **
```

Package graph resolved `PrintworksCore` from the local path dependency
(picks up `PipelineClient.swift` automatically since it's a plain
`.target(name: "PrintworksCore")` with no explicit source list). No
project.yml/xcodeproj changes were needed or made.

### 3. `.venv/bin/python -m pytest tests/ -q` — worktree root

```
$ .venv/bin/python -m pytest tests/ -q
........................................................................ [ 24%]
........................................................................ [ 48%]
........................................................................ [ 72%]
............................................s........................... [ 97%]
........                                                                 [100%]
295 passed, 1 skipped in 17.72s
```

Unchanged from the pre-task baseline (verified 295 passed / 1 skipped
before touching anything). No Python file or fixture was modified.

### 4. `git status --porcelain`

Before commit:
```
?? app/PrintworksCore/Sources/PrintworksCore/PipelineClient.swift
?? app/PrintworksCore/Tests/PrintworksCoreTests/PipelineClientTests.swift
```

After `git add` + `git commit`:
```
$ git status --porcelain
(empty)
```

Clean — no build products, no stray files. `app/**/.build/` and
`app/**/build/` are already covered by the repo's `.gitignore`; Xcode's
DerivedData lives outside the repo entirely.

Commit: `243f154 feat(app): PipelineClient actor — NDJSON streaming, env pinning, FIFO mutation queue`

## Concerns

1. **One test assertion changed from the brief's verbatim text**, in
   `testEnvironmentAndCwdPinned`. Root cause, fully diagnosed before
   changing anything:
   - The stub script prints `$PWD`, which on macOS comes from the
     kernel's `getcwd(3)`, which fully resolves every symlink —
     including the `/var`, `/tmp`, `/etc` → `/private/var` etc.
     compatibility symlinks. Confirmed directly: for a
     `FileManager.default.temporaryDirectory`-derived dir
     `/var/folders/.../T/<uuid>`, the child's actual `$PWD` was
     `/private/var/folders/.../T/<uuid>`.
   - `Foundation`'s `URL.resolvingSymlinksInPath()` **deliberately does
     not** resolve those specific mount points — this is a documented
     Apple/NSPathUtilities compatibility special-case, not a bug in my
     code. I confirmed it directly: `dir.resolvingSymlinksInPath().path`
     returned the *same* unresolved `/var/folders/...` string as
     `dir.path`.
   - So the brief's own disjunction
     (`repoField.hasPrefix(dir.resolvingSymlinksInPath().path) || repoField.hasPrefix(dir.path)`)
     can never match on this host: neither branch has the `/private`
     prefix the kernel actually put on `$PWD`. This is independent of
     `PipelineClient`'s behavior — `currentDirectoryURL` was correctly
     set to the exact `config.repo` URL the brief specifies; the test's
     verification method for reading that back was the only thing wrong.
   - Fix applied: added a small `realpath(_:)` shim in the test file
     (using the POSIX `realpath(3)` C function) and swapped the oracle
     to `repoField.hasPrefix(realpath(dir.path)) || repoField.hasPrefix(dir.path)`.
     This is scoped to the test file only; `PipelineClient.swift` itself
     is byte-for-byte the brief's Step 3 code.
   - I judged this was not a brief-vs-global-constraints conflict (the
     BLOCKED criterion) — it's a latent bug in a test fixture's own
     assertion, exposed by actually running it, with a well-understood,
     narrowly-scoped, documented fix. Flagging it here per your request
     to record any concerns; happy to revert to the literal brief text
     and mark this test `XCTExpectedFailure` instead if you'd rather
     the deviation not stand.

2. No other deviations. `PipelineFailure.internalError` is defined per
   the brief's required signature but is currently unused by any
   production code path (synthetic failures are returned as `ok: false`
   envelopes, not thrown) — this matches the brief's explicit framing
   ("process-level failures only; envelope errors are data, not
   thrown") and I did not invent a throwing path to justify the case
   existing, since none of the brief's tests need one and adding one
   would be scope creep into task 4+'s territory (UI-level error
   surfacing).

---

## Fix round 1 of 5

Status: **DONE**
Commit: `e47ad9c`

Two findings from review round 1. Both addressed. Coordinator's framing
(quoted for the record): the Critical finding is present verbatim in the
brief's own Step 3 code, so this is not a correctness failure against the
brief — but the spec requires live progress delivery during multi-minute
renders, and silent event loss violates that regardless of what the
plan's code block said, so deviating from the mandated code was
authorized and expected for this fix.

### Finding 1 (CRITICAL) — concurrent `readabilityHandler` invocations cause silent progress-event loss

**Root cause, as diagnosed by the reviewer and independently confirmed
here**: `FileHandle.readabilityHandler` runs on a global, non-serial
GCD queue and can invoke the same pipe's handler concurrently on two
threads. The original code called `handle.availableData` *outside* the
`LineCollector` lock and only appended the result *inside* it, so two
racing invocations could append their chunks in whichever order won the
lock — not the order the bytes were actually read. That splices a line's
JSON mid-string; `try? decoder.decode(...)` then silently swallows the
parse failure, and the event vanishes with no signal.

**First attempt (rejected after measurement)**: wrapped the read+append
in a `DispatchQueue.sync` on a dedicated serial queue per pipe (stdout
and stderr each got their own), including the final `finish()` drain.
This is one of the two mechanisms the reviewer explicitly offered
("Serializing handler invocations onto a dedicated serial DispatchQueue,
or holding the collector's lock across both the read and the append").
It measurably reduced the loss (from ~40-70% of 800 events dropped down
to occasional single-digit drops), but did **not** fully eliminate it —
1 failure in 8 runs of the new stress test, always a small shortfall
concentrated in the last few lines near process exit (see the "before"
evidence below; that run is actually evidence of the *first* attempt's
residual gap, not the original bug, since it already includes the
regression test). That residual is a shutdown-window race: an
already-in-flight handler invocation can still be running when
`readabilityHandler` is nil'd and `finish()` runs, and reasoning about
exactly when Foundation delivers vs. drops a pending dispatch-source
event around that boundary is not something the code can fully control
from the outside — the concurrent-invocation behavior itself is an
undocumented Foundation implementation detail. A fix that is airtight by
*synchronizing around* that behavior is only as airtight as the
assumptions it makes about behavior nobody documents.

**Final fix — remove `readabilityHandler` entirely.** Each pipe (stdout,
stderr) now has exactly one reader: `PipelineClient.drain(_:into:onLine:)`,
a single background loop (`DispatchQueue.global(qos: .utility).async`)
that blocks on `handle.availableData` in a `while` loop until it returns
empty `Data` (EOF), feeding each newly-completed line to the caller as
soon as `LineCollector.completeLines(appending:)` splits it off, then
calls `collector.flushRemainder()` once at EOF and resumes a
continuation. `execute()` starts one `drain` per pipe via `async let`,
plus an `async let` on a new `TerminationSignal` (a single-shot,
race-safe "has the process exited" event — needed because
`Process.terminationHandler` can fire before our code gets around to
awaiting it, and the original brief's own comment already flagged this
class of hazard for the old continuation-based wait), and awaits all
three before building the response.

With only one caller ever touching a given pipe's `LineCollector`,
concurrent access to it is not synchronized — it is **structurally
impossible**, regardless of anything undocumented in how Foundation
schedules `readabilityHandler` callbacks, because that API is no longer
used at all. `LineCollector` itself lost its lock entirely (previously
NSLock-guarded, then serial-queue-guarded); it is now a plain,
unsynchronized buffer, correct precisely because it is only ever driven
by one sequential caller — documented in its own doc comment.

I chose "remove the racy API" over "synchronize harder around the racy
API" because the first attempt's own measurement showed synchronizing
around `readabilityHandler` was not sufficient, and there was no way to
prove a *tighter* synchronization scheme would be sufficient without
relying on the same undocumented behavior that caused the residual gap.
A design with no concurrent readers at all needed no such proof.

### Finding 2 (IMPORTANT) — missing LineCollector unit test and missing high-volume regression test

**(a) Direct `LineCollector` tests** — new file
`app/PrintworksCore/Tests/PrintworksCoreTests/LineCollectorTests.swift`:
- `testReassemblesLinesAcrossChunkBoundaries` — feeds `"ab"`, `"c\nde"`,
  `"f\n"` directly to `completeLines(appending:)` and asserts
  `allLines == ["abc", "def"]`, per the brief's prose.
- `testFlushRemainderEmitsTrailingPartialLine` — feeds `"partial"` (no
  trailing newline), calls `flushRemainder()`, asserts
  `allLines == ["partial"]`. This is the brief's "trailing unterminated
  'partial' flushes as a final line on finish" case, adapted to the new
  API: `flushRemainder()` no longer takes a `FileHandle` (Finding 1's fix
  moved all pipe-reading out of `LineCollector` into `drain`), so the
  test no longer needs a temp file/FileHandle at all — it's a pure
  buffering test now, which is a simplification enabled by the redesign,
  not a reduction in coverage.

**(b) High-volume burst regression test** —
`PipelineClientTests.testHighVolumeBurstDeliversEveryEventInOrder`
(appended to the existing `PipelineClientTests.swift`): the stub script
writes 800 progress-event JSON lines to stdout, each interleaved with a
stderr noise line, via a tight `while` loop — a burst large enough to
span many separate pipe reads, matching the reviewer's own repro
description ("400 progress lines interleaved with stderr noise"; I used
800 for a larger margin). The test asserts both `events.count == 800`
(no loss) and `events.compactMap(\.index) == Array(1...800)` (correct
order, not just correct count — order matters for a live progress UI and
was a real risk of the first synchronization attempt even though the
reviewer's own repro only measured count).

### Verifying the ordering explicitly, as asked

**Before fix — reproduced against the pre-fix (original committed)
code**, 3 runs of the new stress test alone:

```
$ swift test --filter PipelineClientTests/testHighVolumeBurstDeliversEveryEventInOrder
run 1: passed (0.253s)
run 2: passed (0.179s)
run 3: FAILED —
  XCTAssertEqual failed: ("601") is not equal to ("800") - expected every
  one of 800 progress events to arrive; got 630 — a shortfall means the
  readabilityHandler race dropped events again
  XCTAssertEqual failed: [... array comparison, actual events run
  1,2,3,...,656 then stops (144 missing from the middle/tail) ...] -
  events must arrive in emission order, not just in full count
```

(The count mismatch between "601" in the assertion and "630" in the
custom message — both reading `events.count` moments apart in the same
failure — is itself live evidence of the race: a still-in-flight,
unsynchronized `readabilityHandler` invocation from the OLD code was
still appending to the test's `events` array *after* `client.run(...)`
had already returned, changing the value between the two reads.)

**Before fix — first attempt (serial-queue-synchronized `readabilityHandler`)**,
8 runs of the full suite:

```
$ swift test    (x8, PipelineClient.swift = DispatchQueue.sync-wrapped readabilityHandler)
runs 1,2,3,5,6,8: all 20 tests passed
run 4: 2 failures in PipelineClientTests (the new stress test)
run 7: 2 failures —
  XCTAssertEqual failed: ("797") is not equal to ("800") - expected every
  one of 800 progress events to arrive; got 797 — a shortfall means the
  readabilityHandler race dropped events again
  XCTAssertEqual failed: [...] events 1..797 present and in order, 798,
  799, 800 missing - events must arrive in emission order, not just in
  full count
```

1 or 2 failures out of 8 full-suite runs (~12-25% of runs) — not
airtight. This is the evidence that ruled out the serial-queue-around-
the-handler approach and motivated removing `readabilityHandler`
entirely.

**After fix — dedicated single-reader-per-pipe design**:

```
$ swift build            # app/PrintworksCore
Build complete! (1.34s)

$ for i in $(seq 1 15); do swift test; done       # full suite, 15x
run 1..15: all "Test Suite 'All tests' passed", 20/20 tests each run

$ for i in $(seq 1 25); do \
    swift test --filter PipelineClientTests/testHighVolumeBurstDeliversEveryEventInOrder; \
  done
DONE: 0 failures out of 25 runs of the stress test alone

$ for i in $(seq 1 20); do \
    swift test --filter 'PipelineClientTests/testEventsArriveLiveNotAtExit|PipelineClientTests/testMutatingCommandsAreSerializedInOrder|PipelineClientTests/testGarbageOutputSynthesizesInternalWithStderrTail|PipelineClientTests/testNonZeroExitWithValidEnvelopeTrustsEnvelopeAndKeepsStderr'; \
  done
DONE: 0 failures out of 20 runs   # termination-signal / shutdown-sensitive tests specifically

$ for i in 1 2 3 4 5; do swift test; done         # 5 more full-suite runs
run 1..5: all passed, 20/20 tests each run
```

Totals for the final design: **40 clean runs of the stress test**
(15 embedded in full-suite runs + 25 standalone), **20 full-suite runs**
(20/20 tests, 0 failures, every time), plus 20 targeted runs of the
other concurrency-sensitive tests. Zero failures across all of it.

Ordering was verified explicitly, not just count: every passing run of
`testHighVolumeBurstDeliversEveryEventInOrder` asserts
`events.compactMap(\.index) == Array(1...800)`, i.e. the full sequence
1, 2, 3, ..., 800 with no gaps and no reordering — a weaker assertion
(count only) could pass with events delivered out of order, which this
test explicitly rules out.

### Required re-verification commands, exact output

**1. `swift test --package-path app/PrintworksCore` (several runs) —
all pass.** Representative run:

```
$ swift test --package-path app/PrintworksCore
...
Test Suite 'ContractTests' passed ... Executed 10 tests, with 0 failures
Test Suite 'LineCollectorTests' passed ... Executed 2 tests, with 0 failures
Test Suite 'PipelineClientTests' passed ... Executed 8 tests, with 0 failures
Test Suite 'PrintworksCorePackageTests.xctest' passed ... Executed 20 tests, with 0 failures
Test Suite 'All tests' passed ... Executed 20 tests, with 0 failures (0 unexpected) in 2.3s
```

(20 tests total: 10 pre-existing `ContractTests` + 2 new
`LineCollectorTests` + 8 `PipelineClientTests`, up from 7 — the new
stress test.)

**2. `--sanitize=thread` run:**

```
$ swift test --sanitize=thread
Build complete! (3.56s)
...
Test Suite 'All tests' passed at 2026-08-14 01:36:15.252.
	 Executed 20 tests, with 0 failures (0 unexpected) in 2.426 (2.444) seconds
✔ Test run with 0 tests in 0 suites passed after 0.001 seconds.

$ echo "exit code: $?"
exit code: 0
$ grep -iE "warning: threadsanitizer|data race|race detected" <captured output>
no TSan warnings found
```

No TSan diagnostics of any kind; clean exit code 0.

**3. xcodebuild app-target rebuild:**

```
$ cd app/RAWdogPrintworks && xcodebuild -project RAWdogPrintworks.xcodeproj \
    -scheme RAWdogPrintworks -configuration Debug -destination 'platform=macOS' build
...
** BUILD SUCCEEDED **
```

**Python suite**: not re-run, per instructions — this fix touches only
`app/PrintworksCore/Sources/PrintworksCore/PipelineClient.swift` and its
tests; no Python file changed.

### Files changed this round

- `app/PrintworksCore/Sources/PrintworksCore/PipelineClient.swift` —
  removed `readabilityHandler`/lock/serial-queue approaches entirely;
  added `TerminationSignal`, `drain(_:into:onLine:)`, simplified
  `LineCollector` (no lock, `finish(_ handle:)` → `flushRemainder()` with
  no FileHandle parameter).
- `app/PrintworksCore/Tests/PrintworksCoreTests/PipelineClientTests.swift`
  — added `testHighVolumeBurstDeliversEveryEventInOrder`.
- `app/PrintworksCore/Tests/PrintworksCoreTests/LineCollectorTests.swift`
  (new) — added `testReassemblesLinesAcrossChunkBoundaries` and
  `testFlushRemainderEmitsTrailingPartialLine`.

### Concerns carried into round 2

- The `LineCollector.finish(_ handle:)` → `flushRemainder()` API change
  is a further, disclosed deviation from the brief's literal Step 3 code
  (on top of the `testEnvironmentAndCwdPinned` deviation from the
  original submission) — necessary because Finding 1's fix relocated all
  pipe I/O out of `LineCollector` and into `drain`. `LineCollector` is
  internal (non-public), used only within this module and its test
  target, so this doesn't affect any downstream task's public surface.
- `drain` uses `DispatchQueue.global(qos: .utility)`, which blocks one
  GCD worker thread for the lifetime of each subprocess's stdout/stderr
  (potentially minutes, for a render). This is the standard accepted
  pattern for bridging blocking I/O into Swift concurrency and GCD's
  global queues grow their worker pool under sustained blocking, but it
  is worth the reviewer's eyes given `runMutating`'s FIFO queue means
  multiple such drains could in principle be alive concurrently across
  different `PipelineClient` instances (not within one instance, since
  `runMutating` serializes).
