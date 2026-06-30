// swift-tools-version: 5.9
// Pure SwiftPM build for WebHarvest — no Xcode project required.

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
            exclude: [
                "Info.plist",
                "README.md",
                "App/README.md",
                "Bridge/README.md",
                "Components/README.md",
                "Modules/README.md",
                "Modules/SiteCrawler/README.md"
            ],
            swiftSettings: [
                .unsafeFlags(["-parse-as-library"])
            ]
        )
    ]
)
