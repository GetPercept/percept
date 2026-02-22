import SwiftUI

struct SettingsView: View {
    @ObservedObject var settings: PerceptSettings
    @Environment(\.dismiss) var dismiss
    
    var body: some View {
        NavigationView {
            Form {
                Section("API Configuration") {
                    VStack(alignment: .leading) {
                        Text("Webhook URL")
                            .font(.caption)
                            .foregroundColor(.secondary)
                        TextField("http://localhost:8900/audio", text: $settings.webhookURL)
                            .textFieldStyle(.roundedBorder)
                            .font(.system(.body, design: .monospaced))
                            .autocapitalization(.none)
                            .disableAutocorrection(true)
                    }
                    
                    VStack(alignment: .leading) {
                        Text("Auth Token")
                            .font(.caption)
                            .foregroundColor(.secondary)
                        SecureField("Bearer token (optional)", text: $settings.authToken)
                            .textFieldStyle(.roundedBorder)
                    }
                }
                
                Section("Trigger Modes") {
                    Toggle("Tap & Hold", isOn: $settings.tapHoldEnabled)
                    Toggle("Raise to Speak", isOn: $settings.raiseToSpeakEnabled)
                    Toggle("Complication Tap", isOn: $settings.complicationEnabled)
                }
                
                Section("Audio") {
                    HStack {
                        Text("Format")
                        Spacer()
                        Text("PCM16, 16kHz, Mono")
                            .foregroundColor(.secondary)
                    }
                    HStack {
                        Text("Chunk Duration")
                        Spacer()
                        Text("1 second")
                            .foregroundColor(.secondary)
                    }
                }
                
                Section("Device") {
                    HStack {
                        Text("Device ID")
                        Spacer()
                        Text(settings.deviceId.prefix(8) + "...")
                            .foregroundColor(.secondary)
                            .font(.system(.caption, design: .monospaced))
                    }
                }
                
                // TODO: Section("Health Data") {
                //     Toggle("Send Heart Rate", isOn: .constant(false))
                //     Text("Attach heart rate context to audio chunks")
                //         .font(.caption).foregroundColor(.secondary)
                // }
                
                // TODO: Section("Siri") {
                //     Text("\"Hey Siri, tell Jarvis...\"")
                //     Text("Configure in Shortcuts app")
                //         .font(.caption).foregroundColor(.secondary)
                // }
            }
            .navigationTitle("Settings")
            .toolbar {
                ToolbarItem(placement: .navigationBarTrailing) {
                    Button("Done") {
                        // Sync settings to Watch
                        WatchConnectivityManager.shared.sendSettings([
                            "webhookURL": settings.webhookURL,
                            "tapHoldEnabled": settings.tapHoldEnabled,
                            "raiseToSpeakEnabled": settings.raiseToSpeakEnabled,
                            "complicationEnabled": settings.complicationEnabled
                        ])
                        dismiss()
                    }
                }
            }
        }
    }
}
