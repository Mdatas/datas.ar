// swift-tools-version:5.9
// The iPhone's side of the link between a person's own devices, with no screen attached:
// it is built and tested on a Mac (`swift build`, `swift test`) and used by the app in ../App.
import PackageDescription

let package = Package(
    name: "DatasLink",
    platforms: [.iOS(.v15), .macOS(.v12)],
    products: [
        .library(name: "DatasLink", targets: ["DatasLink"]),
        .executable(name: "datas-link", targets: ["datas-link"]),
    ],
    targets: [
        .target(name: "DatasLink"),
        // a tiny command line around the library, for the tests against a real Datas
        .executableTarget(name: "datas-link", dependencies: ["DatasLink"]),
        .testTarget(name: "DatasLinkTests", dependencies: ["DatasLink"]),
    ]
)
