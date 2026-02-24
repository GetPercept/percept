import Foundation
import Combine

/// Mock recorder for Simulator — generates fake audio levels and sends test data
final class MockAudioRecorder: ObservableObject, @unchecked Sendable {
    @Published var isRecording = false
    @Published var audioLevel: Float = 0
    
    private var timer: Timer?
    private var elapsed: TimeInterval = 0
    
    func startRecording() {
        guard !isRecording else { return }
        isRecording = true
        elapsed = 0
        
        // Simulate audio levels
        timer = Timer.scheduledTimer(withTimeInterval: 0.05, repeats: true) { [weak self] _ in
            guard let self, self.isRecording else { return }
            self.elapsed += 0.05
            // Simulate speech-like waveform
            let base = Float(sin(self.elapsed * 3.0) * 0.3 + 0.4)
            let noise = Float.random(in: -0.15...0.15)
            self.audioLevel = max(0, min(1, base + noise))
        }
    }
    
    func stopRecording() {
        guard isRecording else { return }
        isRecording = false
        timer?.invalidate()
        timer = nil
        audioLevel = 0
        
        // Simulate sending transcript to server
        sendMockTranscript()
    }
    
    private func sendMockTranscript() {
        let mockText = "Hey Jarvis, this is a test from the Apple Watch simulator."
        print("[MOCK] Would send transcript: \(mockText)")
        
        // Actually POST to our Percept server if reachable
        Task {
            await postMockTranscript(mockText)
        }
    }
    
    private func postMockTranscript(_ text: String) async {
        guard let url = URL(string: "https://percept.clawdoor.com/webhook/transcript?uid=watch-simulator") else { return }
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        
        let payload: [String: Any] = [
            "segments": [
                [
                    "text": text,
                    "speaker": "SPEAKER_0",
                    "speaker_id": 0,
                    "is_user": true,
                    "start": 0.0,
                    "end": 3.0
                ]
            ],
            "session_id": "watch-simulator-\(UUID().uuidString.prefix(8))"
        ]
        
        do {
            request.httpBody = try JSONSerialization.data(withJSONObject: payload)
            let (_, response) = try await URLSession.shared.data(for: request)
            if let httpResponse = response as? HTTPURLResponse {
                print("[MOCK] Server responded: \(httpResponse.statusCode)")
            }
        } catch {
            print("[MOCK] Failed to send: \(error.localizedDescription)")
        }
    }
}
