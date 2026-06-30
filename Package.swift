// swift-tools-version: 5.9
// Pure SwiftPM build for WebHarvest — no Xcode project required.
// Build:   swift build -c release
// Run:     swift build -c release && open .build/arm64-apple-macosx/release/WebHarvest
// Why SwiftPM and not Xcode? Two reasons:
//   1. CLI-only build works on any Mac with Command Line Tools (~700 MB vs 12 GB Xcode).
//   2. CI-friendly: GitHub Actions / any automation can run `swift build` directly.

import PackageDescription

let package = Package(
    name: "WebHarvest",
    platforms: [
        .macOS(.v14)
    ],
    products: [
        .executable(name: "WebHarvest", targets: ["WebHarvest"])
    ],
    targets: [
        .executableTarget(
            name: "WebHarvest",
            path: "SwiftApp/Sources",
            exclude: ["Info.plist", "README.md"],
            linkerSettings: [
                .linkedFramework("AppKit"),
                .linkedFramework("SwiftUI"),
                .linkedFramework("Foundation")
            ],
            swiftSettings: [
                .unsafeFlags(["-parse-as-library"])
            ]
        )
    ]
)
