import Foundation
import Vision
import CoreGraphics

// Persistent raw-pixel transport avoids PNG and process-launch cost in every frame.
// Request: little-endian UInt32 width,height,byteCount followed by BGRA bytes.
// Response: one JSON line. Errors are fatal to prevent an empty detection fallback.
func readExactly(_ count: Int) -> Data? {
    var data = Data()
    while data.count < count {
        let chunk = FileHandle.standardInput.readData(ofLength: count - data.count)
        if chunk.isEmpty { return nil }
        data.append(chunk)
    }
    return data
}
func pixelBox(_ box: CGRect, _ width: Int, _ height: Int) -> [Double] {
    [box.minX * Double(width), (1 - box.maxY) * Double(height),
     box.maxX * Double(width), (1 - box.minY) * Double(height)]
}
func pixelQuad(_ result: VNRectangleObservation, _ width: Int, _ height: Int) -> [[Double]] {
    [result.topLeft, result.topRight, result.bottomRight, result.bottomLeft].map {
        [$0.x * Double(width), (1 - $0.y) * Double(height)]
    }
}
let mode = CommandLine.arguments.dropFirst().first ?? "vision-accurate"
let valid = ["vision-fast", "vision-accurate", "vision-rectangles", "vision-union"]
guard valid.contains(mode) else { fatalError("unknown mode \(mode)") }
// Each process owns one lane; serial handlers can safely reuse its requests.
let recognition = VNRecognizeTextRequest()
recognition.recognitionLevel = mode == "vision-fast" ? .fast : .accurate
recognition.usesLanguageCorrection = false
recognition.minimumTextHeight = 0.005
recognition.recognitionLanguages = ["en-US"]
let rectangles = VNDetectTextRectanglesRequest()
rectangles.reportCharacterBoxes = false
while let header = readExactly(12) {
    let values = header.withUnsafeBytes { p in (0..<3).map { UInt32(littleEndian: p.loadUnaligned(fromByteOffset: $0 * 4, as: UInt32.self)) } }
    let width = Int(values[0]), height = Int(values[1]), size = Int(values[2])
    guard width > 0, height > 0, width <= 8192, height <= 8192, size == width * height * 4,
          let bytes = readExactly(size), let provider = CGDataProvider(data: bytes as CFData),
          let cg = CGImage(width: width, height: height, bitsPerComponent: 8, bitsPerPixel: 32,
                           bytesPerRow: width * 4, space: CGColorSpaceCreateDeviceRGB(),
                           bitmapInfo: CGBitmapInfo(rawValue: CGImageAlphaInfo.noneSkipFirst.rawValue).union(.byteOrder32Little),
                           provider: provider, decode: nil, shouldInterpolate: false, intent: .defaultIntent) else {
        fatalError("invalid frame transport")
    }
    autoreleasepool {
        do {
            var output: [[String: Any]] = []
            let handler = VNImageRequestHandler(cgImage: cg, options: [:])
            if mode != "vision-rectangles" {
                try handler.perform([recognition])
                for result in recognition.results ?? [] {
                    guard let candidate = result.topCandidates(1).first else { continue }
                    output.append(["box": pixelBox(result.boundingBox, width, height), "quad": pixelQuad(result, width, height), "text": candidate.string,
                                   "confidence": Double(candidate.confidence)])
                }
            }
            if mode == "vision-rectangles" || mode == "vision-union" {
                try handler.perform([rectangles])
                for result in rectangles.results ?? [] {
                    output.append(["box": pixelBox(result.boundingBox, width, height), "quad": pixelQuad(result, width, height), "text": "", "confidence": Double(result.confidence)])
                }
            }
            let data = try JSONSerialization.data(withJSONObject: output, options: [.sortedKeys])
            FileHandle.standardOutput.write(data)
            FileHandle.standardOutput.write(Data([10]))
        } catch {
            FileHandle.standardError.write(Data("Vision failed: \(error)\n".utf8))
            exit(1)
        }
    }
}
