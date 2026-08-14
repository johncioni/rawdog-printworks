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
