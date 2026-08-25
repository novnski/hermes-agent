// swift-tools-version: 6.0

import PackageDescription

let package = Package(
  name: "HermesParakeetSTT",
  platforms: [
    .macOS(.v14)
  ],
  products: [
    .executable(
      name: "hermes-parakeet-stt",
      targets: ["HermesParakeetSTT"]
    )
  ],
  dependencies: [
    .package(
      url: "https://github.com/FluidInference/FluidAudio.git",
      revision: "8048812869b0c7c6fa393e564a4fb6f95126ba23"
    )
  ],
  targets: [
    .target(
      name: "HermesParakeetCore",
      dependencies: [
        .product(name: "FluidAudio", package: "FluidAudio")
      ]
    ),
    .executableTarget(
      name: "HermesParakeetSTT",
      dependencies: ["HermesParakeetCore"]
    ),
    .testTarget(
      name: "HermesParakeetCoreTests",
      dependencies: ["HermesParakeetCore"]
    ),
  ]
)
