import FluidAudio
import Foundation

public enum ParakeetSTTError: LocalizedError, Equatable {
  case invalidArguments(String)
  case inputNotReadable(String)
  case modelUnavailable(String)
  case emptyTranscript
  case audioConversionFailed(String)

  public var errorDescription: String? {
    switch self {
    case .invalidArguments(let message):
      message
    case .inputNotReadable(let path):
      "Audio input is not a readable regular file: \(path)"
    case .modelUnavailable(let path):
      "Parakeet v3 model assets are incomplete or unreadable: \(path)"
    case .emptyTranscript:
      "Parakeet returned an empty transcript"
    case .audioConversionFailed(let message):
      "Audio conversion failed: \(message)"
    }
  }
}

public struct ParakeetCommandOptions: Equatable {
  public let inputPath: String?
  public let outputPath: String?
  public let modelDirectory: String
  public let language: String?
  public let checkModelOnly: Bool

  public init(
    inputPath: String?,
    outputPath: String?,
    modelDirectory: String,
    language: String?,
    checkModelOnly: Bool
  ) {
    self.inputPath = inputPath
    self.outputPath = outputPath
    self.modelDirectory = modelDirectory
    self.language = language
    self.checkModelOnly = checkModelOnly
  }

  public static func parse(_ arguments: [String]) throws -> ParakeetCommandOptions {
    var inputPath: String?
    var outputPath: String?
    var modelDirectory: String?
    var language: String?
    var checkModelOnly = false

    var index = 0
    while index < arguments.count {
      let argument = arguments[index]
      switch argument {
      case "--input", "--output", "--model-dir", "--language":
        guard index + 1 < arguments.count else {
          throw ParakeetSTTError.invalidArguments("Missing value for \(argument)")
        }
        let value = arguments[index + 1]
        switch argument {
        case "--input": inputPath = value
        case "--output": outputPath = value
        case "--model-dir": modelDirectory = value
        case "--language": language = value
        default: break
        }
        index += 2
      case "--check-model":
        checkModelOnly = true
        index += 1
      default:
        throw ParakeetSTTError.invalidArguments("Unknown argument: \(argument)")
      }
    }

    guard let modelDirectory, !modelDirectory.isEmpty else {
      throw ParakeetSTTError.invalidArguments("--model-dir is required")
    }
    if !checkModelOnly && (inputPath?.isEmpty != false || outputPath?.isEmpty != false) {
      throw ParakeetSTTError.invalidArguments(
        "--input and --output are required unless --check-model is used"
      )
    }

    let normalizedLanguage = language?.trimmingCharacters(in: .whitespacesAndNewlines)
    return ParakeetCommandOptions(
      inputPath: inputPath,
      outputPath: outputPath,
      modelDirectory: modelDirectory,
      language: normalizedLanguage?.isEmpty == false ? normalizedLanguage : nil,
      checkModelOnly: checkModelOnly
    )
  }
}

public struct ParakeetTranscriber {
  public init() {}

  public func modelIsAvailable(at directory: URL) -> Bool {
    AsrModels.modelsExist(at: directory, version: .v3)
  }

  public func transcribe(
    inputURL: URL,
    modelDirectory: URL,
    languageCode: String?
  ) async throws -> String {
    try validateInput(inputURL)
    guard modelIsAvailable(at: modelDirectory) else {
      throw ParakeetSTTError.modelUnavailable(modelDirectory.path)
    }

    let models = try await AsrModels.load(from: modelDirectory, version: .v3)
    let manager = AsrManager(config: .default, models: models)
    var decoderState = TdtDecoderState.make(decoderLayers: await manager.decoderLayerCount)
    let language = languageCode.flatMap(Language.init(rawValue:))

    do {
      let result = try await manager.transcribe(
        inputURL,
        decoderState: &decoderState,
        language: language
      )
      await manager.cleanup()
      return try nonemptyTranscript(result.text)
    } catch let firstError {
      do {
        let convertedURL = try convertToWAV(inputURL)
        defer { try? FileManager.default.removeItem(at: convertedURL.deletingLastPathComponent()) }
        decoderState = TdtDecoderState.make(decoderLayers: await manager.decoderLayerCount)
        let result = try await manager.transcribe(
          convertedURL,
          decoderState: &decoderState,
          language: language
        )
        await manager.cleanup()
        return try nonemptyTranscript(result.text)
      } catch let fallbackError {
        await manager.cleanup()
        throw ParakeetSTTError.audioConversionFailed(
          "direct decode failed with \(firstError.localizedDescription); "
            + "WAV fallback failed with \(fallbackError.localizedDescription)"
        )
      }
    }
  }

  public func writeTranscript(_ transcript: String, to outputURL: URL) throws {
    let text = try nonemptyTranscript(transcript) + "\n"
    try Data(text.utf8).write(to: outputURL, options: .atomic)
  }

  private func validateInput(_ inputURL: URL) throws {
    let values = try inputURL.resourceValues(forKeys: [
      .isRegularFileKey,
      .isReadableKey,
      .isSymbolicLinkKey,
    ])
    guard values.isRegularFile == true,
      values.isReadable == true,
      values.isSymbolicLink != true
    else {
      throw ParakeetSTTError.inputNotReadable(inputURL.path)
    }
  }

  private func nonemptyTranscript(_ transcript: String) throws -> String {
    let normalized = transcript.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !normalized.isEmpty else {
      throw ParakeetSTTError.emptyTranscript
    }
    return normalized
  }

  private func convertToWAV(_ inputURL: URL) throws -> URL {
    let candidates = [
      ProcessInfo.processInfo.environment["PATH"]?
        .split(separator: ":")
        .map(String.init)
        .map { URL(fileURLWithPath: $0).appendingPathComponent("ffmpeg").path } ?? [],
      ["/opt/homebrew/bin/ffmpeg", "/usr/local/bin/ffmpeg", "/usr/bin/ffmpeg"],
    ].flatMap { $0 }
    guard let ffmpeg = candidates.first(where: { FileManager.default.isExecutableFile(atPath: $0) })
    else {
      throw ParakeetSTTError.audioConversionFailed("ffmpeg was not found")
    }

    let temporaryDirectory = FileManager.default.temporaryDirectory
      .appendingPathComponent("hermes-parakeet-\(UUID().uuidString)", isDirectory: true)
    try FileManager.default.createDirectory(
      at: temporaryDirectory,
      withIntermediateDirectories: true
    )
    let outputURL = temporaryDirectory.appendingPathComponent("audio.wav")
    let process = Process()
    process.executableURL = URL(fileURLWithPath: ffmpeg)
    process.arguments = [
      "-nostdin", "-v", "error", "-y", "-i", inputURL.path,
      "-vn", "-ac", "1", "-ar", "16000", outputURL.path,
    ]
    let errorPipe = Pipe()
    process.standardOutput = FileHandle.nullDevice
    process.standardError = errorPipe
    try process.run()
    process.waitUntilExit()
    guard process.terminationStatus == 0 else {
      let data = errorPipe.fileHandleForReading.readDataToEndOfFile()
      let detail = String(decoding: data, as: UTF8.self)
        .trimmingCharacters(in: .whitespacesAndNewlines)
      try? FileManager.default.removeItem(at: temporaryDirectory)
      throw ParakeetSTTError.audioConversionFailed(
        detail.isEmpty ? "ffmpeg exited with status \(process.terminationStatus)" : detail
      )
    }
    return outputURL
  }
}
