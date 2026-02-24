import SwiftUI

struct CompanionView: View {
    @EnvironmentObject var relay: AudioRelayService
    @StateObject private var settings = PerceptSettings.create()
    @State private var showSettings = false
    
    var body: some View {
        NavigationView {
            VStack(spacing: 24) {
                // Connection status
                HStack {
                    Circle()
                        .fill(relay.isConnected ? Color.green : Color.red)
                        .frame(width: 12, height: 12)
                    Text(relay.isConnected ? "Watch Connected" : "Watch Disconnected")
                        .font(.headline)
                }
                .padding(.top, 20)
                
                // Stats
                VStack(spacing: 16) {
                    StatCard(title: "Chunks Received", value: "\(relay.chunksReceived)")
                    StatCard(title: "Chunks Forwarded", value: "\(relay.chunksForwarded)")
                    
                    if let session = relay.currentSessionId {
                        Text("Session: \(session.prefix(8))...")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                }
                .padding()
                .background(Color.gray.opacity(0.15))
                .cornerRadius(12)
                
                // Error display
                if let error = relay.lastError {
                    HStack {
                        Image(systemName: "exclamationmark.triangle.fill")
                            .foregroundColor(.orange)
                        Text(error)
                            .font(.caption)
                            .foregroundColor(.orange)
                    }
                    .padding()
                    .background(Color.orange.opacity(0.1))
                    .cornerRadius(8)
                }
                
                // Webhook target
                VStack(alignment: .leading, spacing: 4) {
                    Text("Webhook")
                        .font(.caption)
                        .foregroundColor(.secondary)
                    Text(settings.webhookURL)
                        .font(.system(.body, design: .monospaced))
                        .lineLimit(1)
                }
                .padding()
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(Color.gray.opacity(0.15))
                .cornerRadius(8)
                
                Spacer()
            }
            .padding()
            .navigationTitle("Percept")
            .toolbar {
                ToolbarItem(placement: .automatic) {
                    Button(action: { showSettings = true }) {
                        Image(systemName: "gear")
                    }
                }
            }
            .sheet(isPresented: $showSettings) {
                SettingsView(settings: settings)
            }
        }
    }
}

struct StatCard: View {
    let title: String
    let value: String
    
    var body: some View {
        HStack {
            Text(title)
                .foregroundColor(.secondary)
            Spacer()
            Text(value)
                .font(.system(.title2, design: .monospaced))
                .fontWeight(.bold)
        }
    }
}
