import Foundation
import Combine

/// Receives audio chunks from Watch via WatchConnectivity and forwards to Percept API
final class AudioRelayService: ObservableObject, @unchecked Sendable {
    @Published var chunksReceived: Int = 0
    @Published var chunksForwarded: Int = 0
    @Published var lastError: String?
    @Published var isConnected = false
    @Published var currentSessionId: String?
    
    private let uploader = AudioUploader.shared
    private let connectivity = WatchConnectivityManager.shared
    
    func start() {
        connectivity.onAudioChunkReceived = { [weak self] audioData, metadata in
            self?.handleChunk(audioData: audioData, metadata: metadata)
        }
        
        // Observe connectivity
        Timer.scheduledTimer(withTimeInterval: 2, repeats: true) { [weak self] _ in
            DispatchQueue.main.async {
                self?.isConnected = self?.connectivity.isReachable ?? false
            }
        }
    }
    
    private func handleChunk(audioData: Data, metadata: AudioChunkMetadata) {
        DispatchQueue.main.async {
            self.chunksReceived += 1
            self.currentSessionId = metadata.sessionId
        }
        
        Task {
            do {
                try await uploader.upload(audioData: audioData, metadata: metadata)
                DispatchQueue.main.async {
                    self.chunksForwarded += 1
                    self.lastError = nil
                }
            } catch {
                DispatchQueue.main.async {
                    self.lastError = error.localizedDescription
                }
            }
        }
    }
}
