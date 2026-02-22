import Foundation

/// User-configurable settings, stored in UserDefaults with app group sharing
final class PerceptSettings: ObservableObject {
    static let shared = PerceptSettings()
    static let appGroup = "group.com.percept.watch"
    
    private let defaults: UserDefaults
    
    init() {
        let d = UserDefaults(suiteName: PerceptSettings.appGroup) ?? .standard
        self.defaults = d
        self.webhookURL = d.string(forKey: "webhookURL") ?? "https://percept.clawdoor.com/audio"
        self.authToken = d.string(forKey: "authToken") ?? ""
        self.tapHoldEnabled = d.object(forKey: "tapHoldEnabled") as? Bool ?? true
        self.raiseToSpeakEnabled = d.object(forKey: "raiseToSpeakEnabled") as? Bool ?? false
        self.complicationEnabled = d.object(forKey: "complicationEnabled") as? Bool ?? true
    }
    
    // MARK: - Webhook
    
    @Published var webhookURL: String {
        didSet { defaults.set(webhookURL, forKey: "webhookURL") }
    }
    
    @Published var authToken: String {
        didSet { defaults.set(authToken, forKey: "authToken") }
    }
    
    // MARK: - Trigger Modes
    
    @Published var tapHoldEnabled: Bool {
        didSet { defaults.set(tapHoldEnabled, forKey: "tapHoldEnabled") }
    }
    
    @Published var raiseToSpeakEnabled: Bool {
        didSet { defaults.set(raiseToSpeakEnabled, forKey: "raiseToSpeakEnabled") }
    }
    
    @Published var complicationEnabled: Bool {
        didSet { defaults.set(complicationEnabled, forKey: "complicationEnabled") }
    }
    
    // MARK: - Device
    
    var deviceId: String {
        if let id = defaults.string(forKey: "deviceId") { return id }
        let id = UUID().uuidString
        defaults.set(id, forKey: "deviceId")
        return id
    }
    
    // MARK: - Init from defaults
    
    private func load() {
        webhookURL = defaults.string(forKey: "webhookURL") ?? "https://percept.clawdoor.com/audio"
        authToken = defaults.string(forKey: "authToken") ?? ""
        tapHoldEnabled = defaults.object(forKey: "tapHoldEnabled") as? Bool ?? true
        raiseToSpeakEnabled = defaults.object(forKey: "raiseToSpeakEnabled") as? Bool ?? false
        complicationEnabled = defaults.object(forKey: "complicationEnabled") as? Bool ?? true
    }
    
    static func create() -> PerceptSettings {
        let s = PerceptSettings()
        s.load()
        return s
    }
}
