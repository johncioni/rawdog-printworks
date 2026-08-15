# Task 2 report: Contract models + golden-fixture decoding

## What was built and why

Replaced the Task 1 placeholder in `app/PrintworksCore/Sources/PrintworksCore/Contract.swift`
with the full set of `Codable & Sendable & Equatable` model structs the brief's Interfaces
block names, decoding every golden fixture under `tests/fixtures/json_contract/`:

`PipelineErrorInfo`, `Envelope<R>`, `ProgressEvent`, `ToolchainIssue`, `ToolchainStatus`,
`LockStatus`, `Control`, `StyleAdjustments`, `CropWindow`, `PublishedInfo`, `PhotoStatus`,
`StatusSnapshot`, `AdjustResult`, `CropsResult`, `ApproveResult`, `FileNote`, `FileFailure`,
`IngestResult`, `PublishedPhoto`, `AdvancedPhoto`, `StemFailure`, `RunResult`, plus
`ContractDecoder.make()` (a `JSONDecoder` with `keyDecodingStrategy = .convertFromSnakeCase`).
No structs beyond this list were added. The pre-existing `Contract.version = 1` symbol was
kept verbatim alongside the new types (per the task's binding instruction), so the Task 1
`testPackageBuilds` assertion in `ContractTests.swift` still compiles and passes unchanged.

All properties are `let`, no custom `CodingKeys` — snake_case-to-camelCase mapping (e.g.
`review_revision_after` → `reviewRevisionAfter`, `preview_hashes` → `previewHashes`,
`artifact_count` → `artifactCount`) is handled entirely by `ContractDecoder.make()`'s
`convertFromSnakeCase` strategy, matching every fixture's key casing. `previews` and
`previewHashes` are typed `[String: String?]` (JSON `null` map values decode to
`Optional.none` natively). `CropsResult.basis` and `CropWindow.source` are optional per the
brief's explicit note (`basis` is `null` when every window is persisted). `ProgressEvent`
has only `event` required and everything else optional so it decodes both the
`run_stream.ndjson` "stage" lines (`event`, `stage`, `stem` only) and "progress" lines
(`event`, `stage`, `stem`, `index`, `total`, `detail`).

**On the `code` field (the reason a preparatory fixture-update task ran before this one):**
`PipelineErrorInfo.code`, `StemFailure.code`, and `FileFailure.code` are all modeled as plain
`String`, exactly as the brief's Interfaces block literally types them — not as a closed
Swift `enum`. This was a deliberate check against the trap the task's critical context
flagged: `run_partial_failure.json`'s `failed[]` array was updated ahead of this task to
carry two *different* codes (`VERIFY_FAILED` and `RENDER_FAILED`) specifically so that an
implementation which infers a closed enum from the values visible in one fixture would
either miss a case or crash on decode. A plain `String` field decodes any of the ten current
codes (`LOCK_HELD`, `TOOLCHAIN_FAILED`, `RENDER_FAILED`, `VERIFY_FAILED`, `INVALID_STATE`,
`STALE_REVIEW`, `PARTIAL_FAILURE`, `NOT_FOUND`, `BAD_INPUT`, `INTERNAL`) and any future
unrecognised code without throwing, by construction — no custom `Decodable` logic needed.

`ContractTests.swift` was extended (not replaced) with:
1. Every test from the brief's Step 1 code block, used verbatim.
2. `testRunPartialFailureCarriesDistinctFailureCodes` — asserts the fixture's `failed[]`
   set is exactly `{VERIFY_FAILED, RENDER_FAILED}`, pinning the two-different-codes property
   the prep task established.
3. `testAllKnownAndFutureFailureCodesDecode` — round-trips all ten known codes plus one
   synthetic unrecognised code (`SOME_FUTURE_CODE_NOT_YET_INVENTED`) through
   `PipelineErrorInfo`, `StemFailure`, and `FileFailure`, proving the `String` modeling
   handles the full domain and forward-compatibility requirement directly, not just by
   accident of the two values one fixture happens to contain.

The Interfaces block additionally names a `repoFixturesURL()` test helper. The brief's own
Step 1 code (the literal, must-use-verbatim test file content) does not define or call a
function by that name — it inlines the five-`deletingLastPathComponent()` ascent directly
inside a private `fixture(_ name:)` method. No later task brief (checked `task-3-brief.md`
through `task-11-brief.md`) references `repoFixturesURL()` either. Since Step 1's code is
authoritative over the Interfaces block's prose description of the same logic, and using it
verbatim was the explicit instruction, `fixture(_:)` was implemented exactly as given rather
than introducing an additional, unused top-level symbol. Flagged under Concerns below in
case a later task expects that exact free-function name.

## Verifications (run from the worktree root unless noted)

### 1. `swift test` (from `app/PrintworksCore`)

```
$ cd app/PrintworksCore && swift test
Building for debugging...
Build complete! (3.01s)
Test Suite 'All tests' started at 2026-08-14 00:52:47.131.
Test Case '-[PrintworksCoreTests.ContractTests testAdjustStreamFixtureDecodesLineByLine]' passed (0.005 seconds).
Test Case '-[PrintworksCoreTests.ContractTests testAllKnownAndFutureFailureCodesDecode]' passed (0.001 seconds).
Test Case '-[PrintworksCoreTests.ContractTests testDecodesAdjustCropsApproveIngestRun]' passed (0.003 seconds).
Test Case '-[PrintworksCoreTests.ContractTests testDecodesEveryStatusFixture]' passed (0.003 seconds).
Test Case '-[PrintworksCoreTests.ContractTests testErrorEnvelopeDecodes]' passed (0.001 seconds).
Test Case '-[PrintworksCoreTests.ContractTests testPackageBuilds]' passed (0.000 seconds).
Test Case '-[PrintworksCoreTests.ContractTests testRunPartialFailureCarriesDistinctFailureCodes]' passed (0.000 seconds).
Test Case '-[PrintworksCoreTests.ContractTests testRunStreamFixtureIsTheStreamingContract]' passed (0.001 seconds).
Test Case '-[PrintworksCoreTests.ContractTests testStaleReviewFixture]' passed (0.001 seconds).
Test Case '-[PrintworksCoreTests.ContractTests testStatusFieldsRoundTrip]' passed (0.000 seconds).
Test Suite 'ContractTests' passed at 2026-08-14 00:52:47.150.
	 Executed 10 tests, with 0 failures (0 unexpected) in 0.015 (0.016) seconds
Test Suite 'All tests' passed at 2026-08-14 00:52:47.150.
	 Executed 10 tests, with 0 failures (0 unexpected) in 0.015 (0.020) seconds
```

PASS — 10/10 tests (1 pre-existing `Contract.version` test + 6 fixture-decoding tests from
the brief's Step 1 + 3 added for the failure-code domain requirement).

Also ran `swift build` alone and grepped for `warning`/`error` in its output — zero matches,
confirming the new module compiles cleanly with no compiler warnings.

### 2. `xcodebuild` of the app target (same command as Task 1's report)

```
$ xcodebuild -project app/RAWdogPrintworks/RAWdogPrintworks.xcodeproj -scheme RAWdogPrintworks build
... (SwiftDriver compile of PrintworksCore + RAWdogPrintworks; PrintworksCore package
resolved and linked; CodeSign with ad-hoc identity "Sign to Run Locally";
ExtractAppIntentsMetadata; RegisterWithLaunchServices) ...
2026-08-14 00:53:06.566 appintentsmetadataprocessor[91972:6111220] warning: Metadata extraction skipped. No AppIntents.framework dependency found.
** BUILD SUCCEEDED **
```

PASS. The one `warning:` line is the same benign, expected AppIntents-metadata line Task 1's
report already documented (this app doesn't use AppIntents) — not a regression, not related
to this task's changes.

### 3. Python quality gate (from the worktree root) — must remain unchanged

```
$ .venv/bin/python -m pytest tests/ -q
........................................................................ [ 24%]
........................................................................ [ 48%]
........................................................................ [ 72%]
............................................s........................... [ 97%]
........                                                                 [100%]
295 passed, 1 skipped in 17.36s
```

PASS — identical to Task 1's baseline (295 passed, 1 skipped). No file under `tests/` or
`pipeline/` was touched; confirmed by `git status`/`git diff` scope below.

### 4. `git status --porcelain` — clean

Before commit (only the two intended files touched):
```
$ git status --porcelain
 M app/PrintworksCore/Sources/PrintworksCore/Contract.swift
 M app/PrintworksCore/Tests/PrintworksCoreTests/ContractTests.swift
```

After commit:
```
$ git status --porcelain
(empty)
```

No `.build/`, no `xcuserdata/`, no DerivedData, no fixture or Python files staged — matches
Task 1's `.gitignore` coverage (`app/**/.build/`).

## Commit

```
3378ea9 feat(app): contract models decoding the pipeline golden fixtures
```
2 files changed, 300 insertions(+) (`Contract.swift`, `ContractTests.swift`).

## Concerns

- **`repoFixturesURL()` naming** (non-blocking): the Interfaces block names a test helper
  `repoFixturesURL()`, but the brief's own verbatim Step 1 code inlines that exact logic
  inside a private `fixture(_ name:)` method instead of a function with that name. I followed
  the literal, must-use-verbatim Step 1 code (also matching what actually runs and passes) over
  the Interfaces block's prose alias, and confirmed no later task brief (3 through 11)
  references `repoFixturesURL()`. If a later task turns out to expect that exact free-function
  symbol for its own fixture-based tests, it's a small, low-risk addition at that point.
- No other concerns. All four requested verifications pass with real, unedited output as
  recorded above; no fixture, Python, or non-`app/PrintworksCore` file was modified.
