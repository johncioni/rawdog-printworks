### Task 1: Scaffold — PrintworksCore package + XcodeGen app target

**Files:**
- Create: `app/PrintworksCore/Package.swift`, `app/PrintworksCore/Sources/PrintworksCore/Contract.swift` (placeholder type only), `app/PrintworksCore/Tests/PrintworksCoreTests/ContractTests.swift` (one trivial test), `app/RAWdogPrintworks/project.yml`, `app/RAWdogPrintworks/Sources/PrintworksApp.swift`, `app/RAWdogPrintworks/Sources/Theme.swift`
- Modify: `.gitignore` (add `app/**/build/`, `app/**/.build/`, `app/**/xcuserdata/`)

**Interfaces:**
- Produces: `Theme` enum consumed by every view task — `Theme.windowBase` (#0A0A0B), `Theme.canvas` (pure black), `Theme.panel` (#141416), `Theme.hairline` (#232326), `Theme.accent` (#E8A849), `Theme.statusPublished` (green), `Theme.statusReview` (= accent), `Theme.statusIngested` (gray).
- Build commands used by every later task (quality gate).

- [ ] **Step 1: Install XcodeGen** — `brew install xcodegen` (verify: `xcodegen --version`).

- [ ] **Step 2: Create the package**

```swift
// app/PrintworksCore/Package.swift
// swift-tools-version:6.0
import PackageDescription

let package = Package(
    name: "PrintworksCore",
    platforms: [.macOS(.v15)],
    products: [.library(name: "PrintworksCore", targets: ["PrintworksCore"])],
    targets: [
        .target(name: "PrintworksCore"),
        .testTarget(name: "PrintworksCoreTests", dependencies: ["PrintworksCore"]),
    ]
)
```

```swift
// Sources/PrintworksCore/Contract.swift (placeholder; Task 2 fills it)
public enum Contract { public static let version = 1 }
```

```swift
// Tests/PrintworksCoreTests/ContractTests.swift
import XCTest
@testable import PrintworksCore

final class ContractTests: XCTestCase {
    func testPackageBuilds() { XCTAssertEqual(Contract.version, 1) }
}
```

Run: `swift test --package-path app/PrintworksCore` → PASS.

- [ ] **Step 3: Create the app target**

```yaml
# app/RAWdogPrintworks/project.yml
name: RAWdogPrintworks
options:
  bundleIdPrefix: com.john
  deploymentTarget:
    macOS: "15.0"
packages:
  PrintworksCore:
    path: ../PrintworksCore
targets:
  RAWdogPrintworks:
    type: application
    platform: macOS
    sources: [Sources]
    dependencies:
      - package: PrintworksCore
    info:
      path: Info.plist
      properties:
        CFBundleDisplayName: RAWdog Printworks
        LSMinimumSystemVersion: "15.0"
        LSApplicationCategoryType: public.app-category.photography
    settings:
      base:
        PRODUCT_BUNDLE_IDENTIFIER: com.john.rawdog-printworks
        CODE_SIGN_IDENTITY: "-"
        SWIFT_VERSION: "6.0"
```

```swift
// app/RAWdogPrintworks/Sources/PrintworksApp.swift
import SwiftUI
import PrintworksCore

@main
struct PrintworksApp: App {
    var body: some Scene {
        WindowGroup {
            Text("RAWdog Printworks")
                .frame(minWidth: 900, minHeight: 600)
                .background(Theme.windowBase)
                .preferredColorScheme(.dark)
        }
    }
}
```

```swift
// app/RAWdogPrintworks/Sources/Theme.swift
import SwiftUI

public enum Theme {
    public static let windowBase = Color(red: 0x0A/255, green: 0x0A/255, blue: 0x0B/255)
    public static let canvas = Color.black
    public static let panel = Color(red: 0x14/255, green: 0x14/255, blue: 0x16/255)
    public static let hairline = Color(red: 0x23/255, green: 0x23/255, blue: 0x26/255)
    public static let accent = Color(red: 0xE8/255, green: 0xA8/255, blue: 0x49/255)
    public static let statusPublished = Color(red: 0x28/255, green: 0xC8/255, blue: 0x40/255)
    public static let statusReview = accent
    public static let statusIngested = Color(red: 0x9A/255, green: 0x9A/255, blue: 0xA0/255)
}
```

- [ ] **Step 4: Generate + build**

```bash
(cd app/RAWdogPrintworks && xcodegen generate)
xcodebuild -project app/RAWdogPrintworks/RAWdogPrintworks.xcodeproj -scheme RAWdogPrintworks build
```

Expected: BUILD SUCCEEDED.

- [ ] **Step 5: Commit** (include the generated `.xcodeproj` — spec §9 commits the project)

```bash
git add app/ .gitignore
git commit -m "feat(app): scaffold PrintworksCore package + RAWdogPrintworks app target"
```

---

