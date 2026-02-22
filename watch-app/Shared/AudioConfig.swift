import Foundation
import AVFoundation

/// Shared audio configuration matching Percept receiver.py expectations
enum AudioConfig {
    static let sampleRate: Double = 16000
    static let channels: UInt32 = 1
    static let bitsPerSample: UInt32 = 16
    static let chunkDurationSeconds: Double = 1.0
    static let samplesPerChunk: Int = Int(sampleRate * chunkDurationSeconds)
    static let bytesPerChunk: Int = samplesPerChunk * Int(bitsPerSample / 8)
    
    static var audioFormat: AVAudioFormat {
        AVAudioFormat(
            commonFormat: .pcmFormatInt16,
            sampleRate: sampleRate,
            channels: AVAudioChannelCount(channels),
            interleaved: true
        )!
    }
}

/// Metadata sent alongside each audio chunk
struct AudioChunkMetadata: Codable {
    let timestamp: Double      // Unix timestamp
    let duration: Double       // Chunk duration in seconds
    let deviceId: String       // Watch device identifier
    let sampleRate: Int
    let channels: Int
    let encoding: String       // "pcm16"
    let sequenceNumber: Int    // Chunk index within a recording session
    let sessionId: String      // Unique per recording session
}
