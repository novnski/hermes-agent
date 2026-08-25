import Foundation
import Testing

@testable import HermesParakeetCore

@Test
func parsesTranscriptionArguments() throws {
  let options = try ParakeetCommandOptions.parse([
    "--input", "/tmp/input.ogg",
    "--output", "/tmp/output.txt",
    "--model-dir", "/tmp/model",
    "--language", " en ",
  ])

  #expect(options.inputPath == "/tmp/input.ogg")
  #expect(options.outputPath == "/tmp/output.txt")
  #expect(options.modelDirectory == "/tmp/model")
  #expect(options.language == "en")
  #expect(!options.checkModelOnly)
}

@Test
func modelCheckNeedsOnlyModelDirectory() throws {
  let options = try ParakeetCommandOptions.parse([
    "--check-model",
    "--model-dir", "/tmp/model",
  ])

  #expect(options.checkModelOnly)
  #expect(options.inputPath == nil)
  #expect(options.outputPath == nil)
}

@Test
func rejectsIncompleteTranscriptionArguments() {
  #expect(throws: ParakeetSTTError.self) {
    try ParakeetCommandOptions.parse([
      "--input", "/tmp/input.ogg",
      "--model-dir", "/tmp/model",
    ])
  }
}

@Test
func writesNormalizedTranscriptAtomically() throws {
  let directory = FileManager.default.temporaryDirectory
    .appendingPathComponent("hermes-parakeet-test-\(UUID().uuidString)")
  try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true)
  defer { try? FileManager.default.removeItem(at: directory) }
  let output = directory.appendingPathComponent("transcript.txt")

  try ParakeetTranscriber().writeTranscript("  hello from Parakeet  \n", to: output)

  #expect(try String(contentsOf: output, encoding: .utf8) == "hello from Parakeet\n")
}

@Test
func rejectsEmptyTranscript() {
  let output = FileManager.default.temporaryDirectory
    .appendingPathComponent("hermes-parakeet-empty-\(UUID().uuidString).txt")
  defer { try? FileManager.default.removeItem(at: output) }

  #expect(throws: ParakeetSTTError.emptyTranscript) {
    try ParakeetTranscriber().writeTranscript(" \n\t ", to: output)
  }
}
