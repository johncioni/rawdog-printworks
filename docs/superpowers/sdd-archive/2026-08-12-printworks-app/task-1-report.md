# Task 1 Report: Scaffold — PrintworksCore package + XcodeGen app target

Status: **DONE**

Worktree: `/Users/john/orca/workspaces/rawdog-printworks/plan2-printworks-app`
Branch: `johncioni/plan2-printworks-app`
Commit: `0bff85db0691d38a1b940b66d041f2c758b5995e`

## What was created and why

Per `.superpowers/sdd/2026-08-12-printworks-app/task-1-brief.md`, created the two-part
scaffold every later task builds on: a standalone Swift package (`PrintworksCore`, the
future home of the JSON-contract client / process wrapper logic) and a SwiftUI app
target (`RAWdogPrintworks`) generated via XcodeGen from a checked-in `project.yml`.

Per the path convention ruled on before this task (bare `Sources/PrintworksCore/...`
and `Tests/PrintworksCoreTests/...` in later briefs are relative to `app/PrintworksCore/`;
app-target sources live under `app/RAWdogPrintworks/Sources/`), the following layout
was created, with every file's content taken verbatim from the brief:

- `app/PrintworksCore/Package.swift` — SwiftPM manifest, macOS 15 min, library product
  `PrintworksCore`, one library target + one test target.
- `app/PrintworksCore/Sources/PrintworksCore/Contract.swift` — placeholder
  `public enum Contract { public static let version = 1 }` (Task 2 fills this in).
- `app/PrintworksCore/Tests/PrintworksCoreTests/ContractTests.swift` — one trivial
  `XCTest` asserting `Contract.version == 1`.
- `app/RAWdogPrintworks/project.yml` — XcodeGen spec: macOS 15 deployment target,
  bundle id `com.john.rawdog-printworks`, links the local `PrintworksCore` package by
  relative path (`../PrintworksCore`), ad-hoc code signing (`CODE_SIGN_IDENTITY: "-"`),
  Swift 6.
- `app/RAWdogPrintworks/Sources/PrintworksApp.swift` — `@main` `App` with a
  placeholder `WindowGroup` (900x600 min, dark scheme, `Theme.windowBase` background).
- `app/RAWdogPrintworks/Sources/Theme.swift` — the `Theme` enum with all eight
  color constants specified in the brief's Interfaces section (`windowBase`, `canvas`,
  `panel`, `hairline`, `accent`, `statusPublished`, `statusReview = accent`,
  `statusIngested`), which every later view task consumes.
- `.gitignore` — appended exactly the three patterns the brief specifies:
  `app/**/build/`, `app/**/.build/`, `app/**/xcuserdata/`.

XcodeGen (2.46.0) was not installed on this machine; installed it via
`brew install xcodegen` as explicitly authorized by the task instructions. Ran
`xcodegen generate` inside `app/RAWdogPrintworks/`, which produced
`RAWdogPrintworks.xcodeproj` (committed per brief Step 5 / spec §9, which commits the
generated project) plus a generated `Info.plist` (referenced by `project.yml`'s
`info.path`, required for the pbxproj to resolve).

No Python files were touched. No repo writes occurred outside `app/` and `.gitignore`.

## Verification — exact commands and real output

### 1. `swift test` from `app/PrintworksCore`

```
$ cd app/PrintworksCore && swift test
Building for debugging...
[6/9] Compiling PrintworksCore Contract.swift
[7/9] Emitting module PrintworksCore
...
Build complete! (23.15s)
Test Suite 'All tests' started at 2026-08-14 00:41:08.649.
Test Suite 'PrintworksCorePackageTests.xctest' started at 2026-08-14 00:41:08.650.
Test Suite 'ContractTests' started at 2026-08-14 00:41:08.650.
Test Case '-[PrintworksCoreTests.ContractTests testPackageBuilds]' started.
Test Case '-[PrintworksCoreTests.ContractTests testPackageBuilds]' passed (0.001 seconds).
Test Suite 'ContractTests' passed at 2026-08-14 00:41:08.652.
	 Executed 1 test, with 0 failures (0 unexpected) in 0.001 (0.002) seconds
Test Suite 'PrintworksCorePackageTests.xctest' passed at 2026-08-14 00:41:08.652.
	 Executed 1 test, with 0 failures (0 unexpected) in 0.001 (0.002) seconds
Test Suite 'All tests' passed at 2026-08-14 00:41:08.652.
	 Executed 1 test, with 0 failures (0 unexpected) in 0.001 (0.003) seconds
✔ Test run with 0 tests in 0 suites passed after 0.001 seconds.
```

PASS — 1/1 test.

### 2. XcodeGen generate + xcodebuild (brief Step 4)

```
$ cd app/RAWdogPrintworks && xcodegen generate
⚙️  Generating plists...
⚙️  Generating project...
⚙️  Writing project...
Created project at /Users/john/orca/workspaces/rawdog-printworks/plan2-printworks-app/app/RAWdogPrintworks/RAWdogPrintworks.xcodeproj

$ xcodebuild -project app/RAWdogPrintworks/RAWdogPrintworks.xcodeproj -scheme RAWdogPrintworks build
... (SwiftDriver compile of PrintworksApp.swift, Theme.swift; PrintworksCore package
resolved and linked; CodeSign with ad-hoc identity "Sign to Run Locally";
RegisterExecutionPolicyException; Validate) ...
** BUILD SUCCEEDED **
```

0 compiler errors, 0 compiler warnings. The build log contains exactly one line
matching `warning:`, and it is a benign informational line from Xcode's App Intents
metadata processor (`appintentsmetadataprocessor: warning: Metadata extraction
skipped. No AppIntents.framework dependency found.`) — expected since this app does
not use AppIntents, not a code or config defect.

Also ran `xcodegen --version` → `Version: 2.46.0`.

### 3. Python quality gate — must remain untouched

Before any change (baseline):
```
$ .venv/bin/python -m pytest tests/ -q
........................................................................ [ 24%]
........................................................................ [ 48%]
........................................................................ [ 72%]
............................................s........................... [ 97%]
........                                                                 [100%]
295 passed, 1 skipped in 17.35s
```

After the commit:
```
$ .venv/bin/python -m pytest tests/ -q
........................................................................ [ 24%]
........................................................................ [ 48%]
........................................................................ [ 72%]
............................................s........................... [ 97%]
........                                                                 [100%]
295 passed, 1 skipped in 19.35s
```

Identical: 295 passed, 1 skipped, both before and after. No Python file was modified
(confirmed by `git status`/`git diff` scope — only `app/**` and `.gitignore` changed).

### 4. `git status --porcelain` — no build products / generated artifacts committed

Preview of what `git add app/ .gitignore` staged (`git add -n`):
```
add '.gitignore'
add 'app/PrintworksCore/Package.swift'
add 'app/PrintworksCore/Sources/PrintworksCore/Contract.swift'
add 'app/PrintworksCore/Tests/PrintworksCoreTests/ContractTests.swift'
add 'app/RAWdogPrintworks/Info.plist'
add 'app/RAWdogPrintworks/RAWdogPrintworks.xcodeproj/project.pbxproj'
add 'app/RAWdogPrintworks/RAWdogPrintworks.xcodeproj/project.xcworkspace/contents.xcworkspacedata'
add 'app/RAWdogPrintworks/Sources/PrintworksApp.swift'
add 'app/RAWdogPrintworks/Sources/Theme.swift'
add 'app/RAWdogPrintworks/project.yml'
```

10 files — exactly the source/config files plus the generated `.xcodeproj`
(intentionally committed per brief Step 5 / spec §9). No `.build/`, no `build/`, no
`xcuserdata/`, no DerivedData (DerivedData lives outside the repo, at
`~/Library/Developer/Xcode/DerivedData/`, untouched by git regardless).

After commit:
```
$ git status --porcelain
(empty)
```

Confirmed via `git check-ignore -v app/PrintworksCore/.build` that the new
`.gitignore` pattern `app/**/.build/` matches and ignores the local SwiftPM build
directory created by `swift test`. (A `.swiftpm/xcode/` directory was also created by
SwiftPM tooling but contains zero files — Git does not track empty directories, so no
gitignore entry was needed for it, and none was added since it's outside the brief's
verbatim instructions.)

## Commit

```
0bff85db0691d38a1b940b66d041f2c758b5995e feat(app): scaffold PrintworksCore package + RAWdogPrintworks app target
```
10 files changed, 436 insertions(+).

## Concerns

- None blocking. The single `appintentsmetadataprocessor` warning line noted above is
  expected/benign and not something later tasks need to address — it will keep
  appearing on every `xcodebuild` build of this target until/unless AppIntents is
  adopted, and is not a code defect.
- XcodeGen was not previously installed on this machine; it is now present at
  `/opt/homebrew/bin/xcodegen` (Homebrew), version 2.46.0. Any other machine/CI
  running this project's build will need the same `brew install xcodegen` step (this
  matches the brief's Step 1, which was already an explicit prerequisite of the plan).
