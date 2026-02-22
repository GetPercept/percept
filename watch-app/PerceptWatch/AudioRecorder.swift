import Foundation
import AVFoundation
import WatchConnectivity
import WatchKit

/// Captures audio on Apple Watch using AVAudioEngine, chunks into 1-second PCM16 buffers
final class AudioRecorder: ObservableObject {
    @Published var isRecording = false
    @Published var audioLevel: Float = 0 // 0...1 normalized for waveform
    
    private var audioEngine: AVAudioEngine?
    private var currentSessionId = ""
    private var sequenceNumber = 0
    private var chunkBuffer = Data()
    private let connectivity = WatchConnectivityManager.shared
    private let uploader = AudioUploader.shared
    private let settings = PerceptSettings.shared
    
    func startRecording() {
        guard !isRecording else { return }
        
        let session = AVAudioSession.sharedInstance()
        do {
            try session.setCategory(.record, mode: .default, policy: .default)
            try session.setActive(true)
        } catch {
            print("AudioSession error: \(error)")
            return
        }
        
        audioEngine = AVAudioEngine()
        guard let engine = audioEngine else { return }
        
        let inputNode = engine.inputNode
        let inputFormat = inputNode.outputFormat(forBus: 0)
        
        // Target format: PCM16, 16kHz, mono
        guard let targetFormat = AVAudioFormat(
            commonFormat: .pcmFormatInt16,
            sampleRate: AudioConfig.sampleRate,
            channels: 1,
            interleaved: true
        ) else { return }
        
        // Install converter if needed
        guard let converter = AVAudioConverter(from: inputFormat, to: targetFormat) else {
            // Try installing tap with native format and convert manually
            print("Could not create converter, using native format")
            return
        }
        
        currentSessionId = UUID().uuidString
        sequenceNumber = 0
        chunkBuffer = Data()
        
        inputNode.installTap(onBus: 0, bufferSize: 1024, format: inputFormat) { [weak self] buffer, _ in
            self?.processBuffer(buffer, converter: converter, targetFormat: targetFormat)
        }
        
        do {
            try engine.start()
            isRecording = true
            // Haptic: start recording
            WKInterfaceDevice.current().play(.start)
        } catch {
            print("Engine start error: \(error)")
        }
    }
    
    func stopRecording() {
        guard isRecording else { return }
        
        audioEngine?.inputNode.removeTap(onBus: 0)
        audioEngine?.stop()
        audioEngine = nil
        isRecording = false
        
        // Send any remaining buffered audio
        if !chunkBuffer.isEmpty {
            sendChunk(chunkBuffer)
            chunkBuffer = Data()
        }
        
        // Haptic: stop recording
        WKInterfaceDevice.current().play(.stop)
        
        try? AVAudioSession.sharedInstance().setActive(false)
    }
    
    private func processBuffer(_ buffer: AVAudioPCMBuffer, converter: AVAudioConverter, targetFormat: AVAudioFormat) {
        // Convert to target format
        let frameCapacity = AVAudioFrameCount(
            Double(buffer.frameLength) * AudioConfig.sampleRate / buffer.format.sampleRate
        )
        guard let convertedBuffer = AVAudioPCMBuffer(pcmFormat: targetFormat, frameCapacity: frameCapacity) else { return }
        
        var error: NSError?
        var isDone = false
        converter.convert(to: convertedBuffer, error: &error) { _, outStatus in
            if isDone {
                outStatus.pointee = .noDataNow
                return nil
            }
            isDone = true
            outStatus.pointee = .haveData
            return buffer
        }
        
        if let error { print("Conversion error: \(error)"); return }
        
        // Extract raw PCM16 bytes
        guard let int16Data = convertedBuffer.int16ChannelData else { return }
        let data = Data(bytes: int16Data[0], count: Int(convertedBuffer.frameLength) * 2)
        
        // Update audio level for UI
        let rms = computeRMS(int16Data[0], frameCount: Int(convertedBuffer.frameLength))
        DispatchQueue.main.async { self.audioLevel = min(rms / 8000, 1.0) }
        
        // Accumulate into chunk buffer
        chunkBuffer.append(data)
        
        // Send complete 1-second chunks
        while chunkBuffer.count >= AudioConfig.bytesPerChunk {
            let chunk = chunkBuffer.prefix(AudioConfig.bytesPerChunk)
            sendChunk(Data(chunk))
            chunkBuffer = Data(chunkBuffer.dropFirst(AudioConfig.bytesPerChunk))
        }
    }
    
    private func sendChunk(_ data: Data) {
        let metadata = AudioChunkMetadata(
            timestamp: Date().timeIntervalSince1970,
            duration: Double(data.count) / (AudioConfig.sampleRate * 2),
            deviceId: settings.deviceId,
            sampleRate: Int(AudioConfig.sampleRate),
            channels: Int(AudioConfig.channels),
            encoding: "pcm16",
            sequenceNumber: sequenceNumber,
            sessionId: currentSessionId
        )
        sequenceNumber += 1
        
        // Try WatchConnectivity relay to iPhone first, fall back to direct HTTP upload
        if WCSession.isSupported() && WCSession.default.isReachable {
            connectivity.sendAudioChunk(data, metadata: metadata)
        } else {
            // Direct upload from Watch (WiFi or cellular)
            Task {
                do {
                    try await uploader.upload(audioData: data, metadata: metadata)
                } catch {
                    print("Direct upload error: \(error)")
                    // Fall back to WC transferFile for background delivery
                    connectivity.sendAudioChunk(data, metadata: metadata)
                }
            }
        }
    }
    
    private func computeRMS(_ samples: UnsafePointer<Int16>, frameCount: Int) -> Float {
        var sum: Float = 0
        for i in 0..<min(frameCount, 256) {
            let s = Float(samples[i])
            sum += s * s
        }
        return sqrt(sum / Float(min(frameCount, 256)))
    }
}
