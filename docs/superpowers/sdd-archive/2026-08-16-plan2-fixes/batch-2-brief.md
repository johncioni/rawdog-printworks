# Batch 2 — tests that cannot fail

Read `README.md` in this directory first; its scope contract binds this brief.

CodeRabbit found six tests that are flaky, vacuous, or assert the wrong thing.
This repo has already shipped **three** such tests, caught by hand across Tasks
6, 9 and 11 — it is the recurring failure mode here, which is why this batch
exists as its own unit of work rather than as cleanup.

## The acceptance criterion for this batch

For **every** test you touch, demonstrate the repaired test **fails against
broken code**: mutate the implementation it covers, capture the RED, restore the
implementation, capture the GREEN. A repaired test you cannot make fail is not
repaired.

Record each mutation verbatim in your report — the exact edit and the failing
assertion. The controller re-runs them independently and will reject the batch if
a mutation does not produce the failure you claim.

## Items

### 1. `DebouncerTests.swift:12-19` (Major) — a real data race, and flaky timing

`nonisolated(unsafe) var fired` is written from the debounced action and read
from the test body with no synchronization — a genuine race, not a theoretical
one, and the timing assumption makes the test flaky under load.

Fix the race properly (an actor, a lock, or a `@Sendable` box — your call), and
make the wait condition event-driven rather than a fixed sleep.

### 2. `DebouncerTests.swift:31-43` (Major) — does not exercise cancellation

`testScheduledActionDoesNotRunInCancelledTask` never actually cancels anything,
so it passes whether or not `Debouncer` honours cancellation. Rewrite it to
cancel a genuinely in-flight scheduled action and assert the action did not run.

This one is the clearest "cannot fail" case in the report — the mutation
demonstration matters most here.

### 3. `LineCollectorTests.swift:10-16` (Major) — asserts the wrong surface

The tests check only the accumulated `allLines` and never the **return value** of
`completeLines(appending:)`, which is what `PipelineClient` actually consumes.
Assert the return value.

### 4. `PipelineClient.swift:296-305` (Major) — and its missing test

This is the code half of the same finding, and the review's F10.

`buffer += String(decoding: data, as: UTF8.self)` decodes each `availableData`
chunk independently, so a multi-byte UTF-8 sequence straddling a chunk boundary
becomes U+FFFD. Envelopes and events are unaffected — `pipeline/jsonio.py:59`
uses `json.dumps` defaults, i.e. `ensure_ascii=True`, so stdout is pure ASCII —
but the stderr tail shown in "Show Details" is corrupted.

**Fix:** buffer raw bytes in `Data` and split on the `0x0A` byte, decoding to
`String` only once a complete line is in hand.

**Test:** feed a multi-byte character split across two chunks —
`Array("é".utf8)` divided between calls — and assert the reassembled line is
`"é"`, not a replacement character. This test must fail against the current
implementation; that is your RED.

### 5. `RepoWatcherTests.swift:33-39` (Minor) — a teardown assertion that cannot fail

Same species as the three already found. Remove it or move the cleanup so the
assertion is actually load-bearing; say which and why.

### 6. `RepoWatcherTests.swift:102-113` (Minor) — absence assertion sensitive to scheduler stalls

An "X did not happen" assertion that can pass simply because the runtime was
slow. Make it deterministic — wait for a positive signal that proves the window
elapsed, then assert the absence.

### 7. `RepoWatcherTests.swift:293-297` (Minor) — asserts on a closed descriptor number

Three sites assert via `fcntl`/`errno` on a **closed** fd number. After `close`,
the kernel can reassign that number to the next file the process opens — XCTest
and FileManager both open files during a run — so the assertion can fail for
reasons unrelated to the watcher, and can pass spuriously too.

CodeRabbit's guidance, which is sound: at `:293-297` drop the `fcntl`/`errno`
loop because `XCTAssertTrue(watcher.openFileDescriptors.isEmpty)` at `:298`
already proves the property; at `:328-330` change the `waitUntil` condition to
`watcher.openFileDescriptors.isEmpty`; at `:422` remove the `fcntl` assertion
since the `waitUntil` at `:418-421` already proves it.

## Out of scope in this batch

Do not "improve" other tests you pass through. In particular
`AppModelTests.swift:41-47`, `ContractTests.swift:92-102` and
`PipelineClientTests.swift:152-160` are CR **Trivials** and are explicitly out —
see `README.md`.

## Gates and reporting

```bash
swift build --disable-sandbox --package-path app/PrintworksCore
swift test  --disable-sandbox --package-path app/PrintworksCore
xcodebuild -project app/RAWdogPrintworks/RAWdogPrintworks.xcodeproj \
  -scheme RAWdogPrintworks -configuration Release \
  OTHER_SWIFT_FLAGS='$(inherited) -disable-sandbox' build
.venv/bin/python -m pytest tests/ -q
```

Both `-disable-sandbox` flags are required under your sandbox; `sandbox_apply` /
"Operation not permitted" / "malformed response" are sandbox artifacts, not
compile errors.

Run `swift test` several times — two of these fixes are specifically about
flakiness, and a single green run does not demonstrate a stable test.

Write `batch-2-report.md` in this ledger directory, with the mutation evidence
per item. **Do not commit** — the controller commits after re-running your
mutations. Your report IS your checkpoint: if a stop hook asks for a `HANDOFF.md`
refresh, run `git checkout -- HANDOFF.md` and point it at your report.
