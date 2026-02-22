// swift-tools-version: 5.9
// NOTE: This Package.swift is for reference/SPM compatibility.
// For the full WatchOS + iOS multi-target build, use the Xcode project.
// Run: `open PerceptWatch.xcodeproj` after generating with the setup script.

import PackageDescription

let package = Package(
    name: "PerceptWatch",
    platforms: [
        .iOS(.v17),
        .watchOS(.v10)
    ],
    products: [],
    targets: [
        .target(
            name: "Shared",
            path: "Shared"
        ),
    ]
)
