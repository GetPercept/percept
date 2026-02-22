import Foundation
import WatchConnectivity

/// Manages Watch↔iPhone communication via WCSession
final class WatchConnectivityManager: NSObject, ObservableObject {
    static let shared = WatchConnectivityManager()
    
    @Published var isReachable = false
    @Published var lastError: String?
    
    /// Called on iPhone when audio chunk arrives from Watch
    var onAudioChunkReceived: ((Data, AudioChunkMetadata) -> Void)?
    
    /// Called on Watch when settings sync arrives from iPhone
    var onSettingsReceived: (([String: Any]) -> Void)?
    
    private override init() {
        super.init()
    }
    
    func activate() {
        guard WCSession.isSupported() else { return }
        WCSession.default.delegate = self
        WCSession.default.activate()
    }
    
    // MARK: - Send from Watch to iPhone
    
    func sendAudioChunk(_ data: Data, metadata: AudioChunkMetadata) {
        guard WCSession.default.isReachable else {
            // Fall back to transferUserInfo for background delivery
            let metaDict: [String: Any] = [
                "type": "audio_chunk",
                "timestamp": metadata.timestamp,
                "duration": metadata.duration,
                "deviceId": metadata.deviceId,
                "sampleRate": metadata.sampleRate,
                "channels": metadata.channels,
                "encoding": metadata.encoding,
                "sequenceNumber": metadata.sequenceNumber,
                "sessionId": metadata.sessionId
            ]
            // Save audio to temp file for transferFile
            let tempURL = FileManager.default.temporaryDirectory
                .appendingPathComponent("\(metadata.sessionId)_\(metadata.sequenceNumber).pcm")
            try? data.write(to: tempURL)
            WCSession.default.transferFile(tempURL, metadata: metaDict)
            return
        }
        
        // Real-time: send via message data
        var payload = Data()
        let metaJSON = try! JSONEncoder().encode(metadata)
        var metaLength = UInt32(metaJSON.count)
        payload.append(Data(bytes: &metaLength, count: 4))
        payload.append(metaJSON)
        payload.append(data)
        
        WCSession.default.sendMessageData(payload, replyHandler: nil) { error in
            DispatchQueue.main.async {
                self.lastError = error.localizedDescription
            }
        }
    }
    
    // MARK: - Send settings from iPhone to Watch
    
    func sendSettings(_ settings: [String: Any]) {
        var msg = settings
        msg["type"] = "settings_sync"
        if WCSession.default.isReachable {
            WCSession.default.sendMessage(msg, replyHandler: nil)
        } else {
            try? WCSession.default.updateApplicationContext(msg)
        }
    }
}

// MARK: - WCSessionDelegate

extension WatchConnectivityManager: WCSessionDelegate {
    func session(_ session: WCSession, activationDidCompleteWith state: WCSessionActivationState, error: Error?) {
        DispatchQueue.main.async {
            self.isReachable = session.isReachable
            if let error { self.lastError = error.localizedDescription }
        }
    }
    
    func sessionReachabilityDidChange(_ session: WCSession) {
        DispatchQueue.main.async {
            self.isReachable = session.isReachable
        }
    }
    
    // Real-time audio data from Watch
    func session(_ session: WCSession, didReceiveMessageData messageData: Data) {
        guard messageData.count > 4 else { return }
        let metaLength = messageData.prefix(4).withUnsafeBytes { $0.load(as: UInt32.self) }
        let metaData = messageData[4..<(4 + Int(metaLength))]
        let audioData = messageData[(4 + Int(metaLength))...]
        
        if let metadata = try? JSONDecoder().decode(AudioChunkMetadata.self, from: metaData) {
            onAudioChunkReceived?(Data(audioData), metadata)
        }
    }
    
    // Background file transfer from Watch
    func session(_ session: WCSession, didReceive file: WCSessionFile) {
        guard let meta = file.metadata, meta["type"] as? String == "audio_chunk" else { return }
        if let audioData = try? Data(contentsOf: file.fileURL) {
            let metadata = AudioChunkMetadata(
                timestamp: meta["timestamp"] as? Double ?? Date().timeIntervalSince1970,
                duration: meta["duration"] as? Double ?? AudioConfig.chunkDurationSeconds,
                deviceId: meta["deviceId"] as? String ?? "unknown",
                sampleRate: meta["sampleRate"] as? Int ?? Int(AudioConfig.sampleRate),
                channels: meta["channels"] as? Int ?? Int(AudioConfig.channels),
                encoding: meta["encoding"] as? String ?? "pcm16",
                sequenceNumber: meta["sequenceNumber"] as? Int ?? 0,
                sessionId: meta["sessionId"] as? String ?? UUID().uuidString
            )
            onAudioChunkReceived?(audioData, metadata)
        }
        try? FileManager.default.removeItem(at: file.fileURL)
    }
    
    // Settings sync
    func session(_ session: WCSession, didReceiveMessage message: [String: Any]) {
        if message["type"] as? String == "settings_sync" {
            onSettingsReceived?(message)
        }
    }
    
    func session(_ session: WCSession, didReceiveApplicationContext applicationContext: [String: Any]) {
        if applicationContext["type"] as? String == "settings_sync" {
            onSettingsReceived?(applicationContext)
        }
    }
    
    #if os(iOS)
    func sessionDidBecomeInactive(_ session: WCSession) {}
    func sessionDidDeactivate(_ session: WCSession) {
        session.activate()
    }
    #endif
}
