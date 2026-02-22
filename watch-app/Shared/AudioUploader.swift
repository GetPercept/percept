import Foundation

/// Uploads audio chunks to the configured Percept webhook endpoint
final class AudioUploader {
    static let shared = AudioUploader()
    
    private let session: URLSession
    private let settings = PerceptSettings.shared
    
    init() {
        let config = URLSessionConfiguration.default
        config.timeoutIntervalForRequest = 10
        config.waitsForConnectivity = true
        session = URLSession(configuration: config)
    }
    
    /// Upload a raw PCM16 audio chunk with metadata
    func upload(audioData: Data, metadata: AudioChunkMetadata) async throws {
        guard let url = URL(string: settings.webhookURL) else {
            throw UploadError.invalidURL
        }
        
        var request = URLRequest(url: url)
        request.httpMethod = "POST"
        
        // Multipart form: metadata JSON + raw audio binary
        let boundary = UUID().uuidString
        request.setValue("multipart/form-data; boundary=\(boundary)", forHTTPHeaderField: "Content-Type")
        
        if !settings.authToken.isEmpty {
            request.setValue("Bearer \(settings.authToken)", forHTTPHeaderField: "Authorization")
        }
        
        var body = Data()
        
        // Metadata part
        let metadataJSON = try JSONEncoder().encode(metadata)
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"metadata\"\r\n".data(using: .utf8)!)
        body.append("Content-Type: application/json\r\n\r\n".data(using: .utf8)!)
        body.append(metadataJSON)
        body.append("\r\n".data(using: .utf8)!)
        
        // Audio part
        body.append("--\(boundary)\r\n".data(using: .utf8)!)
        body.append("Content-Disposition: form-data; name=\"audio\"; filename=\"chunk.pcm\"\r\n".data(using: .utf8)!)
        body.append("Content-Type: application/octet-stream\r\n\r\n".data(using: .utf8)!)
        body.append(audioData)
        body.append("\r\n--\(boundary)--\r\n".data(using: .utf8)!)
        
        request.httpBody = body
        
        let (_, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse, (200...299).contains(http.statusCode) else {
            throw UploadError.serverError((response as? HTTPURLResponse)?.statusCode ?? -1)
        }
    }
    
    enum UploadError: LocalizedError {
        case invalidURL
        case serverError(Int)
        
        var errorDescription: String? {
            switch self {
            case .invalidURL: return "Invalid webhook URL"
            case .serverError(let code): return "Server error: \(code)"
            }
        }
    }
}
