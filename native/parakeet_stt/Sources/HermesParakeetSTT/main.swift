import Darwin
import Foundation
import HermesParakeetCore

@main
struct HermesParakeetSTTMain {
  static func main() async {
    let startedAt = ContinuousClock.now
    do {
      let options = try ParakeetCommandOptions.parse(
        Array(CommandLine.arguments.dropFirst())
      )
      let transcriber = ParakeetTranscriber()
      let modelDirectory = URL(
        fileURLWithPath: options.modelDirectory,
        isDirectory: true
      )

      if options.checkModelOnly {
        guard transcriber.modelIsAvailable(at: modelDirectory) else {
          throw ParakeetSTTError.modelUnavailable(modelDirectory.path)
        }
        writeStandardError("Parakeet v3 model is ready at \(modelDirectory.path)\n")
        return
      }

      guard let inputPath = options.inputPath, let outputPath = options.outputPath else {
        throw ParakeetSTTError.invalidArguments("Missing transcription paths")
      }
      let transcript = try await transcriber.transcribe(
        inputURL: URL(fileURLWithPath: inputPath),
        modelDirectory: modelDirectory,
        languageCode: options.language
      )
      try transcriber.writeTranscript(
        transcript,
        to: URL(fileURLWithPath: outputPath)
      )
      let elapsed = startedAt.duration(to: .now)
      writeStandardError("Hermes Parakeet transcription completed in \(elapsed)\n")
    } catch {
      let message = (error as? LocalizedError)?.errorDescription ?? error.localizedDescription
      writeStandardError("Hermes Parakeet STT failed: \(message)\n")
      exit(1)
    }
  }

  private static func writeStandardError(_ message: String) {
    FileHandle.standardError.write(Data(message.utf8))
  }
}
